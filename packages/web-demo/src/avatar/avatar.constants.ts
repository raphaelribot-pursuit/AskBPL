import type { AvatarStateName } from './avatar.types'

export const STORAGE_KEYS = {
  position: 'askbpl.avatar.position',
  minimized: 'askbpl.avatar.minimized',
  greeted: 'askbpl.avatar.greeted',
} as const

export const STORAGE_KEY_PREFIX = 'askbpl.avatar.'

export const SCENE_PATH = '/scenes/askbpl-book.splinecode'

export const AVATAR_STATE_VARIABLE = 'avatarState'

export const SAFE_AREA_INSET_PX = 16

export const DEFAULT_INSET_PX = 24

export const DOCK_TAB_WIDTH_PX = 32

export const PILL_WIDTH_PX = 120

export const PLACEHOLDER_ACCENT = '#185FA5'

/**
 * Mapping from machine-state literal to the Spline state name that the
 * authored scene must expose. The scene contract is documented in
 * `scenes/README.md` and AskBPL_Avatar_Spec.md §8.
 */
export const SPLINE_STATE_NAMES: Record<AvatarStateName, string> = {
  idle: 'Idle',
  listening: 'Listening',
  thinking: 'Thinking',
  retrieving: 'Retrieving',
  answering: 'Answering',
  success: 'Success',
  refusalOutOfCorpus: 'RefusalSoft',
  refusalPII: 'RefusalAlert',
  routing: 'Routing',
  greeting: 'Greeting',
  goodbye: 'Goodbye',
  error: 'Error',
  dragging: 'Dragging',
  minimized: 'Minimized',
}

/**
 * Spec §4: how long each auto-resolving state should hold before returning
 * to `idle`. The state machine shortens these to ~40% when the OS reports
 * `prefers-reduced-motion: reduce` (spec §9).
 */
export const STATE_HOLD_MS = {
  success: 1200,
  refusalOutOfCorpus: 1500,
  refusalPII: 1200,
  routing: 1000,
  greeting: 2000,
  goodbye: 1000,
  error: 1500,
} as const

export const REDUCED_MOTION_MULTIPLIER = 0.4
