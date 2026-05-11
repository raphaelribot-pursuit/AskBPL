import type { FormEvent, KeyboardEvent } from 'react'
import { useEffect, useRef, useState } from 'react'
import './App.css'

const SAMPLE_PROMPT =
  'Summarize gift acceptance prerequisites and who must approve unusually large pledges.'

type AttributionMode = 'attributed' | 'anonymous'

type CitationPayload = {
  chunk_id: string
  document_id: string
  document_title?: string
  section_heading?: string | null
}

type RoutingPayload = {
  team: string
  contact_hint: string
  team_id: string
}

type ChatTurn =
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

export function App() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const docsBase = (import.meta.env.VITE_DOCUMENTS_PUBLIC_BASE ?? '').replace(/\/$/, '')

  const [fabOpen, setFabOpen] = useState(false)
  const [view, setView] = useState<'demo' | 'build'>('demo')

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

  const [adminUser, setAdminUser] = useState('vizion_build')
  const [adminPass, setAdminPass] = useState('')
  const [adminSummaryJson, setAdminSummaryJson] = useState('')
  const [adminDocsJson, setAdminDocsJson] = useState('')
  const [adminError, setAdminError] = useState('')

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [thread, fabOpen])

  function signOut() {
    setToken(null)
    setThread([])
    setComposer('')
    setShowSamplePrompt(true)
    setFeedbackStatus('')
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
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      setFeedbackStatus(`Sign-in failed: ${typeof body.detail === 'string' ? body.detail : res.status}`)
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

    if (showSamplePrompt) {
      setShowSamplePrompt(false)
    }

    setThread((history) => [...history, { role: 'user', body: text }])
    setComposer('')

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    }

    const res = await fetch(`${apiBase}/questions/ask`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ question: text }),
    })

    let payload: Record<string, unknown> = {}
    try {
      payload = (await res.json()) as Record<string, unknown>
    } catch {
      payload = {}
    }

    const requestId = typeof payload.request_id === 'string' ? payload.request_id : undefined

    if (res.status === 401 || res.status === 403) {
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
    const citations = Array.isArray(payload.citations) ? (payload.citations as CitationPayload[]) : []

    const assistantTurn: ChatTurn = {
      role: 'assistant',
      requestId,
      responseType: typeof payload.type === 'string' ? payload.type : '',
      answer: typeof payload.answer === 'string' ? payload.answer : null,
      refusalExplanation:
        typeof payload.refusal_explanation === 'string' ? payload.refusal_explanation : null,
      inferredPolicy:
        typeof payload.inferred_policy_type === 'string' ? payload.inferred_policy_type : null,
      citations,
      routing,
    }

    setThread((history) => [...history, assistantTurn])
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
      setFeedbackStatus('Set VITE_DOCUMENTS_PUBLIC_BASE or server DOCUMENTS_PUBLIC_BASE_URL for citation links.')
      return
    }
    window.open(`${docsBase}/${c.document_id}`, '_blank', 'noopener,noreferrer')
  }

  function loadAdminPanels() {
    setAdminSummaryJson('')
    setAdminDocsJson('')
    setAdminError('')
    if (!adminPass) {
      setAdminError('Set your admin_basic_password from .env.')
      return
    }
    const basic = typeof btoa === 'function' ? btoa(`${adminUser}:${adminPass}`) : ''

    fetch(`${apiBase}/admin/summary`, { headers: { Authorization: `Basic ${basic}` } })
      .then(async (response) => {
        const txt = await response.text()
        if (!response.ok) {
          throw new Error(txt || `${response.status}`)
        }
        return txt
      })
      .then((txt) => setAdminSummaryJson(txt))
      .catch((error: unknown) =>
        setAdminError(error instanceof Error ? error.message : 'summary failed'),
      )

    fetch(`${apiBase}/admin/documents`, { headers: { Authorization: `Basic ${basic}` } })
      .then(async (response) => {
        const txt = await response.text()
        if (!response.ok) {
          throw new Error(txt || `${response.status}`)
        }
        return txt
      })
      .then((txt) => setAdminDocsJson(txt))
      .catch((error: unknown) =>
        setAdminError((prior) =>
          `${prior}${prior ? '\n' : ''}${error instanceof Error ? error.message : 'documents failed'}`,
        ),
      )
  }

  const handleComposerSubmit = () => sendQuestion(composer)

  const handleComposerKeys = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleComposerSubmit()
    }
  }

  return (
    <div className="ask-root">
      <header className="ask-topbar">
        <div className="brand-stack">
          <span className="brand-title">Ask BPL — pilot modal</span>
          <span className="brand-subtitle">June 2026 demo client</span>
        </div>
        <nav className="segmented">
          <button
            type="button"
            className={`seg ${view === 'demo' ? 'active' : ''}`}
            onClick={() => setView('demo')}
          >
            Demo modal
          </button>
          <button
            type="button"
            className={`seg ${view === 'build' ? 'active' : ''}`}
            onClick={() => setView('build')}
          >
            Build-team readout
          </button>
        </nav>
      </header>

      {view === 'build' && (
        <section className="build-panel brutal-card">
          <h2>Ingest + weekly aggregates</h2>
          <p className="muted">
            Basic-auth credentials mirror <code>admin_basic_*</code> on the orchestrator.
          </p>
          <div className="form-grid">
            <label htmlFor="admin-u">Admin user</label>
            <input
              id="admin-u"
              className="brutal-input"
              autoComplete="username"
              value={adminUser}
              onChange={(e) => setAdminUser(e.target.value)}
            />

            <label htmlFor="admin-p">Admin password</label>
            <input
              id="admin-p"
              className="brutal-input"
              type="password"
              autoComplete="current-password"
              value={adminPass}
              onChange={(e) => setAdminPass(e.target.value)}
            />
          </div>
          <div className="row-actions">
            <button type="button" className="primary" onClick={loadAdminPanels}>
              Refresh /admin payloads
            </button>
          </div>
          {adminError && <pre className="error-block">{adminError}</pre>}
          <div className="admin-columns">
            <div>
              <h3>/admin/summary</h3>
              <pre className="json-pane">{adminSummaryJson || '{}'}</pre>
            </div>
            <div>
              <h3>/admin/documents</h3>
              <pre className="json-pane">{adminDocsJson || '{}'}</pre>
            </div>
          </div>
        </section>
      )}

      {view === 'demo' && !fabOpen && (
        <button
          type="button"
          aria-label="Open Ask BPL"
          title="Ask BPL"
          className="fab-book"
          onClick={() => setFabOpen(true)}
        >
          <BookGlyph />
        </button>
      )}

      {view === 'demo' && fabOpen && (
        <dialog className="modal-shell brutal-card open" aria-modal="true">
          <div className="modal-toolbar">
            <div>
              <strong>Ask BPL</strong>
              <p className="muted small">JWT kept in-memory for this demo tab.</p>
            </div>
            <button type="button" className="ghost" onClick={() => setFabOpen(false)}>
              Close
            </button>
          </div>

          {!token ? (
            <form className="signin-form brutal-stack" onSubmit={handleSignIn}>
              <p className="binding-note">
                Attribution mode is binding for this signing session (<code>attributed</code> stores
                your question verbatim; <code>anonymous</code> stores only a hash server-side).
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
          ) : (
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
                  <button type="button" className="secondary" onClick={() => sendQuestion(SAMPLE_PROMPT)}>
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
            </div>
          )}
        </dialog>
      )}
    </div>
  )
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
        <span className="pill subtle">
          {(turn.responseType ?? 'response').replace(/_/g, ' ')}
        </span>
        <span className="mono-muted">{turn.requestId ? turn.requestId.slice(0, 13) : 'pending'}</span>
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
          <p>{turn.refusalExplanation ?? (String(turn.answer ?? '').trim() || 'Blocked response.')}</p>
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
                    {(citation.document_title ?? 'Document')}
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
            <button type="button" className="secondary slim" onClick={() => onFeedback(turn.requestId!, 'helpful')}>
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
