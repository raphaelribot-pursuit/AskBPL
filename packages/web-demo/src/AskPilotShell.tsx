import type { CSSProperties, FormEvent, KeyboardEvent } from 'react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { AskBPLAvatar } from './avatar/AskBPLAvatar'
import { AvatarDebugPanel } from './avatar/AvatarDebugPanel'
import { AvatarEventsProvider, useAvatarEvents } from './avatar/AvatarEventsContext'
import {
  DEFAULT_INSET_PX,
  DOCK_TAB_WIDTH_PX,
  PILL_WIDTH_PX,
  SAFE_AREA_INSET_PX,
  STORAGE_KEYS,
  STORAGE_KEY_PREFIX,
} from './avatar/avatar.constants'
import type { AvatarPosition } from './avatar/avatar.types'
import { useAvatarDrag } from './avatar/useAvatarDrag'
import { useAvatarMinimize } from './avatar/useAvatarMinimize'
import { useAvatarStateMachine } from './avatar/useAvatarStateMachine'

/**
 * Floating "Ask BPL" pilot shell. Owns the request lifecycle previously
 * inlined in App.tsx, wires it into the avatar state machine
 * (`AskBPL_Avatar_Spec.md` §5), and renders three faces:
 *
 *  - closed → bottom-right book FAB (unchanged from before)
 *  - open + normal → positioned modal anchored at the persisted coords
 *  - open + minimized → pill (default) or edge dock per spec §7
 */

const SAMPLE_PROMPT =
  'Summarize gift acceptance prerequisites and who must approve unusually large pledges.'

export type AttributionMode = 'attributed' | 'anonymous'

export type CitationPayload = {
  chunk_id: string
  document_id: string
  document_title?: string
  section_heading?: string | null
}

export type RoutingPayload = {
  team: string
  contact_hint: string
  team_id: string
}

export type ChatTurn =
  | { role: 'user'; body: string }
  | {
      role: 'assistant'
      requestId?: string
      responseType?: string
      answer?: string | null
      refusalExplanation?: string | null
      inferredPolicy?: string | null
      routing?: RoutingPayload[]
      citations?: CitationPayload[]
      error?: string
    }

export type AskPilotShellProps = {
  apiBase: string
  docsBase: string
}

type ShellSize = { width: number; height: number }

const SHELL_DEFAULT_SIZE: ShellSize = { width: 480, height: 640 }
const PILL_SIZE: ShellSize = { width: PILL_WIDTH_PX, height: 56 }
const DOCK_SIZE: ShellSize = { width: DOCK_TAB_WIDTH_PX, height: 132 }

const FIRST_OPEN_KEY = STORAGE_KEYS.greeted

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
    // ignore
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
    // ignore
  }
}

export function AskPilotShell({ apiBase, docsBase }: AskPilotShellProps) {
  const { snapshot, send, isReducedMotion } = useAvatarStateMachine()
  const [open, setOpen] = useState(false)

  const minimize = useAvatarMinimize({ send })

  // The shell measures itself so the drag clamp matches the live element.
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

  // Drag clamps against the live shell size; switches to pill/dock sizes when
  // minimized so the small chrome can sit comfortably anywhere onscreen.
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

  // Compute fixed top/left for the rendered shell, with a special edge-snap
  // for `dock` mode (always flush to the right edge per spec §7b).
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

  // Keyboard nudges + Esc-to-minimize (spec §9). Only active while open.
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

  // FAB: closed face. Same visual identity as before.
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

  // Minimized: pill or dock. Clicking restores; the avatar continues to drive
  // its `Minimized` state which keeps the Spline runtime paused.
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
            // Allow drag to start from the restore surface in pill mode.
            {...(isPill ? drag.bind() : {})}
            style={
              isPill
                ? { touchAction: 'none', cursor: drag.isDragging ? 'grabbing' : 'grab' }
                : undefined
            }
          >
            <AskBPLAvatar
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

  // Open + normal. The avatar lives on the toolbar drag handle.
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
            <AskBPLAvatar
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
        <ShellBody apiBase={apiBase} docsBase={docsBase} />
      </div>
      {import.meta.env.DEV ? <AvatarDebugPanel send={send} snapshot={snapshot} /> : null}
    </AvatarEventsProvider>
  )
}

