import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { namesRemovedFromPayload, namesRemovedText, rowFromAskResponse } from '../../conversation/types'
import { InputField, PRIVACY_HINT } from './InputField'
import { PilotTranscript } from './PilotTranscript'

/** Patch 0064 (SAF-1): staff are asked not to type names, and told when the server removed one. */

const ANSWER = {
  type: 'answer',
  request_id: 'req-1',
  answer: 'Supervisors approve annual leave.',
  citations: [{ chunk_id: 'c1', document_id: 'd1', document_title: 'Annual Leave Policy' }],
  routing: [],
}

function show(payload: Record<string, unknown>) {
  const row = rowFromAskResponse({ status: 200, payload, id: 'r1' })
  render(<PilotTranscript rows={[row]} pending={false} onFeedback={vi.fn()} onOpenCitation={vi.fn()} />)
}

describe('names in questions', () => {
  it('asks staff not to type names, under the question box and tied to it for screen readers', () => {
    render(<InputField value="" onChange={vi.fn()} onSubmit={vi.fn()} disabled={false} placeholder="Ask" />)
    expect(screen.getByText(PRIVACY_HINT)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /your question/i })).toHaveAccessibleDescription(PRIVACY_HINT)
    expect(PRIVACY_HINT).toMatch(/name/)
  })

  it('tells the staff member when a name was removed from an answered question', () => {
    show({ ...ANSWER, names_removed: 1 })
    expect(screen.getByRole('note')).toHaveTextContent('We removed a name from your question before searching the policies.')
  })

  it('says how many when more than one was removed, and on a refusal too', () => {
    show({ type: 'refusal_oo_corpus', request_id: 'req-2', refusal_explanation: 'I could not find enough approved policy information to answer reliably.', routing: [], names_removed: 2 })
    expect(screen.getByText(/We removed 2 names from your question/)).toBeInTheDocument()
  })

  it.each([[0], [undefined], [null], ['1'], [1.5], [-1]])('shows no note when the server sends %s', (value) => {
    show({ ...ANSWER, names_removed: value })
    expect(screen.queryByText(/We removed/)).not.toBeInTheDocument()
  })

  it('reads only whole positive numbers', () => {
    expect(namesRemovedFromPayload(3)).toBe(3)
    expect(namesRemovedFromPayload('3')).toBe(0)
    expect(namesRemovedText(1)).toMatch(/a name/)
  })
})
