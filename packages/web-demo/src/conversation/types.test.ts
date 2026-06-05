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
