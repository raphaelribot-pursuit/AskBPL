import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { rowFromAskResponse, type CrisisResourceRow } from '../../conversation/types'
import { CrisisCard } from './CrisisCard'
import { PilotTranscript } from './PilotTranscript'

// The payload the orchestrator sends when the crisis gate matches (services/crisis_gate.format_crisis_response).
const CRISIS_PAYLOAD = {
  type: 'crisis_resource',
  message: "I'm concerned about what you've shared. Your wellbeing matters, and there are people ready to help right now.",
  resources: [
    { name: '988 Suicide & Crisis Lifeline', contact: 'Call or text 988', description: 'Free, confidential support available 24/7' },
    { name: 'BPL Staff Employee Assistance Program', contact: '[Contact HR for EAP details]', description: 'TODO' },
  ],
  closing: 'Please reach out to one of these resources.',
  request_id: 'req-crisis-1',
}

describe('crisis response (SAF-2, UX-9)', () => {
  it('maps a crisis_resource response to a crisis row, not an error', () => {
    const row = rowFromAskResponse({ status: 200, payload: CRISIS_PAYLOAD, id: 'r1' })

    expect(row.kind).toBe('crisis_resource')
    const crisis = row as CrisisResourceRow
    expect(crisis.resources.map((r) => r.name)).toContain('988 Suicide & Crisis Lifeline')
    expect(crisis.closing).toBe('Please reach out to one of these resources.')
  })

  it('shows the message, every resource with its contact, and the closing line', () => {
    const row = rowFromAskResponse({ status: 200, payload: CRISIS_PAYLOAD, id: 'r1' }) as CrisisResourceRow

    render(<CrisisCard row={row} />)

    const card = screen.getByRole('region', { name: /support/i })
    expect(within(card).getByText(/concerned about what you've shared/i)).toBeInTheDocument()
    expect(within(card).getByText('988 Suicide & Crisis Lifeline')).toBeInTheDocument()
    expect(within(card).getByText('Call or text 988')).toBeInTheDocument()
    expect(within(card).getByText('BPL Staff Employee Assistance Program')).toBeInTheDocument()
    expect(within(card).getByText(/reach out to one of these resources/i)).toBeInTheDocument()
  })

  it('still shows the 988 Lifeline if the server sent no resources (fail-safe)', () => {
    const row = rowFromAskResponse({ status: 200, payload: { ...CRISIS_PAYLOAD, resources: [] }, id: 'r2' }) as CrisisResourceRow

    render(<CrisisCard row={row} />)

    expect(screen.getByText('Call or text 988')).toBeInTheDocument()
    expect(screen.getByText('Call 911')).toBeInTheDocument()  // SAF-8, patch 0067: immediate danger first
  })

  it('renders in the transcript as a crisis card with no error label and no feedback buttons', () => {
    const row = rowFromAskResponse({ status: 200, payload: CRISIS_PAYLOAD, id: 'r3' })

    render(<PilotTranscript rows={[row]} pending={false} onFeedback={vi.fn()} onOpenCitation={vi.fn()} />)

    expect(screen.getByRole('region', { name: /support/i })).toBeInTheDocument()
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /helpful/i })).not.toBeInTheDocument()
  })
})
