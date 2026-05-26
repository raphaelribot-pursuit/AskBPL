import { useCallback, useMemo, useRef, useState } from 'react'

import {
  askQuestion,
  buildConversationContext,
  isMockEnabled,
  submitFeedback as submitFeedbackApi,
  type FeedbackRating,
  type FeedbackSubmitResult,
} from './askApi'
import type { CitationPayload, TranscriptRow } from './types'

/**
 * Shared chat state + API integration.
 *
 * Both the wireframe modal (`AskPilotShell` default) and the legacy
 * draggable avatar shell (gated by `VITE_ENABLE_AVATAR_SHELL`) consume this
 * hook, which keeps the request lifecycle, transcript bookkeeping, and the
 * mock-ask dev path in one place. The hook is UI-agnostic — it exposes
 * primitives, never markup.
 *
 * Behaviors covered:
 *   - Append a user-message row optimistically.
 *   - POST `/questions/ask`, narrow the response to a typed row, append.
 *   - 401/403 → invoke the supplied `onSessionExpired` (host page redirect).
 *   - Network failure → restore the question text via `onRestoreInput` so
 *     the tester can retry (Wireframe §4.6).
 *   - `submitFeedback` for per-message ratings + comments.
 *   - `openCitation` silently no-ops when `VITE_DOCUMENTS_PUBLIC_BASE`
 *     is not configured (demo UI must not surface dev config hints).
 */

let __rowSeq = 0
function nextRowId(): string {
  __rowSeq += 1
  return `row-${Date.now().toString(36)}-${__rowSeq}`
}

export type UseAskChatArgs = {
  apiBase: string
  docsBase: string
  token: string | null
  onSessionExpired: () => void
  /** Called when a 5xx/network error occurs so the parent can restore input. */
  onRestoreInput?: (text: string) => void
}

export type UseAskChatResult = {
  rows: TranscriptRow[]
  pending: boolean
  status: string
  setStatus: (next: string) => void
  /** Send `text` as a user message + dispatch the orchestrator request. */
  ask: (text: string) => Promise<void>
  submitFeedback: (args: {
    requestId: string
    rating: FeedbackRating
    comment: string | null
  }) => Promise<FeedbackSubmitResult>
  openCitation: (citation: CitationPayload) => void
  reset: () => void
  /** Live-region summary for the most recent assistant turn. */
  liveRegionMessage: string
}

export function useAskChat({
  apiBase,
  docsBase,
  token,
  onSessionExpired,
  onRestoreInput,
}: UseAskChatArgs): UseAskChatResult {
  const [rows, setRows] = useState<TranscriptRow[]>([])
  const [pending, setPending] = useState(false)
  const [status, setStatus] = useState('')
  const mockEnabled = useRef(isMockEnabled())

  const ask = useCallback(
    async (textRaw: string) => {
      const text = textRaw.trim()
      if (!text || pending) return
      if (!token && !mockEnabled.current) {
        setStatus('Session missing. Sign in again.')
        return
      }

      setStatus('')
      setPending(true)

      const conversationContext = buildConversationContext(rows)

      const userRowId = nextRowId()
      setRows((history) => [
        ...history,
        { kind: 'user_message', id: userRowId, body: text },
      ])

      const outcome = await askQuestion({
        apiBase,
        token: token ?? '',
        question: text,
        rowId: nextRowId(),
        conversationContext,
        mock: mockEnabled.current,
      })

      if (outcome.kind === 'session_expired') {
        setPending(false)
        onSessionExpired()
        return
      }

      if (outcome.kind === 'network_error') {
        setRows((history) => [
          ...history,
          {
            kind: 'error_generic',
            id: nextRowId(),
            message: outcome.message,
          },
        ])
        // Wireframe §4.6 — restore the question text so it isn’t lost.
        onRestoreInput?.(text)
        setPending(false)
        return
      }

      setRows((history) => [...history, outcome.row])
      setPending(false)
    },
    [apiBase, onRestoreInput, onSessionExpired, pending, rows, token],
  )

  const submitFeedback = useCallback(
    async (args: {
      requestId: string
      rating: FeedbackRating
      comment: string | null
    }): Promise<FeedbackSubmitResult> => {
      if (!token && !mockEnabled.current) {
        return { ok: false, error: 'Session missing.' }
      }
      return submitFeedbackApi({
        apiBase,
        token: token ?? '',
        requestId: args.requestId,
        rating: args.rating,
        comment: args.comment,
        mock: mockEnabled.current,
      })
    },
    [apiBase, token],
  )

  const openCitation = useCallback(
    (citation: CitationPayload) => {
      if (!docsBase) return
      window.open(
        `${docsBase}/${citation.document_id}`,
        '_blank',
        'noopener,noreferrer',
      )
    },
    [docsBase],
  )

  const reset = useCallback(() => {
    setRows([])
    setPending(false)
    setStatus('')
  }, [])

  const liveRegionMessage = useMemo(() => {
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

  return {
    rows,
    pending,
    status,
    setStatus,
    ask,
    submitFeedback,
    openCitation,
    reset,
    liveRegionMessage,
  }
}
