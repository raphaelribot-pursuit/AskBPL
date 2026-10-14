import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AssistantAnswerRow } from '../../conversation/types'
import { CitationCardList } from './CitationCard'
import { PilotTranscript } from './PilotTranscript'
import { DocumentViewer } from './DocumentViewer'

const LABEL = 'Test index: sources not yet confirmed current by BPL'

const baseRow: AssistantAnswerRow = {
  kind: 'assistant_answer',
  id: 'r1',
  requestId: 'req-1',
  body: 'Staff accrue leave monthly.',
  citations: [{ chunk_id: 'c1', document_id: 'd1', document_title: 'Annual Leave Policy', test_index: true }],
  routing: [],
}

const renderTranscript = (row: AssistantAnswerRow) =>
  render(
    <PilotTranscript
      rows={[row]}
      pending={false}
      onFeedback={vi.fn()}
      onOpenCitation={vi.fn()}
    />,
  )

describe('PilotTranscript test-index notice', () => {
  it('shows the label before the answer text', () => {
    renderTranscript({ ...baseRow, indexLabel: LABEL })
    const notice = screen.getByTestId('test-index-notice')
    expect(notice).toHaveTextContent(LABEL)
    const answer = screen.getByText('Staff accrue leave monthly.')
    // notice precedes the answer in document order
    expect(notice.compareDocumentPosition(answer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows no notice for an answer from confirmed sources', () => {
    renderTranscript({ ...baseRow, indexLabel: null, citations: [{ chunk_id: 'c1', document_id: 'd1' }] })
    expect(screen.queryByTestId('test-index-notice')).not.toBeInTheDocument()
  })
})

describe('CitationCardList test-index tag', () => {
  it('tags only the flagged source and says so to screen readers', () => {
    render(
      <CitationCardList
        onOpen={vi.fn()}
        citations={[
          { chunk_id: 'c1', document_id: 'd1', document_title: 'Annual Leave Policy', test_index: true },
          { chunk_id: 'c2', document_id: 'd2', document_title: 'Fundraising Policy' },
        ]}
      />,
    )
    expect(screen.getAllByText('Test index')).toHaveLength(1)
    expect(
      screen.getByRole('button', { name: /Annual Leave Policy.*test index, not yet confirmed current/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^View source: Fundraising Policy$/ })).toBeInTheDocument()
  })

  it('tags the grouped card if any of its chunks is flagged', () => {
    render(
      <CitationCardList
        onOpen={vi.fn()}
        citations={[
          { chunk_id: 'c1', document_id: 'd1', document_title: 'A', test_index: false },
          { chunk_id: 'c2', document_id: 'd1', document_title: 'A', test_index: true },
        ]}
      />,
    )
    expect(screen.getAllByText('Test index')).toHaveLength(1)
  })
})

describe('DocumentViewer test-index banner', () => {
  it('shows the banner when the document is test-index', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({
        document_id: 'd1', title: 'Annual Leave Policy', policy_type: 'annual_leave',
        test_index: true, index_label: LABEL, full_text: 'x',
        chunks: [{ chunk_id: 'c1', ordinal: 0, text: 'Leave text', section_heading: null, start_offset: 0, end_offset: 1 }],
      }),
    })
    vi.stubGlobal('fetch', fetchImpl)
    try {
      render(<DocumentViewer apiBase="http://x" documentId="d1" highlightChunkIds={[]} onClose={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('test-index-notice')).toHaveTextContent(LABEL))
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('shows no banner for a confirmed document', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({
        document_id: 'd1', title: 'Policy', policy_type: 'p', test_index: false, full_text: 'x',
        chunks: [{ chunk_id: 'c1', ordinal: 0, text: 'Body text', section_heading: null, start_offset: 0, end_offset: 1 }],
      }),
    }))
    try {
      render(<DocumentViewer apiBase="http://x" documentId="d1" highlightChunkIds={[]} onClose={vi.fn()} />)
      await waitFor(() => expect(screen.getByText('Body text')).toBeInTheDocument())
      expect(screen.queryByTestId('test-index-notice')).not.toBeInTheDocument()
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
