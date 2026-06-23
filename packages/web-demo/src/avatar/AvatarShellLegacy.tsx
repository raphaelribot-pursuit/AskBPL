import type { CSSProperties, KeyboardEvent } from 'react'
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  apiSessionHeaders,
  clearStoredSessionId,
  getStoredSessionId,
  persistSessionIdFromResponse,
} from '../conversation/demoSession'
import { AvatarDebugPanel } from './AvatarDebugPanel'
import { AvatarEventsProvider, useAvatarEvents } from './AvatarEventsContext'
import {
  DOCK_TAB_WIDTH_PX,
  PILL_WIDTH_PX,
  SAFE_AREA_INSET_PX,
  STORAGE_KEYS,
  STORAGE_KEY_PREFIX,
} from './avatar.constants'
import type { AvatarPosition } from './avatar.types'
import { useAvatarDrag } from './useAvatarDrag'
import { useAvatarMinimize } from './useAvatarMinimize'
import { useAvatarStateMachine, type AvatarSnapshot } from './useAvatarStateMachine'
import { TranscriptList } from '../conversation/TranscriptList'
import type {
  AssistantAnswerRow,
  AssistantRefusalRow,
  CitationPayload,
  ErrorGenericRow,
  PiiBannerRow,
  TranscriptRow,
} from '../conversation/types'
import { rowFromAskResponse } from '../conversation/types'

const AskBPLAvatarLazy = lazy(() =>
  import('./AskBPLAvatar').then((m) => ({ default: m.AskBPLAvatar })),
)

/**
 * Legacy draggable Spline-capable avatar shell. This is the previous
 * `AskPilotShell` implementation, preserved verbatim and gated behind
 * `VITE_ENABLE_AVATAR_SHELL=true`. The default surface is now the wireframe
 * v3 modal in `components/pilot/WireframeShell.tsx`.
 *
 * Rendering faces (unchanged from before):
 *   - closed         → bottom-right book FAB
 *   - open + normal  → positioned modal at the persisted drag coords
 *   - open + minimized → pill (default) or edge dock per Avatar spec §7
 *
 * 3D `AskBPLAvatar` loads only when `VITE_ENABLE_SPLINE=true`; otherwise
 * the toolbar uses `BookAvatarLite` (same as `VITE_LITE_DEMO`) so WebGL
 * never runs in pilot builds.
 */

const SAMPLE_PROMPT =
  'Summarize gift acceptance prerequisites and who must approve unusually large pledges.'

type ShellSize = { width: number; height: number }

const SHELL_DEFAULT_SIZE: ShellSize = { width: 480, height: 640 }
const PILL_SIZE: ShellSize = { width: PILL_WIDTH_PX, height: 56 }
const DOCK_SIZE: ShellSize = { width: DOCK_TAB_WIDTH_PX, height: 132 }

const FIRST_OPEN_KEY = STORAGE_KEYS.greeted

let __rowSeq = 0
function nextRowId(): string {
  __rowSeq += 1
  return `row-${Date.now().toString(36)}-${__rowSeq}`
}

function BookAvatarLite(props: {
  snapshot: AvatarSnapshot
  reducedMotion: boolean
  size?: 'thumb' | 'standard' | 'pill'
  paused?: boolean
}) {
  const { snapshot, size = 'standard' } = props
  const sizeClass =
    size === 'pill'
      ? 'avatar-face pill'
      : size === 'thumb'
        ? 'avatar-face thumb'
        : 'avatar-face standard'
  return (
    <div className={sizeClass} data-state={snapshot.state}>
      <span className="book-lite-glyph" role="img" aria-hidden="true">
        📖
      </span>
    </div>
  )
}

