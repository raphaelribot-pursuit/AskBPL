import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { formatPageLabel, type AssistantAnswerRow } from '../../conversation/types'
import { CitationCardList } from './CitationCard'
import { DocumentViewer } from './DocumentViewer'
import { PilotTranscript } from './PilotTranscript'
import { AssistantAnswer } from '../../conversation/TranscriptRows'

/** Patch 0013 (PRD ING-11, GRD-4): page ranges reach staff; unknown pages show nothing. */

describe('formatPageLabel', () => {
  it('formats a single page and a range', () => {
    expect(formatPageLabel(2, 2)).toBe('p. 2')
    expect(formatPageLabel(2)).toBe('p. 2')
    expect(formatPageLabel(2, 3)).toBe('pp. 2\u20133')
    expect(formatPageLabel(8, 9)).toBe('pp. 8\u20139')
  })

  it('returns null when the start page is unknown or invalid', () => {
    expect(formatPageLabel(null, null)).toBeNull()
    expect(formatPageLabel(undefined)).toBeNull()
    expect(formatPageLabel(0, 3)).toBeNull()
    expect(formatPageLabel(-1, 3)).toBeNull()
    expect(formatPageLabel(1.5, 3)).toBeNull()
    expect(formatPageLabel('2', 3)).toBeNull()
    expect(formatPageLabel(null, 3)).toBeNull()
  })

  it('collapses a missing or inverted end to the start page', () => {
    expect(formatPageLabel(5, null)).toBe('p. 5')
    expect(formatPageLabel(5, undefined)).toBe('p. 5')
    expect(formatPageLabel(5, 3)).toBe('p. 5')
    expect(formatPageLabel(5, 'x')).toBe('p. 5')
  })
})

describe('CitationCardList pages', () => {
  it('shows the page range and announces it to screen readers', () => {
    render(
      <CitationCardList
        onOpen={vi.fn()}
        citations={[
          { chunk_id: 'c1', document_id: 'd1', document_title: 'Annual Leave Policy', page_start: 2, page_end: 3 },
        ]}
      />,
    )
    expect(screen.getByText('pp. 2\u20133')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Annual Leave Policy.*pp\. 2\u20133/ })).toBeInTheDocument()
  })

  it('lists each distinct page label once for a grouped document', () => {
    render(
      <CitationCardList
        onOpen={vi.fn()}
        citations={[
          { chunk_id: 'c1', document_id: 'd1', document_title: 'A', page_start: 2, page_end: 2 },
          { chunk_id: 'c2', document_id: 'd1', document_title: 'A', page_start: 2, page_end: 2 },
          { chunk_id: 'c3', document_id: 'd1', document_title: 'A', page_start: 8, page_end: 9 },
        ]}
      />,
    )
    expect(screen.getByText('p. 2, pp. 8\u20139')).toBeInTheDocument()
  })

  it('picks up a page from a later chunk when the first has none', () => {
    render(
      <CitationCardList
        onOpen={vi.fn()}
        citations={[
          { chunk_id: 'c1', document_id: 'd1', document_title: 'A', page_start: null, page_end: null },
          { chunk_id: 'c2', document_id: 'd1', document_title: 'A', page_start: 4, page_end: 4 },
        ]}
      />,
    )
    expect(screen.getByText('p. 4')).toBeInTheDocument()
  })

  it('shows no page text for rows ingested before 0013', () => {
    render(
      <CitationCardList
        onOpen={vi.fn()}
        citations={[{ chunk_id: 'c1', document_id: 'd1', document_title: 'Fundraising Policy' }]}
      />,
    )
    expect(screen.queryByText(/pp?\./)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^View source: Fundraising Policy$/ })).toBeInTheDocument()
  })
})

describe('PilotTranscript citation pages', () => {
  const row: AssistantAnswerRow = {
    kind: 'assistant_answer',
    id: 'r1',
    requestId: 'req-1',
    body: 'Answer.',
    citations: [
      { chunk_id: 'c1', document_id: 'd1', document_title: 'Annual Leave Policy', page_start: 3, page_end: 4 },
      { chunk_id: 'c2', document_id: 'd2', document_title: 'Fundraising Policy' },
    ],
    routing: [],
  }

  it('shows pages only on the citation that has them', () => {
    render(<PilotTranscript rows={[row]} pending={false} onFeedback={vi.fn()} onOpenCitation={vi.fn()} />)
    expect(screen.getAllByText('pp. 3\u20134')).toHaveLength(1)
    expect(screen.queryByText(/^p\. /)).not.toBeInTheDocument()
  })
})

describe('DocumentViewer pages', () => {
  const mockDoc = (chunks: unknown[]) =>
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers(),
        json: async () => ({
          document_id: 'd1', title: 'Policy', policy_type: 'p', test_index: false, full_text: 'x', chunks,
        }),
      }),
    )

  it('shows the page range on a chunk and nothing on an old chunk', async () => {
    mockDoc([
      { chunk_id: 'c1', ordinal: 0, text: 'First body', section_heading: 'Eligibility Requirements:', page_start: 2, page_end: 3, start_offset: 0, end_offset: 1 },
      { chunk_id: 'c2', ordinal: 1, text: 'Second body', section_heading: null, page_start: null, page_end: null, start_offset: 1, end_offset: 2 },
      { chunk_id: 'c3', ordinal: 2, text: 'Third body', section_heading: null, start_offset: 2, end_offset: 3 },
    ])
    try {
      render(<DocumentViewer apiBase="http://x" documentId="d1" highlightChunkIds={[]} onClose={vi.fn()} />)
      await waitFor(() => expect(screen.getByText('First body')).toBeInTheDocument())
      expect(screen.getByText('pp. 2\u20133')).toBeInTheDocument()
      expect(screen.getByText('Eligibility Requirements:')).toBeInTheDocument()
      expect(screen.getAllByText(/^pp?\. /)).toHaveLength(1)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

describe('Legacy AssistantAnswer citation pages', () => {
  it('shows pages only on the citation that has them', () => {
    const row: AssistantAnswerRow = {
      kind: 'assistant_answer', id: 'r1', requestId: 'req-1', body: 'Answer.', routing: [],
      citations: [
        { chunk_id: 'c1', document_id: 'd1', document_title: 'Annual Leave Policy', page_start: 3, page_end: 4 },
        { chunk_id: 'c2', document_id: 'd2', document_title: 'Fundraising Policy', page_start: null, page_end: null },
      ],
    }
    render(<AssistantAnswer row={row} onFeedback={vi.fn()} onOpenCitation={vi.fn()} />)
    expect(screen.getAllByText('pp. 3\u20134')).toHaveLength(1)
    expect(screen.queryByText(/^p\. /)).not.toBeInTheDocument()
  })
})
