import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CitationCardList } from './CitationCard'
import { DocumentViewer } from './DocumentViewer'

/**
 * Patch 0054 (PRD GRD-6; UX specification section 11): a "Show evidence" interaction that exposes the supporting passage
 * without scores or raw identifiers; the cited passage is marked in words, not only by colour (WCAG 1.4.1); every cited
 * source can be reached.
 */

const cite = (n: number) => ({
  chunk_id: `chunk-${n}`,
  document_id: `doc-${n}`,
  document_title: `Policy ${n}`,
})

describe('Show evidence on source cards', () => {
  it('labels each source card "Show evidence", visibly and for screen readers', () => {
    const onOpen = vi.fn()
    render(<CitationCardList citations={[cite(1)]} onOpen={onOpen} />)

    const button = screen.getByRole('button', { name: /^Show evidence: Policy 1$/ })
    expect(within(button).getByText('Show evidence')).toBeInTheDocument()
    fireEvent.click(button)
    expect(onOpen).toHaveBeenCalledWith('doc-1', ['chunk-1'])
  })

  it('lets staff reach the evidence for every source, not only the first three', () => {
    const onOpen = vi.fn()
    render(<CitationCardList citations={[1, 2, 3, 4, 5].map(cite)} onOpen={onOpen} />)

    expect(screen.queryByRole('button', { name: /^Show evidence: Policy 5$/ })).not.toBeInTheDocument()
    const more = screen.getByRole('button', { name: '+2 more sources' })
    expect(more).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(more)
    fireEvent.click(screen.getByRole('button', { name: /^Show evidence: Policy 5$/ }))
    expect(onOpen).toHaveBeenCalledWith('doc-5', ['chunk-5'])
    expect(screen.getByRole('button', { name: 'Show fewer sources' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('never shows a score or a raw identifier on a source card', () => {
    const scored = { ...cite(1), score: 0.873, similarity: 0.873 } as unknown as ReturnType<typeof cite>
    const { container } = render(<CitationCardList citations={[scored]} onOpen={vi.fn()} />)

    expect(container.textContent).not.toMatch(/0\.87|87%|chunk-1|doc-1|score|similarity/i)
  })
})

describe('the evidence viewer', () => {
  afterEach(() => vi.restoreAllMocks())

  const DOC = {
    document_id: 'doc-1',
    title: 'Annual Leave Policy',
    policy_type: 'annual_leave',
    test_index: false,
    index_label: null,
    full_text: 'Intro.\n\nAll full-time non-union employees are eligible.',
    chunks: [
      { chunk_id: 'c-intro', ordinal: 0, text: 'Intro.', section_heading: null, page_start: 1, page_end: 1, start_offset: 0, end_offset: 6 },
      { chunk_id: 'c-cited', ordinal: 1, text: 'All full-time non-union employees are eligible.', section_heading: 'Eligibility', page_start: 2, page_end: 2, start_offset: 8, end_offset: 55 },
    ],
  }

  function renderViewer() {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(DOC), { status: 200, headers: { 'content-type': 'application/json' } }))
    const onClose = vi.fn()
    render(<DocumentViewer apiBase="http://api" documentId="doc-1" highlightChunkIds={['c-cited']} onClose={onClose} />)
    return onClose
  }

  it('marks the cited passage in words, once, next to that passage', async () => {
    renderViewer()

    await waitFor(() => expect(screen.getByText('All full-time non-union employees are eligible.')).toBeInTheDocument())
    const tags = screen.getAllByText('Cited in the answer')
    expect(tags).toHaveLength(1)
    expect(tags[0].parentElement).toHaveTextContent('All full-time non-union employees are eligible.')
    expect(tags[0].parentElement).not.toHaveTextContent('Intro.')
  })

  it('closes with "Hide evidence" and shows no identifiers or scores', async () => {
    const onClose = renderViewer()

    await waitFor(() => expect(screen.getByText('Eligibility')).toBeInTheDocument())
    expect(screen.getByRole('complementary', { name: 'Source document' }).textContent).not.toMatch(/c-cited|c-intro|doc-1|score/i)
    fireEvent.click(screen.getByRole('button', { name: 'Hide evidence' }))
    expect(onClose).toHaveBeenCalled()
  })
})