function DynamicAvatar(props: {
  snapshot: AvatarSnapshot
  reducedMotion: boolean
  size?: 'thumb' | 'standard' | 'pill'
  paused?: boolean
}) {
  const liteDemo = import.meta.env.VITE_LITE_DEMO === 'true'
  const splineEnabled = import.meta.env.VITE_ENABLE_SPLINE === 'true'
  if (liteDemo || !splineEnabled) {
    return <BookAvatarLite {...props} />
  }
  return (
    <Suspense fallback={<BookAvatarLite {...props} />}>
      <AskBPLAvatarLazy {...props} />
    </Suspense>
  )
}

const wasGreetedThisSession = (): boolean => {
  if (typeof window === 'undefined') return false
  try {
    return window.sessionStorage.getItem(FIRST_OPEN_KEY) === '1'
  } catch {
    return false
  }
}

const markGreeted = (): void => {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(FIRST_OPEN_KEY, '1')
  } catch {
    /* ignore */
  }
}

const clearAvatarSessionState = (): void => {
  if (typeof window === 'undefined') return
  try {
    const keys: string[] = []
    for (let i = 0; i < window.sessionStorage.length; i += 1) {
      const key = window.sessionStorage.key(i)
      if (key && key.startsWith(STORAGE_KEY_PREFIX)) keys.push(key)
    }
    keys.forEach((k) => window.sessionStorage.removeItem(k))
  } catch {
    /* ignore */
  }
}

export type AvatarShellLegacyProps = {
  apiBase: string
  docsBase: string
}

