/**
 * Build-team console API helpers (Basic auth → /v1/internal/*).
 * Denward Systems — Ask BPL pilot integration layer.
 */

export type AdminCredentials = {
  user: string
  password: string
}

function basicHeader(creds: AdminCredentials): string {
  if (typeof btoa !== 'function') return ''
  return `Basic ${btoa(`${creds.user}:${creds.password}`)}`
}

async function adminFetch(
  apiBase: string,
  creds: AdminCredentials,
  path: string,
  init?: RequestInit,
): Promise<Response> {
  return fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      Authorization: basicHeader(creds),
      ...(init?.headers ?? {}),
    },
  })
}

export type CorpusStatus = {
  doc_count: number
  page_count: number
  chunk_count: number
  last_ingest_at: string | null
  documents: Array<{
    document_id: string
    title: string
    version: string
    policy_type: string
    ingest_status: string
    last_ingested_at: string | null
    page_count: number | null
  }>
}

export type ReadoutSummary = {
  questions_total: number
  questions_submitted_last_7d: number
  questions_pii_blocked: number
  responses_non_answer_approx: number
  feedback_helpful: number
  feedback_not_helpful: number
}

export type FeedbackRow = {
  request_id: string
  session_id: string
  helpful: boolean
  comment: string | null
  created_at: string
}

export type FeedbackListResponse = {
  total: number
  helpful_count: number
  not_helpful_count: number
  items: FeedbackRow[]
}

export type RoutingRuleRow = {
  rule_id: string
  policy_type: string
  policy_display_name: string
  team_id: string
  team_name: string
  contact_hint: string
  priority: number
  selvon_approved: boolean
  approved_at: string | null
}

export async function fetchCorpusStatus(
  apiBase: string,
  creds: AdminCredentials,
): Promise<CorpusStatus> {
  const res = await adminFetch(apiBase, creds, '/v1/internal/corpus')
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as CorpusStatus
}

export async function fetchReadout(
  apiBase: string,
  creds: AdminCredentials,
): Promise<ReadoutSummary> {
  const res = await adminFetch(apiBase, creds, '/v1/internal/readout')
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as ReadoutSummary
}

export async function fetchRoutingRules(
  apiBase: string,
  creds: AdminCredentials,
): Promise<{ rules: RoutingRuleRow[]; pending_approval_count: number }> {
  const res = await adminFetch(apiBase, creds, '/v1/internal/routing')
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as { rules: RoutingRuleRow[]; pending_approval_count: number }
}

export async function triggerReIngest(
  apiBase: string,
  creds: AdminCredentials,
  /** Omit to let the API use server default pilot manifest (`INGEST_MANIFEST_PATH`). */
  manifestPath?: string | null,
): Promise<{ status: string; manifest: string }> {
  const body =
    manifestPath === undefined || manifestPath === null
      ? {}
      : { manifest_path: manifestPath }
  const res = await adminFetch(apiBase, creds, '/v1/internal/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as { status: string; manifest: string }
}

export async function fetchFeedbackList(
  apiBase: string,
  creds: AdminCredentials,
  limit = 50,
  offset = 0,
): Promise<FeedbackListResponse> {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const res = await adminFetch(apiBase, creds, `/v1/internal/feedback?${qs}`)
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as FeedbackListResponse
}

export async function setRoutingApproval(
  apiBase: string,
  creds: AdminCredentials,
  ruleId: string,
  selvonApproved: boolean,
): Promise<void> {
  const res = await adminFetch(apiBase, creds, `/v1/internal/routing/${ruleId}/approval`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selvon_approved: selvonApproved }),
  })
  if (!res.ok) throw new Error(await res.text())
}
