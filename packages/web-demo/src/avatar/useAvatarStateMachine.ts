import { useEffect, useMemo, useSyncExternalStore } from 'react'
import { useMachine } from '@xstate/react'
import { assign, setup } from 'xstate'
import { REDUCED_MOTION_MULTIPLIER, STATE_HOLD_MS } from './avatar.constants'
import type { AvatarEvent, AvatarStateName, MinimizeMode, QueuedOutcome } from './avatar.types'

/**
 * Implements AskBPL_Avatar_Spec.md §4 (the 14 behaviors) and §5 (concurrency
 * rules around drag + minimize). The machine is the single source of truth
 * for which Spline state is currently driving the avatar; the host shell
 * pushes `AvatarEvent`s into it and consumes a small derived view back.
 */

type Context = {
  /** Last "settled" state to return to after dragging. */
  lastSettled: AvatarStateName
  /** Active minimization mode, orthogonal to the request lifecycle. */
  minimized: MinimizeMode
  /** Outcome that arrived while minimized (drives the static dot). */
  queuedOutcome: QueuedOutcome
  /** OS-level prefers-reduced-motion flag, drives delay shortening. */
  reducedMotion: boolean
}

type MachineInput = { reducedMotion: boolean }

const buildInitialContext = (input: MachineInput): Context => ({
  lastSettled: 'idle',
  minimized: 'none',
  queuedOutcome: null,
  reducedMotion: input.reducedMotion,
})

const settled = (state: AvatarStateName): boolean =>
  state !== 'dragging' && state !== 'minimized' && state !== 'goodbye'

const holdDelay = (
  base: (typeof STATE_HOLD_MS)[keyof typeof STATE_HOLD_MS],
): (({ context }: { context: Context }) => number) => {
  return ({ context }) =>
    context.reducedMotion ? Math.round(base * REDUCED_MOTION_MULTIPLIER) : base
}

const machine = setup({
  types: {
    context: {} as Context,
    events: {} as AvatarEvent,
    input: {} as MachineInput,
  },
  delays: {
    successHold: holdDelay(STATE_HOLD_MS.success),
    refusalSoftHold: holdDelay(STATE_HOLD_MS.refusalOutOfCorpus),
    refusalPiiHold: holdDelay(STATE_HOLD_MS.refusalPII),
    routingHold: holdDelay(STATE_HOLD_MS.routing),
    greetingHold: holdDelay(STATE_HOLD_MS.greeting),
    goodbyeHold: holdDelay(STATE_HOLD_MS.goodbye),
    errorHold: holdDelay(STATE_HOLD_MS.error),
  },
  actions: {
    rememberSettled: assign(({ context }, params: { state: AvatarStateName }) => ({
      lastSettled: settled(params.state) ? params.state : context.lastSettled,
    })),
    queueOutcome: assign((_, params: { outcome: QueuedOutcome }) => ({
      queuedOutcome: params.outcome,
    })),
    clearQueued: assign({ queuedOutcome: null as QueuedOutcome }),
    setMinimizeMode: assign((_, params: { mode: MinimizeMode }) => ({
      minimized: params.mode,
    })),
    setLastSettled: assign((_, params: { state: AvatarStateName }) => ({
      lastSettled: params.state,
    })),
    setReducedMotion: assign((_, params: { reducedMotion: boolean }) => ({
      reducedMotion: params.reducedMotion,
    })),
  },
  guards: {
    isMinimized: ({ context }) => context.minimized !== 'none',
  },
}).createMachine({
  id: 'askbplAvatar',
  context: ({ input }) => buildInitialContext(input),
  initial: 'idle',
  on: {
    SET_REDUCED_MOTION: {
      actions: {
        type: 'setReducedMotion',
        params: ({ event }) => ({ reducedMotion: event.reducedMotion }),
      },
    },
    DRAG_START: { target: '.dragging' },
    MINIMIZE: {
      target: '.minimized',
      actions: { type: 'setMinimizeMode', params: ({ event }) => ({ mode: event.mode }) },
    },
    RESTORE: {
      target: '.idle',
      actions: [
        { type: 'setMinimizeMode', params: { mode: 'none' } },
        { type: 'clearQueued' },
      ],
    },
    DEV_FORCE: [
      {
        guard: ({ event }) => event.state === 'minimized',
        target: '.minimized',
        actions: { type: 'setMinimizeMode', params: { mode: 'pill' } },
      },
      {
        target: '.dynamic',
        actions: { type: 'setLastSettled', params: ({ event }) => ({ state: event.state }) },
      },
    ],
    RESPONSE_SUCCESS: [
      {
        guard: 'isMinimized',
        actions: { type: 'queueOutcome', params: { outcome: 'success' } },
      },
      { target: '.success' },
    ],
    RESPONSE_REFUSAL_CORPUS: [
      {
        guard: 'isMinimized',
        actions: { type: 'queueOutcome', params: { outcome: 'refusalOutOfCorpus' } },
      },
      { target: '.refusalOutOfCorpus' },
    ],
    RESPONSE_REFUSAL_PII: [
      {
        guard: 'isMinimized',
        actions: { type: 'queueOutcome', params: { outcome: 'refusalPII' } },
      },
      { target: '.refusalPII' },
    ],
    RESPONSE_ROUTING: [
      { guard: 'isMinimized' },
      { target: '.routing' },
    ],
    RESPONSE_ERROR: [
      {
        guard: 'isMinimized',
        actions: { type: 'queueOutcome', params: { outcome: 'error' } },
      },
      { target: '.error' },
    ],
    MODAL_OPENED: [
      { guard: ({ event }) => event.firstThisSession, target: '.greeting' },
      { target: '.idle' },
    ],
    MODAL_CLOSING: { target: '.goodbye' },
  },
  states: {
    idle: {
      entry: { type: 'rememberSettled', params: { state: 'idle' } },
      on: {
        INPUT_FOCUSED: 'listening',
        REQUEST_SUBMITTED: 'thinking',
      },
    },
    listening: {
      entry: { type: 'rememberSettled', params: { state: 'listening' } },
      on: {
        INPUT_BLURRED: 'idle',
        REQUEST_SUBMITTED: 'thinking',
      },
    },
    thinking: {
      entry: { type: 'rememberSettled', params: { state: 'thinking' } },
      on: {
        RETRIEVAL_STARTED: 'retrieving',
        GENERATION_STARTED: 'answering',
      },
    },
    retrieving: {
      entry: { type: 'rememberSettled', params: { state: 'retrieving' } },
      on: { GENERATION_STARTED: 'answering' },
    },
    answering: {
      entry: { type: 'rememberSettled', params: { state: 'answering' } },
    },
    success: {
      entry: { type: 'rememberSettled', params: { state: 'success' } },
      after: { successHold: 'idle' },
    },
    refusalOutOfCorpus: {
      entry: { type: 'rememberSettled', params: { state: 'refusalOutOfCorpus' } },
      after: { refusalSoftHold: 'idle' },
    },
    refusalPII: {
      entry: { type: 'rememberSettled', params: { state: 'refusalPII' } },
      after: { refusalPiiHold: 'idle' },
    },
    routing: {
      entry: { type: 'rememberSettled', params: { state: 'routing' } },
      after: { routingHold: 'idle' },
    },
    greeting: {
      entry: { type: 'rememberSettled', params: { state: 'greeting' } },
      after: { greetingHold: 'idle' },
    },
    goodbye: {
      after: { goodbyeHold: 'idle' },
    },
    error: {
      entry: { type: 'rememberSettled', params: { state: 'error' } },
      after: { errorHold: 'idle' },
    },
    dragging: {
      on: {
        DRAG_END: [
          {
            guard: ({ context }) => context.minimized !== 'none',
            target: 'minimized',
          },
          { target: 'idle' },
        ],
      },
    },
    minimized: {
      // No idle animation; Spline runtime is paused while in this state.
    },
    /**
     * Pseudo-state used by the dev debug panel; it transitions out
     * immediately to whichever state was forced via `DEV_FORCE`.
     */
    dynamic: {
      always: [
        { guard: ({ context }) => context.lastSettled === 'success', target: 'success' },
        { guard: ({ context }) => context.lastSettled === 'refusalOutOfCorpus', target: 'refusalOutOfCorpus' },
        { guard: ({ context }) => context.lastSettled === 'refusalPII', target: 'refusalPII' },
        { guard: ({ context }) => context.lastSettled === 'routing', target: 'routing' },
        { guard: ({ context }) => context.lastSettled === 'greeting', target: 'greeting' },
        { guard: ({ context }) => context.lastSettled === 'goodbye', target: 'goodbye' },
        { guard: ({ context }) => context.lastSettled === 'error', target: 'error' },
        { guard: ({ context }) => context.lastSettled === 'thinking', target: 'thinking' },
        { guard: ({ context }) => context.lastSettled === 'retrieving', target: 'retrieving' },
        { guard: ({ context }) => context.lastSettled === 'answering', target: 'answering' },
        { guard: ({ context }) => context.lastSettled === 'listening', target: 'listening' },
        { target: 'idle' },
      ],
    },
  },
})

