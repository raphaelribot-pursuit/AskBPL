import { useState } from 'react'

import type { FeedbackRating, FeedbackSubmitResult } from '../../conversation/askApi'

/**
 * FeedbackControl (Wireframe v3 §2.8).
 *
 * Two phases:
 *   1. Compact rating row — 👍 / 👎 buttons.
 *   2. After a rating is chosen, an optional comment textarea appears with
 *      a submit button. Comments are wired to `POST /feedback/`'s
 *      `comment` field (see `routes_feedback.py`).
 *
 * Once the orchestrator records the rating, the row collapses into a
 * “Thanks — recorded.” success line. Any error keeps the buttons available
 * so the tester can retry; the wireframe explicitly avoids blocking the
 * conversation on feedback failures.
 */

type FeedbackControlProps = {
  requestId: string
  /** Async submit. Should return `{ ok: true }` on success or `{ ok: false, error }`. */
  onSubmit: (args: {
    requestId: string
    rating: FeedbackRating
    comment: string | null
  }) => Promise<FeedbackSubmitResult>
}

type Phase = 'idle' | 'rated' | 'submitted'

export function FeedbackControl({ requestId, onSubmit }: FeedbackControlProps) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [rating, setRating] = useState<FeedbackRating | null>(null)
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!requestId) return null

  const choose = (next: FeedbackRating) => {
    if (submitting || phase === 'submitted') return
    setRating(next)
    setError(null)
    setPhase('rated')
  }

  const submit = async () => {
    if (!rating || submitting) return
    setSubmitting(true)
    setError(null)
    const result = await onSubmit({
      requestId,
      rating,
      comment: comment.trim() ? comment.trim() : null,
    })
    setSubmitting(false)
    if (result.ok) {
      setPhase('submitted')
    } else {
      setError(result.error)
    }
  }

  if (phase === 'submitted') {
    return (
      <div className="pilot-feedback" role="status">
        <span className="pilot-feedback-thanks">
          Thanks — feedback recorded.
        </span>
      </div>
    )
  }

  return (
    <div className="pilot-feedback">
      <div className="pilot-feedback-row">
        <span className="pilot-feedback-label">Was this helpful?</span>
        <button
          type="button"
          className={`pilot-feedback-button${rating === 'helpful' ? ' is-active' : ''}`}
          onClick={() => choose('helpful')}
          aria-pressed={rating === 'helpful'}
          disabled={submitting}
        >
          <span aria-hidden="true">👍</span>
          <span>Helpful</span>
        </button>
        <button
          type="button"
          className={`pilot-feedback-button${rating === 'not_helpful' ? ' is-active' : ''}`}
          onClick={() => choose('not_helpful')}
          aria-pressed={rating === 'not_helpful'}
          disabled={submitting}
        >
          <span aria-hidden="true">👎</span>
          <span>Not helpful</span>
        </button>
      </div>

      {phase === 'rated' && rating ? (
        <>
          <textarea
            className="pilot-feedback-comment"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder={
              rating === 'helpful'
                ? 'Optional: what made this answer useful?'
                : 'Optional: what was missing or wrong?'
            }
            maxLength={1000}
            disabled={submitting}
            aria-label="Feedback comment (optional)"
          />
          <div className="pilot-feedback-actions">
            <button
              type="button"
              className="pilot-button pilot-button-primary"
              onClick={submit}
              disabled={submitting}
              aria-busy={submitting}
            >
              {submitting ? 'Sending…' : 'Send feedback'}
            </button>
            {error ? (
              <span className="pilot-feedback-error" role="alert">
                {error}
              </span>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  )
}
