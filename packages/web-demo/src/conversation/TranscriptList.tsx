import {
  AssistantAnswer,
  AssistantRefusal,
  ErrorGeneric,
  PiiBanner,
  UserMessage,
} from './TranscriptRows'
import type { CitationPayload, TranscriptRow } from './types'

/**
 * Single point that resolves a `TranscriptRow` to its concrete renderer.
 * Screens 2 (grounded answer) and Screen 3 (refusal / PII / error) both
 * scroll through this same component — the row variant decides the visual.
 */

export function TranscriptList({
  rows,
  pending,
  onFeedback,
  onOpenCitation,
}: {
  rows: TranscriptRow[]
  /** True while a `/v1/ask` request is in flight, drives the typing indicator. */
  pending: boolean
  onFeedback: (requestId: string, rating: 'helpful' | 'not_helpful') => void
  onOpenCitation: (citation: CitationPayload) => void
}) {
  return (
    <>
      {rows.map((row) => {
        switch (row.kind) {
          case 'user_message':
            return <UserMessage key={row.id} row={row} />
          case 'pii_banner':
            return <PiiBanner key={row.id} row={row} />
          case 'assistant_answer':
            return (
              <AssistantAnswer
                key={row.id}
                row={row}
                onFeedback={onFeedback}
                onOpenCitation={onOpenCitation}
              />
            )
          case 'assistant_refusal':
            return <AssistantRefusal key={row.id} row={row} onFeedback={onFeedback} />
          case 'error_generic':
            return <ErrorGeneric key={row.id} row={row} />
        }
      })}
      {pending ? (
        <div
          className="bubble assistant brutal-border pending"
          aria-live="polite"
          aria-label="Ask BPL is thinking"
        >
          <span className="typing-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </div>
      ) : null}
    </>
  )
}
