/**
 * Conversation model per the plan in
 * `/Users/vizion/.cursor/plans/askbpl_screen_structure_6673dcee.plan.md`.
 *
 * Screens 2 and 3 share one transcript surface (Wireframe §4–§5). What
 * differs between them is **which row variant** the renderer emits for an
 * assistant turn, not the route or the modal shell. Each variant carries
 * exactly the fields the renderer needs and nothing more — extra payload
 * stays on the orchestrator response.
 */

export type CitationPayload = {
  chunk_id: string
  document_id: string
  document_title?: string
  section_heading?: string | null
  /** 1-based page range of the cited chunk; null/absent for rows ingested before patch 0013. */
  page_start?: number | null
  page_end?: number | null
  /** True when the cited document is not yet BPL-confirmed (OD-11 test index). */
  test_index?: boolean
}

function asPage(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 ? value : null
}

/**
 * "p. 2" or "pp. 2–3" for a chunk's page range (PRD GRD-4). Returns null when the
 * start page is unknown, so staff never see a guessed or half-formed location.
 * A missing or inverted end collapses to the single start page.
 */
export function formatPageLabel(start: unknown, end?: unknown): string | null {
  const first = asPage(start)
  if (first === null) return null
  const last = asPage(end)
  if (last === null || last <= first) return `p. ${first}`
  return `pp. ${first}\u2013${last}`
}

/** Shown when a citation is flagged but the server sent no label text. */
export const DEFAULT_TEST_INDEX_LABEL =
  'Test index: sources not yet confirmed current by BPL'

/**
 * Fail-safe: the label shows if the server sent one OR any citation is flagged,
 * so a missing field on one side cannot hide it from staff.
 */
export function testIndexLabelFor(
  indexLabel: unknown,
  citations: CitationPayload[],
): string | null {
  if (typeof indexLabel === 'string' && indexLabel.trim() !== '') return indexLabel
  return citations.some((c) => c.test_index === true) ? DEFAULT_TEST_INDEX_LABEL : null
}

/** The label the server says it used. Anything malformed is ignored, so a bad field can never hide an answer. */
export function roleLabelFromPayload(role: unknown): string | null {
  if (typeof role !== 'object' || role === null) return null
  const label = (role as Record<string, unknown>).label
  return typeof label === 'string' && label.trim() !== '' ? label.trim().slice(0, 40) : null
}

export type RoutingPayload = {
  team: string
  contact_hint: string
  team_id: string
}

/** What the user typed; mirrored verbatim into a bubble. */
export type UserMessageRow = {
  kind: 'user_message'
  id: string
  body: string
}

/**
 * Privacy gate (Wireframe §5.3, Userflow §5.1). Rendered as a banner that is
 * a **sibling** of the user bubble, not inside a bot bubble — there is no
 * assistant turn and no feedback control here.
 */
export type PiiBannerRow = {
  kind: 'pii_banner'
  id: string
  /** Categories reported by `error_pii.pii_categories`, may be empty. */
  categories: string[]
}

/** `type: "answer"` (Wireframe §4.5, Userflow §8.1). */
export type AssistantAnswerRow = {
  kind: 'assistant_answer'
  id: string
  requestId: string
  body: string
  citations: CitationPayload[]
  routing: RoutingPayload[]
  inferredPolicy?: string | null
  /** Non-null when any cited source is not yet confirmed by BPL (OD-11). */
  indexLabel?: string | null
  /** Role lens that framed this answer (ROLE-9). Absent on answers from a server that predates patch 0024. */
  roleLabel?: string | null
}

/** `type: "refusal"` (Wireframe §5.4–5.5). */
export type AssistantRefusalRow = {
  kind: 'assistant_refusal'
  id: string
  requestId: string
  explanation: string
  routing: RoutingPayload[]
  inferredPolicy?: string | null
}

/** Any non-PII non-2xx (Wireframe §4.6). 401/403 also surface as this. */
export type ErrorGenericRow = {
  kind: 'error_generic'
  id: string
  message: string
}

export type TranscriptRow =
  | UserMessageRow
  | PiiBannerRow
  | AssistantAnswerRow
  | AssistantRefusalRow
  | ErrorGenericRow

