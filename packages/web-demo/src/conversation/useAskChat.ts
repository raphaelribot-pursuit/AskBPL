import { useCallback, useMemo, useRef, useState } from 'react'

import { clearStoredSessionId } from './demoSession'
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
 */

let __rowSeq = 0
function nextRowId(): string {
  __rowSeq += 1
  return `row-${Date.now().toString(36)}-${__rowSeq}`
}

export type UseAskChatArgs = {
  apiBase: string
  docsBase: string
  /** Called when a 5xx/network error occurs so the parent can restore input. */
  onRestoreInput?: (text: string) => void
}

export type UseAskChatResult = {
  rows: TranscriptRow[]
  pending: boolean
  status: string
  setStatus: (next: string) => void
  ask: (text: string) => Promise<void>
  submitFeedback: (args: {
    requestId: string
    rating: FeedbackRating
    comment: string | null
  }) => Promise<FeedbackSubmitResult>
  openCitation: (citation: CitationPayload) => void
  reset: () => void
  liveRegionMessage: string
}

export function useAskChat({
  apiBase,
  docsBase,
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
        question: text,
        rowId: nextRowId(),
        conversationContext,
        mock: mockEnabled.current,
      })

      if (outcome.kind === 'session_expired') {
        clearStoredSessionId()
        setRows((history) => [
          ...history,
          {
            kind: 'error_generic',
            id: nextRowId(),
            message: 'Your session expired. Please send your question again.',
          },
        ])
        onRestoreInput?.(text)
        setPending(false)
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
        onRestoreInput?.(text)
        setPending(false)
        return
      }

      setRows((history) => [...history, outcome.row])
      setPending(false)
    },
    [apiBase, onRestoreInput, pending, rows],
  )

  const submitFeedback = useCallback(
    async (args: {
      requestId: string
      rating: FeedbackRating
      comment: string | null
    }): Promise<FeedbackSubmitResult> => {
      return submitFeedbackApi({
        apiBase,
        requestId: args.requestId,
        rating: args.rating,
        comment: args.comment,
        mock: mockEnabled.current,
      })
    },
    [apiBase],
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
    clearStoredSessionId()
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
