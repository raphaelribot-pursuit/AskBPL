import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import type { Application } from '@splinetool/runtime'
import {
  AVATAR_STATE_VARIABLE,
  PLACEHOLDER_ACCENT,
  SCENE_PATH,
  SPLINE_STATE_NAMES,
} from './avatar.constants'
import type { AvatarStateName } from './avatar.types'

/**
 * Loads the authored Spline scene and drives it from the avatar state
 * machine via `setVariable('avatarState', '<StateName>')` (spec §8). Pauses
 * rendering when minimized, resumes on restore. When the .splinecode asset
 * is missing or fails to load we fall back to a friendly SVG book so that
 * the build never blocks on art delivery.
 */

const Spline = lazy(() => import('@splinetool/react-spline'))

type AvatarSceneProps = {
  state: AvatarStateName
  paused: boolean
  reducedMotion: boolean
  /** Override the .splinecode URL. Defaults to {@link SCENE_PATH}. */
  scenePath?: string
}

type SceneStatus = 'probing' | 'loading' | 'ready' | 'fallback'

const probeSceneAvailability = async (path: string): Promise<boolean> => {
  if (typeof fetch === 'undefined') return false
  try {
    const res = await fetch(path, { method: 'HEAD', cache: 'no-store' })
    return res.ok
  } catch {
    return false
  }
}

export function AvatarScene({
  state,
  paused,
  reducedMotion,
  scenePath = SCENE_PATH,
}: AvatarSceneProps) {
  const [status, setStatus] = useState<SceneStatus>('probing')
  const appRef = useRef<Application | null>(null)

  useEffect(() => {
    let cancelled = false
    void probeSceneAvailability(scenePath).then((ok) => {
      if (cancelled) return
      setStatus(ok ? 'loading' : 'fallback')
    })
    return () => {
      cancelled = true
    }
  }, [scenePath])

  // Push state changes into the running Spline scene. The scene contract is
  // a `String` variable named `avatarState` (see scenes/README.md).
  useEffect(() => {
    const app = appRef.current
    if (!app || status !== 'ready') return
    try {
      app.setVariable(AVATAR_STATE_VARIABLE, SPLINE_STATE_NAMES[state])
    } catch {
      // Tolerate scenes that don't expose the variable yet.
    }
  }, [state, status])

  // Pause/resume rendering when the avatar is minimized (spec §8 budget).
  useEffect(() => {
    const app = appRef.current
    if (!app || status !== 'ready') return
    try {
      if (paused) app.stop()
      else app.play()
    } catch {
      // ignore
    }
  }, [paused, status])

  if (status === 'fallback') {
    return <FallbackBook state={state} reducedMotion={reducedMotion || paused} />
  }

  return (
    <div className="avatar-scene-canvas" aria-hidden="true">
      <Suspense fallback={<FallbackBook state={state} reducedMotion={true} />}>
        {status === 'loading' || status === 'ready' ? (
          <Spline
            scene={scenePath}
            onLoad={(app) => {
              appRef.current = app
              setStatus('ready')
              try {
                app.setVariable(AVATAR_STATE_VARIABLE, SPLINE_STATE_NAMES[state])
              } catch {
                // ignore
              }
            }}
            onError={() => setStatus('fallback')}
          />
        ) : (
          <FallbackBook state={state} reducedMotion={reducedMotion || paused} />
        )}
      </Suspense>
    </div>
  )
}

/**
 * Lightweight SVG stand-in that lives wherever the Spline scene would. It
 * communicates the current state via a label and a coarse expression swap
 * — enough to verify wiring before art lands.
 */
function FallbackBook({
  state,
  reducedMotion,
}: {
  state: AvatarStateName
  reducedMotion: boolean
}) {
  const expression = readableExpression(state)
  const animate = !reducedMotion && state !== 'minimized' && state !== 'goodbye'
  return (
    <div
      className={`avatar-fallback ${animate ? 'is-active' : 'is-static'}`}
      data-state={state}
      aria-hidden="true"
    >
      <svg viewBox="0 0 120 140" role="presentation" focusable={false}>
        <rect
          x={10}
          y={14}
          width={100}
          height={114}
          rx={10}
          fill={PLACEHOLDER_ACCENT}
          stroke="#000"
          strokeWidth={3}
        />
        <rect x={20} y={24} width={80} height={94} rx={6} fill="#fff" opacity={0.08} />
        <circle cx={45} cy={62} r={8} fill="#fff" />
        <circle cx={75} cy={62} r={8} fill="#fff" />
        <circle cx={45} cy={62} r={3.5} fill="#0a0a0a" />
        <circle cx={75} cy={62} r={3.5} fill="#0a0a0a" />
        <path
          d="M40 90 Q60 110 80 90"
          stroke="#0a0a0a"
          strokeWidth={3.5}
          fill="none"
          strokeLinecap="round"
        />
      </svg>
      <span className="avatar-fallback-label">{expression}</span>
    </div>
  )
}

function readableExpression(state: AvatarStateName): string {
  switch (state) {
    case 'idle':
      return 'idle'
    case 'listening':
      return 'listening…'
    case 'thinking':
      return 'thinking'
    case 'retrieving':
      return 'searching'
    case 'answering':
      return 'answering'
    case 'success':
      return 'got it'
    case 'refusalOutOfCorpus':
      return 'not in corpus'
    case 'refusalPII':
      return 'PII blocked'
    case 'routing':
      return 'routing'
    case 'greeting':
      return 'hello'
    case 'goodbye':
      return 'goodbye'
    case 'error':
      return 'something went wrong'
    case 'dragging':
      return 'whoa'
    case 'minimized':
      return 'paused'
  }
}
