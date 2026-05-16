import type {
  AssistantAnswerRow,
  AssistantRefusalRow,
  CitationPayload,
  ErrorGenericRow,
  TranscriptRow,
  UserMessageRow,
} from '../../conversation/types'
import type { FeedbackRating, FeedbackSubmitResult } from '../../conversation/askApi'
import { Bubble } from './Bubble'
import { CitationCardList } from './CitationCard'
import { FeedbackControl } from './FeedbackControl'
import { PIIBanner } from './PIIBanner'
import { RoutingCard } from './RoutingCard'

/**
 * Wireframe v3 transcript renderer.
 *
 * Replaces the legacy `<TranscriptList>` (used only by the gated avatar
 * shell) with a render path that composes the pilot component library.
 * Each row maps to exactly one visual block; the typing indicator is a
 * regular bot bubble in `typing` mode (Wireframe §4.6), so it sits inline
 * with the conversation flow rather than off to the side.
 */

type FeedbackHandler = (args: {
  requestId: string
  rating: FeedbackRating
  comment: string | null
}) => Promise<FeedbackSubmitResult>

export type PilotTranscriptProps = {
  rows: TranscriptRow[]
  pending: boolean
  onFeedback: FeedbackHandler
  onOpenCitation: (citation: CitationPayload) => void
}

export function PilotTranscript({
  rows,
  pending,
  onFeedback,
  onOpenCitation,
}: PilotTranscriptProps) {
  return (
    <>
      {rows.map((row) => {
        switch (row.kind) {
          case 'user_message':
            return <UserMessage key={row.id} row={row} />
          case 'pii_banner':
            return <PIIBanner key={row.id} row={row} />
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
        <Bubble variant="bot" typing>
          {/* Children unused while typing; aria handled inline. */}
          <span className="pilot-sr-only">Ask BPL is thinking</span>
        </Bubble>
      ) : null}
    </>
  )
}

function UserMessage({ row }: { row: UserMessageRow }) {
  return <Bubble variant="user">{row.body}</Bubble>
}

function AssistantAnswer({
  row,
  onFeedback,
  onOpenCitation,
}: {
  row: AssistantAnswerRow
  onFeedback: FeedbackHandler
  onOpenCitation: (citation: CitationPayload) => void
}) {
  return (
    <Bubble variant="bot">
      <Bubble.Stack>
        <p>{row.body}</p>
        <CitationCardList citations={row.citations} onOpen={onOpenCitation} />
        {row.routing.length > 0 ? (
          <RoutingCard routing={row.routing} variant="answer" />
        ) : null}
        <FeedbackControl requestId={row.requestId} onSubmit={onFeedback} />
      </Bubble.Stack>
    </Bubble>
  )
}

function AssistantRefusal({
  row,
  onFeedback,
}: {
  row: AssistantRefusalRow
  onFeedback: FeedbackHandler
}) {
  return (
    <Bubble variant="bot">
      <Bubble.Stack>
        <p>{row.explanation}</p>
        <RoutingCard routing={row.routing} variant="refusal" />
        <FeedbackControl requestId={row.requestId} onSubmit={onFeedback} />
      </Bubble.Stack>
    </Bubble>
  )
}

function ErrorGeneric({ row }: { row: ErrorGenericRow }) {
  return (
    <Bubble variant="bot" tone="error">
      <strong>Something went wrong.</strong>
      <br />
      {row.message}
    </Bubble>
  )
}
