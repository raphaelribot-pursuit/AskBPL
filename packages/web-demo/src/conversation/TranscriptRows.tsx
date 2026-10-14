import { useEffect } from 'react'

import { useAvatarEvents } from '../avatar/AvatarEventsContext'
import type {
  AssistantAnswerRow,
  AssistantRefusalRow,
  CitationPayload,
  ErrorGenericRow,
  PiiBannerRow,
  RoutingPayload,
  UserMessageRow,
} from './types'
import { TestIndexNotice } from '../components/pilot/TestIndexNotice'

/**
 * Row-by-row renderers for the discriminated union in `./types.ts`.
 *
 * The transcript itself is owned by the shell; each component here is pure
 * and depends only on a single row + a small set of callbacks. That keeps
 * Screens 2 & 3 from forking — the modal renders the same `<TranscriptList>`
 * either way and the row kind decides what shows up.
 */

export function UserMessage({ row }: { row: UserMessageRow }) {
  return (
    <div className="bubble user brutal-border" data-row-kind="user_message">
      {row.body}
    </div>
  )
}

export function PiiBanner({ row }: { row: PiiBannerRow }) {
  // Banner is a sibling of the user bubble (Wireframe §5.3). It is NOT a bot
  // bubble — there is no feedback control here (Wireframe §5.6).
  const detail =
    row.categories.length > 0
      ? `Detected: ${row.categories.join(', ')}.`
      : 'Possible personal information detected.'
  return (
    <aside
      className="pii-banner brutal-border"
      role="status"
      data-row-kind="pii_banner"
    >
      <strong>This question was blocked for privacy.</strong>
      <p className="muted">{detail} Rephrase without personal details and try again.</p>
    </aside>
  )
}

export function AssistantAnswer({
  row,
  onFeedback,
  onOpenCitation,
}: {
  row: AssistantAnswerRow
  onFeedback: (requestId: string, rating: 'helpful' | 'not_helpful') => void
  onOpenCitation: (citation: CitationPayload) => void
}) {
  return (
    <article className="bubble assistant brutal-border" data-row-kind="assistant_answer">
      <div className="assistant-head">
        <span className="pill subtle">answer</span>
        <span className="mono-muted">{row.requestId.slice(0, 13) || 'no-id'}</span>
      </div>
      <div className="answer-block">
        {row.indexLabel ? <TestIndexNotice label={row.indexLabel} /> : null}
        <p className="answer-body">{row.body}</p>
        {row.citations.length > 0 ? (
          <ul className="citation-inset-stack" aria-label="Sources">
            {row.citations.map((citation, idx) => (
              <li key={`${citation.chunk_id}-${idx}`} className="citation-inset-item">
                <button
                  type="button"
                  className="citation-card"
                  onClick={() => onOpenCitation(citation)}
                  aria-label={`Open source document: ${citation.document_title ?? 'Document'}`}
                >
                  <span className="citation-card-title">
                    {citation.document_title ?? 'Document'}
                  </span>
                  {citation.section_heading ? (
                    <span className="citation-card-section">{citation.section_heading}</span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted citation-inset-missing">No citations were returned for this turn.</p>
        )}
      </div>
      {row.routing.length > 0 ? <RoutingDeck teams={row.routing} isRefusal={false} /> : null}
      <FeedbackRow requestId={row.requestId} onFeedback={onFeedback} />
    </article>
  )
}

export function AssistantRefusal({
  row,
  onFeedback,
}: {
  row: AssistantRefusalRow
  onFeedback: (requestId: string, rating: 'helpful' | 'not_helpful') => void
}) {
  return (
    <article className="bubble assistant brutal-border" data-row-kind="assistant_refusal">
      <div className="assistant-head">
        <span className="pill subtle">out of corpus</span>
        <span className="mono-muted">{row.requestId.slice(0, 13) || 'no-id'}</span>
      </div>
      <p>{row.explanation}</p>
      {row.routing.length > 0 ? (
        <RoutingDeck teams={row.routing} isRefusal />
      ) : (
        <p className="muted">Routing teams were not surfaced for this turn.</p>
      )}
      <FeedbackRow requestId={row.requestId} onFeedback={onFeedback} />
    </article>
  )
}

export function ErrorGeneric({ row }: { row: ErrorGenericRow }) {
  // No feedback control on generic errors — that maps to PII-rejection rules
  // (Wireframe §5.6) and applies to any non-assistant outcome.
  return (
    <article className="bubble assistant brutal-border" data-row-kind="error_generic">
      <div className="assistant-head">
        <span className="pill subtle">error</span>
      </div>
      <p className="error-text">{row.message}</p>
    </article>
  )
}

function FeedbackRow({
  requestId,
  onFeedback,
}: {
  requestId: string
  onFeedback: (requestId: string, rating: 'helpful' | 'not_helpful') => void
}) {
  if (!requestId) return null
  return (
    <div className="feedback-row">
      <button
        type="button"
        className="secondary slim"
        onClick={() => onFeedback(requestId, 'helpful')}
      >
        Helpful
      </button>
      <button
        type="button"
        className="secondary slim"
        onClick={() => onFeedback(requestId, 'not_helpful')}
      >
        Not helpful
      </button>
    </div>
  )
}

function RoutingDeck({ teams, isRefusal }: { teams: RoutingPayload[]; isRefusal: boolean }) {
  // Surfacing routing is itself an avatar beat (spec §5).
  const emit = useAvatarEvents()
  useEffect(() => {
    if (teams.length === 0) return
    emit({ type: 'RESPONSE_ROUTING' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teams.length])
  return (
    <div className={`routing-pane ${isRefusal ? 'refusal' : 'normal'}`}>
      <div className="panel-title">
        {isRefusal ? 'Suggested routing contacts' : 'Routing context'}
      </div>
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
