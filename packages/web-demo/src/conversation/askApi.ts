import type { TranscriptRow } from './types'
import { rowFromAskResponse } from './types'

/**
 * Network layer for the Ask BPL chat surface.
 *
 * Centralizes the two endpoints the pilot modal talks to (`POST /questions/ask`
 * and `POST /feedback/`) so the wireframe shell and the legacy avatar shell
 * (gated behind `VITE_ENABLE_AVATAR_SHELL`) share one implementation. The
 * mock-ask helper backs the `VITE_MOCK_ASK=true` dev path used for UI QA
 * when the orchestrator is not running locally.
 */

export type FeedbackRating = 'helpful' | 'not_helpful'

export type FeedbackSubmitResult =
  | { ok: true }
  | { ok: false; error: string }

export type AskOutcome =
  | { kind: 'session_expired' }
  | { kind: 'network_error'; message: string }
  | { kind: 'row'; row: Exclude<TranscriptRow, { kind: 'user_message' }> }

export type AskRequestArgs = {
  apiBase: string
  token: string
  question: string
  /** Stable id for the row the caller will append to the transcript. */
  rowId: string
  /** When true, return canned data without hitting the orchestrator. */
  mock?: boolean
  /** Override `fetch`; mostly useful for tests. */
  fetchImpl?: typeof fetch
}

export async function askQuestion({
  apiBase,
  token,
  question,
  rowId,
  mock,
  fetchImpl,
}: AskRequestArgs): Promise<AskOutcome> {
  if (mock) {
    return mockAsk(question, rowId)
  }

  const f = fetchImpl ?? fetch
  let res: Response
  try {
    res = await f(`${apiBase}/questions/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ question }),
    })
  } catch {
    return {
      kind: 'network_error',
      message:
        'Network error. Check your connection or the orchestrator and try again.',
    }
  }

  if (res.status === 401 || res.status === 403) {
    return { kind: 'session_expired' }
  }

  let payload: Record<string, unknown>
  try {
    payload = (await res.json()) as Record<string, unknown>
  } catch {
    payload = {}
  }

  return {
    kind: 'row',
    row: rowFromAskResponse({ status: res.status, payload, id: rowId }),
  }
}

export type FeedbackSubmitArgs = {
  apiBase: string
  token: string
  requestId: string
  rating: FeedbackRating
  comment: string | null
  anonymousOverride?: boolean
  mock?: boolean
  fetchImpl?: typeof fetch
}

export async function submitFeedback({
  apiBase,
  token,
  requestId,
  rating,
  comment,
  anonymousOverride,
  mock,
  fetchImpl,
}: FeedbackSubmitArgs): Promise<FeedbackSubmitResult> {
  if (mock) return { ok: true }

  const f = fetchImpl ?? fetch
  let res: Response
  try {
    res = await f(`${apiBase}/feedback/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        request_id: requestId,
        rating,
        comment,
        anonymous_override: !!anonymousOverride,
      }),
    })
  } catch {
    return { ok: false, error: 'Network error.' }
  }

  if (res.ok) return { ok: true }
  if (res.status === 409) {
    // Idempotent in the wireframe’s eyes — feedback already exists.
    return { ok: true }
  }
  const text = await res.text().catch(() => '')
  return { ok: false, error: text || `Feedback failed (${res.status}).` }
}

/* ──────────────────────────────────────────────────────────────────────────
 * Mock path. Keep responses tiny + deterministic so QA can compare visuals
 * across runs. Triggered via `VITE_MOCK_ASK=true` (Wireframe v3 plan §6).
 * ────────────────────────────────────────────────────────────────────────── */

const MOCK_LATENCY_MS = 700

function mockAsk(
  question: string,
  rowId: string,
): Promise<AskOutcome> {
  const lower = question.toLowerCase()
  return new Promise((resolve) => {
    window.setTimeout(() => {
      if (
        lower.includes('@') ||
        lower.includes('ssn') ||
        lower.includes('phone') ||
        /\b\d{3}-\d{2}-\d{4}\b/.test(question) ||
        /\b\d{3}-\d{3}-\d{4}\b/.test(question)
      ) {
        resolve({
          kind: 'row',
          row: {
            kind: 'pii_banner',
            id: rowId,
            categories: ['EMAIL_ADDRESS', 'PHONE_NUMBER'],
          },
        })
        return
      }
      if (
        lower.includes('weather') ||
        lower.includes('news') ||
        lower.includes('outside')
      ) {
        resolve({
          kind: 'row',
          row: {
            kind: 'assistant_refusal',
            id: rowId,
            requestId: `mock-${Date.now().toString(36)}`,
            explanation:
              'That topic is outside the BPL policy and procedure corpus. The teams below can help.',
            routing: [
              {
                team: 'Department of HR',
                contact_hint: 'hr@bklynlibrary.org',
                team_id: 'hr',
              },
            ],
            inferredPolicy: null,
          },
        })
        return
      }
      resolve({
        kind: 'row',
        row: {
          kind: 'assistant_answer',
          id: rowId,
          requestId: `mock-${Date.now().toString(36)}`,
          body:
            'Per BPL policy, gift acceptance over $5,000 requires Director-level approval and a written summary on the donor record. Routine gifts (≤ $5,000) follow the standard intake form.',
          citations: [
            {
              chunk_id: 'mock-1',
              document_id: 'gift-acceptance.pdf',
              document_title: 'Gift Acceptance Policy',
              section_heading: '§3 Approval Thresholds',
            },
            {
              chunk_id: 'mock-2',
              document_id: 'donor-records.pdf',
              document_title: 'Donor Record Procedure',
              section_heading: 'Filing & Review',
            },
          ],
          routing: [],
          inferredPolicy: 'gift_acceptance',
        },
      })
    }, MOCK_LATENCY_MS)
  })
}

export function isMockEnabled(): boolean {
  // Env first, then `?mock=ask` query for ad-hoc QA toggles per page load.
  if (import.meta.env.VITE_MOCK_ASK === 'true') return true
  if (typeof window === 'undefined') return false
  try {
    return new URL(window.location.href).searchParams.get('mock') === 'ask'
  } catch {
    return false
  }
}