export function AvatarShellLegacy({ apiBase, docsBase }: AvatarShellLegacyProps) {
  const { snapshot, send, isReducedMotion } = useAvatarStateMachine()
  const [open, setOpen] = useState(false)

  const minimize = useAvatarMinimize({ send })

  const shellRef = useRef<HTMLDivElement | null>(null)
  const [shellSize, setShellSize] = useState(SHELL_DEFAULT_SIZE)

  useLayoutEffect(() => {
    if (!shellRef.current || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      const { width, height } = entry.contentRect
      if (width > 0 && height > 0) {
        setShellSize({ width: Math.round(width), height: Math.round(height) })
      }
    })
    ro.observe(shellRef.current)
    return () => ro.disconnect()
  }, [open, minimize.mode])

  const draggableSize = useMemo(() => {
    if (minimize.mode === 'pill') return PILL_SIZE
    if (minimize.mode === 'dock') return DOCK_SIZE
    return shellSize
  }, [minimize.mode, shellSize])

  const drag = useAvatarDrag({
    send,
    shellSize: draggableSize,
    disabled: minimize.mode === 'dock',
  })

  const shellPosition: AvatarPosition = useMemo(() => {
    if (minimize.mode !== 'dock') return drag.position
    if (typeof window === 'undefined') return drag.position
    return {
      x: window.innerWidth - DOCK_SIZE.width - SAFE_AREA_INSET_PX,
      y: Math.max(SAFE_AREA_INSET_PX, drag.position.y),
    }
  }, [drag.position, minimize.mode])

  const handleOpen = useCallback(() => {
    const firstThisSession = !wasGreetedThisSession()
    setOpen(true)
    markGreeted()
    send({ type: 'MODAL_OPENED', firstThisSession })
  }, [send])

  const handleClose = useCallback(() => {
    send({ type: 'MODAL_CLOSING' })
    setOpen(false)
    if (minimize.mode !== 'none') minimize.restore()
  }, [minimize, send])

  useEffect(() => {
    if (!open || typeof window === 'undefined') return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        if (minimize.mode === 'none') minimize.minimizeTo('pill')
        else handleClose()
        return
      }
      if (!event.altKey) return
      switch (event.key) {
        case 'ArrowUp':
          event.preventDefault()
          drag.nudge(0, -10)
          break
        case 'ArrowDown':
          event.preventDefault()
          drag.nudge(0, 10)
          break
        case 'ArrowLeft':
          event.preventDefault()
          drag.nudge(-10, 0)
          break
        case 'ArrowRight':
          event.preventDefault()
          drag.nudge(10, 0)
          break
        default:
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drag, handleClose, minimize, open])

  if (!open) {
    return (
      <button
        type="button"
        aria-label="Open Ask BPL"
        title="Ask BPL"
        className="fab-book"
        onClick={handleOpen}
      >
        <BookGlyph />
      </button>
    )
  }

  const baseStyle: CSSProperties = {
    position: 'fixed',
    left: `${shellPosition.x}px`,
    top: `${shellPosition.y}px`,
    margin: 0,
    inset: 'auto',
  }

  if (minimize.mode !== 'none') {
    const isPill = minimize.mode === 'pill'
    const dotVisible = snapshot.queuedOutcome !== null
    return (
      <AvatarEventsProvider emit={send}>
        <div
          ref={shellRef}
          className={`avatar-min-shell ${isPill ? 'pill' : 'dock'}`}
          style={baseStyle}
          aria-label="Ask BPL minimized"
        >
          <button
            type="button"
            className="avatar-min-restore"
            onClick={() => minimize.restore()}
            aria-label={
              dotVisible
                ? `Restore Ask BPL — new ${snapshot.queuedOutcome ?? 'response'}`
                : 'Restore Ask BPL'
            }
            {...(isPill ? drag.bind() : {})}
            style={
              isPill
                ? { touchAction: 'none', cursor: drag.isDragging ? 'grabbing' : 'grab' }
                : undefined
            }
          >
            <DynamicAvatar
              snapshot={snapshot}
              reducedMotion={isReducedMotion}
              size={isPill ? 'pill' : 'thumb'}
              paused
            />
            {isPill ? <span className="avatar-min-label">Ask BPL</span> : null}
            {dotVisible ? <span className="avatar-min-dot" aria-hidden="true" /> : null}
          </button>
        </div>
        {import.meta.env.DEV ? <AvatarDebugPanel send={send} snapshot={snapshot} /> : null}
      </AvatarEventsProvider>
    )
  }

  return (
    <AvatarEventsProvider emit={send}>
      <div
        ref={shellRef}
        className="modal-shell brutal-card open avatar-positioned"
        style={baseStyle}
        role="dialog"
        aria-modal="false"
        aria-label="Ask BPL"
      >
        <header className="modal-toolbar avatar-toolbar">
          <button
            type="button"
            className="avatar-handle"
            aria-label="Drag Ask BPL window"
            {...drag.bind()}
            style={{ touchAction: 'none', cursor: drag.isDragging ? 'grabbing' : 'grab' }}
          >
            <DynamicAvatar
              snapshot={snapshot}
              reducedMotion={isReducedMotion}
              size="standard"
            />
          </button>
          <div className="avatar-toolbar-meta">
            <strong>Ask BPL</strong>
            <p className="muted small">JWT kept in-memory for this demo tab.</p>
          </div>
          <div className="avatar-toolbar-actions">
            <button
              type="button"
              className="ghost"
              aria-label="Minimize Ask BPL"
              onClick={() => minimize.minimizeTo('pill')}
            >
              ▾
            </button>
            <button
              type="button"
              className="ghost"
              aria-label="Dock Ask BPL to edge"
              onClick={() => minimize.minimizeTo('dock')}
            >
              ◧
            </button>
            <button type="button" className="ghost" onClick={handleClose}>
              Close
            </button>
          </div>
        </header>
        <div className="modal-shell-body">
          <ShellBody apiBase={apiBase} docsBase={docsBase} />
        </div>
      </div>
      {import.meta.env.DEV ? <AvatarDebugPanel send={send} snapshot={snapshot} /> : null}
    </AvatarEventsProvider>
  )
}

/**
 * Authenticated chat surface used by the legacy avatar shell. Keeps its
 * own request lifecycle (separate from `useAskChat`) so the avatar state
 * machine can keep emitting fine-grained beats — `RETRIEVAL_STARTED`,
 * `GENERATION_STARTED`, etc. — without polluting the wireframe shell.
 */
