import { useState } from 'react'
import type { AvatarStateName } from './avatar.types'
import type { AvatarSendFn, AvatarSnapshot } from './useAvatarStateMachine'

/**
 * Dev-only panel exposing every avatar state for spec §10 acceptance check
 * #1. Mount only when `import.meta.env.DEV` is true; the host shell gates
 * this. No production styles, no analytics.
 */

const STATES: AvatarStateName[] = [
  'idle',
  'listening',
  'thinking',
  'retrieving',
  'answering',
  'success',
  'refusalOutOfCorpus',
  'refusalPII',
  'routing',
  'greeting',
  'goodbye',
  'error',
  'dragging',
  'minimized',
]

type AvatarDebugPanelProps = {
  send: AvatarSendFn
  snapshot: AvatarSnapshot
}

export function AvatarDebugPanel({ send, snapshot }: AvatarDebugPanelProps) {
  const [open, setOpen] = useState(false)
  if (!open) {
    return (
      <button
        type="button"
        className="avatar-debug-toggle"
        aria-label="Open avatar debug panel"
        onClick={() => setOpen(true)}
      >
        avatar:debug
      </button>
    )
  }
  return (
    <aside className="avatar-debug-panel" aria-label="Avatar debug panel">
      <header>
        <strong>avatar / {snapshot.state}</strong>
        <button type="button" className="avatar-debug-close" onClick={() => setOpen(false)}>
          close
        </button>
      </header>
      <p className="avatar-debug-hint">
        Force any of the 14 states; resolves back to idle on its hold timer.
      </p>
      <ul className="avatar-debug-grid">
        {STATES.map((state) => (
          <li key={state}>
            <button
              type="button"
              className={state === snapshot.state ? 'active' : ''}
              onClick={() => send({ type: 'DEV_FORCE', state })}
            >
              {state}
            </button>
          </li>
        ))}
      </ul>
      <div className="avatar-debug-meta">
        <div>
          minimized: <code>{snapshot.minimized}</code>
        </div>
        <div>
          queued: <code>{snapshot.queuedOutcome ?? 'none'}</code>
        </div>
      </div>
    </aside>
  )
}