/**
 * The actual sign-in / chat surface. Pulled into its own component so it
 * can read the avatar event bus via context without prop-drilling.
 */
function ShellBody({ apiBase, docsBase }: { apiBase: string; docsBase: string }) {
  const emit = useAvatarEvents()
  const [email, setEmail] = useState('pilot-demo@bklynlibrary.org')
  const [accessCode, setAccessCode] = useState('DEMO2026')
  const [attribution, setAttribution] = useState<AttributionMode>('attributed')
  const [token, setToken] = useState<string | null>(null)

  const [composer, setComposer] = useState('')
  const [thread, setThread] = useState<ChatTurn[]>([])
  const [showSamplePrompt, setShowSamplePrompt] = useState(true)
  const [sending, setSending] = useState(false)

  const [feedbackAnonymousGlobal, setFeedbackAnonymousGlobal] = useState(false)
  const [feedbackStatus, setFeedbackStatus] = useState<string>('')

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const liveRegionMessage = useLastAssistantSummary(thread)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [thread])

  function signOut() {
    setToken(null)
    setThread([])
    setComposer('')
    setShowSamplePrompt(true)
    setFeedbackStatus('')
    clearAvatarSessionState()
  }

  async function handleSignIn(e: FormEvent) {
    e.preventDefault()
    setFeedbackStatus('')
    const res = await fetch(`${apiBase}/auth/sign-in`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email.trim(),
        access_code: accessCode.trim(),
        attribution_mode: attribution,
        user_agent: navigator.userAgent?.slice(0, 240),
      }),
    })
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>
    if (!res.ok) {
      setFeedbackStatus(
        `Sign-in failed: ${typeof body.detail === 'string' ? body.detail : res.status}`,
      )
      return
    }
    setToken(String(body.token ?? ''))
  }

  async function sendQuestion(textRaw: string) {
    const text = textRaw.trim()
    if (!text || sending) return
    if (!token) {
      setFeedbackStatus('Session missing. Sign in again.')
      return
    }

    setSending(true)
    setFeedbackStatus('')
    if (showSamplePrompt) setShowSamplePrompt(false)

    setThread((history) => [...history, { role: 'user', body: text }])
    setComposer('')

    emit({ type: 'REQUEST_SUBMITTED' })

    // Synthesize a brief retrieval window before generation so the avatar
    // surfaces the "searching" beat. Skip the pause under reduced motion so
    // we don't introduce latency for accessibility users (spec §9).
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

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    }

    let res: Response
    try {
      res = await fetch(`${apiBase}/questions/ask`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ question: text }),
      })
    } catch {
      window.clearTimeout(retrievalTimer)
      window.clearTimeout(generationTimer)
      emit({ type: 'RESPONSE_ERROR' })
      setThread((history) => [
        ...history,
        { role: 'assistant', error: 'Network error. Please try again.' },
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

    const requestId = typeof payload.request_id === 'string' ? payload.request_id : undefined

    if (res.status === 401 || res.status === 403) {
      emit({ type: 'RESPONSE_ERROR' })
      signOut()
      setSending(false)
      setThread((history) => [
        ...history,
        { role: 'assistant', error: 'Session expired. Sign in again.' },
      ])
      return
    }

    if (!res.ok) {
      const piiCats = payload.pii_categories
      let reason = `${res.status}`
      if (payload.type === 'error_pii' && Array.isArray(piiCats)) {
        reason = `Question blocked (${(piiCats as string[]).join(', ') || 'possible PII'})`
        emit({ type: 'RESPONSE_REFUSAL_PII' })
      } else {
        emit({ type: 'RESPONSE_ERROR' })
      }
      const assistantTurn: ChatTurn = {
        role: 'assistant',
        requestId,
        responseType: typeof payload.type === 'string' ? payload.type : 'error',
        error: typeof payload.detail === 'string' ? payload.detail : reason,
        refusalExplanation:
          typeof payload.refusal_explanation === 'string' ? payload.refusal_explanation : null,
        citations: [],
        routing: [],
      }
      setThread((history) => [...history, assistantTurn])
      setSending(false)
      return
    }

    const routing = Array.isArray(payload.routing) ? (payload.routing as RoutingPayload[]) : []
    const citations = Array.isArray(payload.citations)
      ? (payload.citations as CitationPayload[])
      : []
    const responseType = typeof payload.type === 'string' ? payload.type : ''

    const assistantTurn: ChatTurn = {
      role: 'assistant',
      requestId,
      responseType,
      answer: typeof payload.answer === 'string' ? payload.answer : null,
      refusalExplanation:
        typeof payload.refusal_explanation === 'string' ? payload.refusal_explanation : null,
      inferredPolicy:
        typeof payload.inferred_policy_type === 'string' ? payload.inferred_policy_type : null,
      citations,
      routing,
    }

    setThread((history) => [...history, assistantTurn])

    // Map orchestrator response shape onto avatar outcomes (spec §5).
    if (responseType === 'answer') {
      emit({ type: 'RESPONSE_SUCCESS' })
    } else if (responseType === 'error_pii') {
      emit({ type: 'RESPONSE_REFUSAL_PII' })
    } else if (responseType) {
      emit({ type: 'RESPONSE_REFUSAL_CORPUS' })
    } else {
      emit({ type: 'RESPONSE_ERROR' })
    }
    // RESPONSE_ROUTING is emitted from <RoutingDeck /> on mount so the avatar
    // beat is tied to the visible routing surface (spec §5 / plan).

    setSending(false)
  }

  async function submitFeedback(reqId: string, rating: 'helpful' | 'not_helpful') {
    setFeedbackStatus('')
    const res = await fetch(`${apiBase}/feedback/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: reqId,
        rating,
        anonymous_override: feedbackAnonymousGlobal,
      }),
    })
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

  if (!token) {
    return (
      <form className="signin-form brutal-stack" onSubmit={handleSignIn}>
        <p className="binding-note">
          Attribution mode is binding for this signing session (<code>attributed</code> stores your
          question verbatim; <code>anonymous</code> stores only a hash server-side).
        </p>

        <label htmlFor="si-email">Email</label>
        <input
          id="si-email"
          autoComplete="email"
          className="brutal-input"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label htmlFor="si-pass">Access code</label>
        <input
          id="si-pass"
          autoComplete="off"
          className="brutal-input"
          type="password"
          value={accessCode}
          onChange={(e) => setAccessCode(e.target.value)}
        />

        <fieldset className="brutal-fieldset">
          <legend className="sr-only">Attribution modes</legend>
          <label className="radio-line">
            <input
              type="radio"
              name="attrib"
              value="attributed"
              checked={attribution === 'attributed'}
              onChange={() => setAttribution('attributed')}
            />
            attributed (question retained)
          </label>
          <label className="radio-line">
            <input
              type="radio"
              name="attrib"
              value="anonymous"
              checked={attribution === 'anonymous'}
              onChange={() => setAttribution('anonymous')}
            />
            anonymous (hash only server-side per ERD §4)
          </label>
        </fieldset>

        <button className="primary" type="submit">
          Continue
        </button>
        {feedbackStatus && <div className="status-line muted">{feedbackStatus}</div>}
      </form>
    )
  }

  return (
    <div className="chat-shell">
      <div className="modal-toolbar skinny">
        <span className="pill success">authenticated</span>
        <button type="button" className="ghost" onClick={() => signOut()}>
          Sign out
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

      <div ref={scrollRef} className="history brutal-scroll">
        {thread.map((turn, idx) =>
          turn.role === 'user' ? (
            <div key={`u-${idx}`} className="bubble user brutal-border">
              {turn.body}
            </div>
          ) : (
            <AssistantTurn
              key={`a-${idx}`}
              turn={turn}
              onFeedback={submitFeedback}
              onOpenCitation={openCitation}
            />
          ),
        )}
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

/**
 * Derives a short, human-friendly announcement for the screen-reader live
 * region from the most recent assistant turn (spec §9 — the avatar must
 * never be the sole signal).
 */
function useLastAssistantSummary(thread: ChatTurn[]): string {
  return useMemo(() => {
    for (let i = thread.length - 1; i >= 0; i -= 1) {
      const turn = thread[i]
      if (turn.role !== 'assistant') continue
      if (turn.error) return `Error: ${turn.error}`
      if (turn.responseType === 'answer') return 'Answer ready.'
      if (turn.responseType === 'error_pii') return 'Question blocked for privacy.'
      if (turn.responseType) return 'Out of corpus; routing suggestions available.'
      return 'Response received.'
    }
    return ''
  }, [thread])
}

function AssistantTurn({
  turn,
  onFeedback,
  onOpenCitation,
}: {
  turn: Extract<ChatTurn, { role: 'assistant' }>
  onFeedback: (rid: string, rating: 'helpful' | 'not_helpful') => void
  onOpenCitation: (citation: CitationPayload) => void
}) {
  const isRefusal = turn.responseType && turn.responseType !== 'answer'

  return (
    <article className="bubble assistant brutal-border">
      <div className="assistant-head">
        <span className="pill subtle">{(turn.responseType ?? 'response').replace(/_/g, ' ')}</span>
        <span className="mono-muted">
          {turn.requestId ? turn.requestId.slice(0, 13) : 'pending'}
        </span>
      </div>
      {turn.error && (
        <>
          <p className="error-text">{turn.error}</p>
          {(turn.routing?.length ?? 0) > 0 && (
            <RoutingDeck teams={turn.routing ?? []} isRefusal={Boolean(isRefusal)} />
          )}
        </>
      )}

      {!turn.error && isRefusal && (
        <>
          <p>
            {turn.refusalExplanation ??
              (String(turn.answer ?? '').trim() || 'Blocked response.')}
          </p>
          {(turn.routing?.length ?? 0) > 0 ? (
            <RoutingDeck teams={turn.routing ?? []} isRefusal />
          ) : (
            <p className="muted">
              Routing teams were not surfaced for this turn (inspect orchestrator routing tables).
            </p>
          )}
        </>
      )}
      {!turn.error && turn.responseType === 'answer' && (
        <>
          <p className="answer-body">{turn.answer}</p>

          {(turn.routing?.length ?? 0) > 0 ? (
            <RoutingDeck teams={turn.routing ?? []} isRefusal={false} />
          ) : null}

          {(turn.citations ?? []).length > 0 ? (
            <div className="citation-pane">
              <p className="panel-title">Citations</p>
              <div className="citation-chip-row">
                {(turn.citations ?? []).map((citation, index) => (
                  <button
                    key={`${citation.chunk_id}-${index}`}
                    type="button"
                    className="citation-chip"
                    onClick={() => onOpenCitation(citation)}
                  >
                    {citation.document_title ?? 'Document'}
                    {citation.section_heading ? ` · ${citation.section_heading}` : ''}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="muted">No citations were returned for this turn.</p>
          )}
        </>
      )}
      {turn.requestId && (
        <div className="feedback-row">
          <button
            type="button"
            className="secondary slim"
            onClick={() => onFeedback(turn.requestId!, 'helpful')}
          >
            Helpful
          </button>
          <button
            type="button"
            className="secondary slim"
            onClick={() => onFeedback(turn.requestId!, 'not_helpful')}
          >
            Not helpful
          </button>
        </div>
      )}
    </article>
  )
}

function RoutingDeck({ teams, isRefusal }: { teams: RoutingPayload[]; isRefusal: boolean }) {
  // Surfacing the deck is itself a routing event for the avatar machine.
  const emit = useAvatarEvents()
  useEffect(() => {
    if (teams.length === 0) return
    emit({ type: 'RESPONSE_ROUTING' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teams.length])
  return (
    <div className={`routing-pane ${isRefusal ? 'refusal' : 'normal'}`}>
      <div className="panel-title">{isRefusal ? 'Suggested routing contacts' : 'Routing context'}</div>
      <ul className="routing-list brutal-scroll">
        {teams.map((team) => (
          <li key={team.team_id} className="routing-card brutal-border">
            <strong>{team.team}</strong>
            <p>{team.contact_hint}</p>
          </li>
        ))}
      </ul>
    </div>
  )
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

// Re-exported so the dev panel and tests can render the FAB glyph standalone.
export { BookGlyph }

// `DEFAULT_INSET_PX` is re-exported to silence unused warnings when the
// caller wants to mirror the pre-drag layout in static documentation.
export { DEFAULT_INSET_PX }
