import { describe, expect, it } from 'vitest'

import { rowFromAskResponse } from './types'

describe('rowFromAskResponse refusal mapping', () => {
  it('maps refusal_oo_corpus to assistant_refusal', () => {
    const row = rowFromAskResponse({
      status: 200,
      id: 'r1',
      payload: {
        type: 'refusal_oo_corpus',
        request_id: 'req-1',
        refusal_explanation: 'No matching policy excerpts.',
        routing: [],
      },
    })
    expect(row.kind).toBe('assistant_refusal')
    if (row.kind === 'assistant_refusal') {
      expect(row.requestId).toBe('req-1')
      expect(row.explanation).toContain('No matching')
    }
  })

  it('maps refusal_citation_invalid to assistant_refusal', () => {
    const row = rowFromAskResponse({
      status: 200,
      id: 'r2',
      payload: {
        type: 'refusal_citation_invalid',
        request_id: 'req-2',
        refusal_explanation: 'Citation verification failed.',
        routing: [{ team: 'HR', contact_hint: 'hr@example.com', team_id: 'hr' }],
      },
    })
    expect(row.kind).toBe('assistant_refusal')
  })

  it('maps HTTP 504 to a temporary-unavailability message', () => {
    const row = rowFromAskResponse({
      status: 504,
      id: 'r4',
      payload: {
        type: 'error_timeout',
        message: 'Upstream API timeout. Please retry.',
      },
    })
    expect(row.kind).toBe('error_generic')
    if (row.kind === 'error_generic') {
      expect(row.message).toContain('timeout')
    }
  })

  it('maps error_pii to pii_banner with categories', () => {
    const row = rowFromAskResponse({
      status: 400,
      id: 'r3',
      payload: {
        type: 'error_pii',
        pii_categories: ['email_address'],
      },
    })
    expect(row.kind).toBe('pii_banner')
    if (row.kind === 'pii_banner') {
      expect(row.categories).toEqual(['email_address'])
    }
  })
})

describe('test-index label (OD-11)', () => {
  const answer = (extra: Record<string, unknown>, citations: unknown[] = []) =>
    rowFromAskResponse({
      status: 200,
      id: 'a1',
      payload: { type: 'answer', request_id: 'req-9', answer: 'Yes.', citations, routing: [], ...extra },
    })

  it('carries the server-provided label onto the answer row', () => {
    const row = answer({ index_label: 'Test index: sources not yet confirmed current by BPL' })
    expect(row.kind).toBe('assistant_answer')
    if (row.kind === 'assistant_answer') {
      expect(row.indexLabel).toBe('Test index: sources not yet confirmed current by BPL')
    }
  })

  it('still labels the answer when only a citation is flagged (fail-safe)', () => {
    const row = answer({}, [{ chunk_id: 'c1', document_id: 'd1', test_index: true }])
    if (row.kind !== 'assistant_answer') throw new Error('expected answer')
    expect(row.indexLabel).toMatch(/test index/i)
  })

  it('does not label an answer from confirmed sources', () => {
    const row = answer({}, [{ chunk_id: 'c1', document_id: 'd1', test_index: false }])
    if (row.kind !== 'assistant_answer') throw new Error('expected answer')
    expect(row.indexLabel).toBeNull()
  })

  it('ignores a blank label string', () => {
    const row = answer({ index_label: '   ' })
    if (row.kind !== 'assistant_answer') throw new Error('expected answer')
    expect(row.indexLabel).toBeNull()
  })
})