function ShellBody({ apiBase, docsBase }: { apiBase: string; docsBase: string }) {
  const emit = useAvatarEvents()

  const [composer, setComposer] = useState('')
  const [rows, setRows] = useState<TranscriptRow[]>([])
  const [showSamplePrompt, setShowSamplePrompt] = useState(true)
  const [sending, setSending] = useState(false)

  const [feedbackAnonymousGlobal, setFeedbackAnonymousGlobal] = useState(false)
  const [feedbackStatus, setFeedbackStatus] = useState<string>('')

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const liveRegionMessage = useLastAssistantSummary(rows)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [rows, sending])

  const handleClearChat = useCallback(() => {
    clearStoredSessionId()
    setRows([])
    setComposer('')
    setShowSamplePrompt(true)
    setFeedbackStatus('')
    clearAvatarSessionState()
  }, [])

  async function sendQuestion(textRaw: string) {
    const text = textRaw.trim()
    if (!text || sending) return

    setSending(true)
    setFeedbackStatus('')
    if (showSamplePrompt) setShowSamplePrompt(false)

    setRows((history) => [...history, { kind: 'user_message', id: nextRowId(), body: text }])
    setComposer('')

    emit({ type: 'REQUEST_SUBMITTED' })

    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    let retrievalTimer: number | undefined
    let generationTimer: number | undefined
    if (!reduced) {
      retrievalTimer = window.setTimeout(() => emit({ type: 'RETRIEVAL_STARTED' }), 80)
      generationTimer = window.setTimeout(() => emit({ type: 'GENERATION_STARTED' }), 220)
    } else {
      emit({ type: 'GENERATION_STARTED' })
    }

    const sessionId = getStoredSessionId()

    let res: Response
    try {
      res = await fetch(`${apiBase}/questions/ask`, {
        method: 'POST',
        headers: apiSessionHeaders(sessionId),
        body: JSON.stringify({ question: text }),
      })
      persistSessionIdFromResponse(res)
    } catch {
      window.clearTimeout(retrievalTimer)
      window.clearTimeout(generationTimer)
      emit({ type: 'RESPONSE_ERROR' })
      setRows((history) => [
        ...history,
        {
          kind: 'error_generic',
          id: nextRowId(),
          message: 'Network error. Please try again.',
        },
      ])
      setSending(false)
      return
    }

    window.clearTimeout(retrievalTimer)
    window.clearTimeout(generationTimer)

    let payload: Record<string, unknown>
    try {
      payload = (await res.json()) as Record<string, unknown>
    } catch {
      payload = {}
    }

    if (res.status === 401 || res.status === 403) {
      emit({ type: 'RESPONSE_ERROR' })
      clearStoredSessionId()
      setFeedbackStatus('Session expired. Send your question again.')
      setSending(false)
      return
    }

    const row = rowFromAskResponse({ status: res.status, payload, id: nextRowId() })
    setRows((history) => [...history, row])
    emitAvatarBeatFor(emit, row)
    setSending(false)
  }

  async function submitFeedback(reqId: string, rating: 'helpful' | 'not_helpful') {
    setFeedbackStatus('')
    const res = await fetch(`${apiBase}/feedback/`, {
      method: 'POST',
      headers: apiSessionHeaders(getStoredSessionId()),
      body: JSON.stringify({
        request_id: reqId,
        rating,
        anonymous_override: feedbackAnonymousGlobal,
      }),
    })
    persistSessionIdFromResponse(res)
    const bodyText = await res.text()
    setFeedbackStatus(
      res.ok ? `Recorded ${rating.replace('_', ' ')}` : `${res.status}: ${bodyText}`,
    )
  }

  function openCitation(c: CitationPayload) {
    if (!docsBase) {
      setFeedbackStatus(
        'Set VITE_DOCUMENTS_PUBLIC_BASE or server DOCUMENTS_PUBLIC_BASE_URL for citation links.',
      )
      return
    }
    window.open(`${docsBase}/${c.document_id}`, '_blank', 'noopener,noreferrer')
  }

  const handleComposerSubmit = () => sendQuestion(composer)

  const handleComposerKeys = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleComposerSubmit()
    }
  }

  return (
    <div className="chat-shell">
      <div className="modal-toolbar skinny">
        <span className="pill success">authenticated</span>
        <button type="button" className="ghost" onClick={handleClearChat}>
          Clear chat
        </button>
      </div>

      {showSamplePrompt && (
        <div className="sample-card">
          <p className="sample-label">Suggested pilot prompt</p>
          <blockquote>{SAMPLE_PROMPT}</blockquote>
          <button
            type="button"
            className="secondary"
            onClick={() => sendQuestion(SAMPLE_PROMPT)}
          >
            Try sample prompt
          </button>
        </div>
      )}

      <div ref={scrollRef} className="history brutal-scroll" role="log" aria-live="polite">
        <TranscriptList
          rows={rows}
          pending={sending}
          onFeedback={submitFeedback}
          onOpenCitation={openCitation}
        />
      </div>

      <div className="composer brutal-border">
        <textarea
          className="composer-input"
          rows={3}
          placeholder="Ask a closed-corpus policy question…"
          value={composer}
          onChange={(e) => setComposer(e.target.value)}
          onKeyDown={handleComposerKeys}
          onFocus={() => emit({ type: 'INPUT_FOCUSED' })}
          onBlur={() => emit({ type: 'INPUT_BLURRED' })}
          disabled={sending}
          aria-disabled={sending}
        />

        <div className="composer-actions">
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={feedbackAnonymousGlobal}
              onChange={(event) => setFeedbackAnonymousGlobal(event.target.checked)}
            />
            Anonymous feedback payloads (no tester linkage flag)
          </label>
          <button
            type="button"
            className="primary"
            disabled={sending || !composer.trim()}
            onClick={handleComposerSubmit}
          >
            {sending ? 'Sending…' : 'Ask'}
          </button>
        </div>
      </div>
      {feedbackStatus && (
        <p className="status-line muted" role="status">
          {feedbackStatus}
        </p>
      )}
      <div className="sr-only" aria-live="polite">
        {liveRegionMessage}
      </div>
    </div>
  )
}