/**
 * Narrow the orchestrator JSON into our typed row. Caller passes:
 *
 *  - `status`     — HTTP status from the `/v1/ask` response
 *  - `payload`    — parsed JSON body (may be `{}` if parse failed)
 *  - `id`         — caller-supplied transcript row id (e.g. nanoid / counter)
 *
 * Behaviors mapped 1:1 from the userflow state machine (Userflow §2, §8.1):
 *
 *  - 400 + `type === 'error_pii'` → `pii_banner`
 *  - 200 + `type === 'answer'`    → `assistant_answer`
 *  - 200 + `type === 'refusal'`   → `assistant_refusal`
 *  - anything else (incl. 401/5xx) → `error_generic`
 */
export function rowFromAskResponse(args: {
  status: number
  payload: Record<string, unknown>
  id: string
}): Exclude<TranscriptRow, UserMessageRow> {
  const { status, payload, id } = args
  const responseType = typeof payload.type === 'string' ? payload.type : ''
  const requestId = typeof payload.request_id === 'string' ? payload.request_id : ''
  const piiCategories = Array.isArray(payload.pii_categories)
    ? (payload.pii_categories as unknown[]).filter(
        (entry): entry is string => typeof entry === 'string',
      )
    : []

  // 401/403 collapse to a generic error here; the host page interprets the
  // status separately to decide whether to send the user back to `/login`.
  if (status === 401 || status === 403) {
    return {
      kind: 'error_generic',
      id,
      message: 'Your session has expired. Please sign out and sign back in.',
    }
  }

  if (status === 429) {
    return {
      kind: 'error_generic',
      id,
      message: 'Too many requests. Please wait a moment and try again.',
    }
  }

  if (status === 500) {
    const serverMessage =
      typeof payload.message === 'string'
        ? payload.message
        : 'The server encountered an error. Please try again.'
    return { kind: 'error_generic', id, message: serverMessage }
  }

  if (status === 502 || status === 503 || status === 504) {
    const serverMessage =
      typeof payload.message === 'string'
        ? payload.message
        : 'The server is temporarily unavailable. Please try again in a moment.'
    return { kind: 'error_generic', id, message: serverMessage }
  }

  if (status === 400 && responseType === 'error_pii') {
    return { kind: 'pii_banner', id, categories: piiCategories }
  }

  if (status >= 200 && status < 300) {
    if (responseType === 'answer') {
      const body = typeof payload.answer === 'string' ? payload.answer : ''
      const citations = Array.isArray(payload.citations)
        ? (payload.citations as CitationPayload[])
        : []
      const routing = Array.isArray(payload.routing)
        ? (payload.routing as RoutingPayload[])
        : []
      return {
        kind: 'assistant_answer',
        id,
        requestId,
        body,
        citations,
        routing,
        inferredPolicy:
          typeof payload.inferred_policy_type === 'string'
            ? payload.inferred_policy_type
            : null,
        indexLabel: testIndexLabelFor(payload.index_label, citations),
        roleLabel: roleLabelFromPayload(payload.role),
      }
    }

    if (
      responseType === 'refusal' ||
      responseType === 'refusal_oo_corpus' ||
      responseType === 'refusal_citation_invalid'
    ) {
      const explanation =
        typeof payload.refusal_explanation === 'string'
          ? payload.refusal_explanation
          : typeof payload.answer === 'string'
            ? payload.answer
            : 'Out of corpus — see the routing suggestions.'
      const routing = Array.isArray(payload.routing)
        ? (payload.routing as RoutingPayload[])
        : []
      return {
        kind: 'assistant_refusal',
        id,
        requestId,
        explanation,
        routing,
        inferredPolicy:
          typeof payload.inferred_policy_type === 'string'
            ? payload.inferred_policy_type
            : null,
      }
    }
  }

  const serverMessage =
    typeof payload.message === 'string'
      ? payload.message
      : typeof payload.detail === 'string'
        ? payload.detail
        : 'Something went wrong. Please try again.'

  return {
    kind: 'error_generic',
    id,
    message: serverMessage,
  }
}