export type AvatarSendFn = (event: AvatarEvent) => void

export type AvatarSnapshot = {
  state: AvatarStateName
  minimized: MinimizeMode
  queuedOutcome: QueuedOutcome
}

export type UseAvatarStateMachine = {
  snapshot: AvatarSnapshot
  send: AvatarSendFn
  isReducedMotion: boolean
}

const reducedMotionSubscribe = (cb: () => void): (() => void) => {
  if (typeof window === 'undefined' || !('matchMedia' in window)) {
    return () => undefined
  }
  const mql = window.matchMedia('(prefers-reduced-motion: reduce)')
  mql.addEventListener('change', cb)
  return () => mql.removeEventListener('change', cb)
}

const reducedMotionSnapshot = (): boolean => {
  if (typeof window === 'undefined' || !('matchMedia' in window)) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

const reducedMotionServerSnapshot = (): boolean => false

export function useAvatarStateMachine(): UseAvatarStateMachine {
  const isReducedMotion = useSyncExternalStore(
    reducedMotionSubscribe,
    reducedMotionSnapshot,
    reducedMotionServerSnapshot,
  )
  const [state, send] = useMachine(machine, { input: { reducedMotion: isReducedMotion } })

  // Push reduced-motion changes into the running machine so timer delays
  // shorten as soon as the OS preference flips (spec §9).
  useEffect(() => {
    send({ type: 'SET_REDUCED_MOTION', reducedMotion: isReducedMotion })
  }, [isReducedMotion, send])

  const snapshot = useMemo<AvatarSnapshot>(() => {
    const value = state.value
    const literal = (typeof value === 'string' ? value : 'idle') as AvatarStateName | 'dynamic'
    const safe: AvatarStateName = literal === 'dynamic' ? state.context.lastSettled : literal
    return {
      state: safe,
      minimized: state.context.minimized,
      queuedOutcome: state.context.queuedOutcome,
    }
  }, [state])

  return { snapshot, send, isReducedMotion }
}