function emitAvatarBeatFor(
  emit: ReturnType<typeof useAvatarEvents>,
  row: AssistantAnswerRow | AssistantRefusalRow | PiiBannerRow | ErrorGenericRow,
) {
  switch (row.kind) {
    case 'assistant_answer':
      emit({ type: 'RESPONSE_SUCCESS' })
      return
    case 'assistant_refusal':
      emit({ type: 'RESPONSE_REFUSAL_CORPUS' })
      return
    case 'pii_banner':
      emit({ type: 'RESPONSE_REFUSAL_PII' })
      return
    case 'error_generic':
      emit({ type: 'RESPONSE_ERROR' })
      return
  }
}

function useLastAssistantSummary(rows: TranscriptRow[]): string {
  return useMemo(() => {
    for (let i = rows.length - 1; i >= 0; i -= 1) {
      const row = rows[i]
      switch (row.kind) {
        case 'assistant_answer':
          return 'Answer ready.'
        case 'assistant_refusal':
          return 'Out of corpus; routing suggestions available.'
        case 'pii_banner':
          return 'Question blocked for privacy.'
        case 'error_generic':
          return `Error: ${row.message}`
        default:
          continue
      }
    }
    return ''
  }, [rows])
}

function BookGlyph() {
  return (
    <svg aria-hidden focusable={false} viewBox="0 0 72 92" role="presentation">
      <rect x={6} y={8} width={60} height={76} rx={4} fill="currentColor" />
      <rect x={12} y={16} width={22} height={60} rx={2} fill="var(--accent)" opacity={0.8} />
      <rect x={38} y={18} width={22} height={8} rx={2} fill="var(--accent)" opacity={0.95} />
      <rect x={38} y={30} width={22} height={44} rx={2} fill="var(--surface)" />
    </svg>
  )
}

export { BookGlyph }
