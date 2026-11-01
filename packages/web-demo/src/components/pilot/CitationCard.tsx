import { useState } from 'react'

import { formatPageLabel, type CitationPayload } from '../../conversation/types'

/**
 * CitationCard (Wireframe v3 §2.5). Up to 3 unique documents surface inline;
 * extras collapse into a `+N more sources` footer. Multiple chunks from the
 * same document render as one card with section headings and a count.
 *
 * Clicking a card opens the in-app document viewer (parent supplies handler).
 *
 * Patch 0054 (GRD-6): each card says "Show evidence" (visible and to screen readers), and the `+N more sources`
 * footer is a button that reveals the rest, so every cited source's evidence can be reached.
 */

const VISIBLE_LIMIT = 3

type GroupedCitation = {
  title: string
  documentId: string
  sections: string[]
  pages: string[]
  chunkIds: string[]
  count: number
  testIndex: boolean
}

type CitationCardListProps = {
  citations: CitationPayload[]
  onOpen: (documentId: string, chunkIds: string[]) => void
}

function groupCitations(citations: CitationPayload[]): GroupedCitation[] {
  const grouped = new Map<string, GroupedCitation>()

  for (const cite of citations) {
    const key = cite.document_id
    const existing = grouped.get(key)
    if (existing) {
      existing.count += 1
      existing.chunkIds.push(cite.chunk_id)
      if (cite.test_index === true) existing.testIndex = true
      const page = formatPageLabel(cite.page_start, cite.page_end)
      if (page && !existing.pages.includes(page)) existing.pages.push(page)
      if (
        cite.section_heading &&
        !existing.sections.includes(cite.section_heading)
      ) {
        existing.sections.push(cite.section_heading)
      }
    } else {
      grouped.set(key, {
        title: cite.document_title || 'Unknown document',
        documentId: cite.document_id,
        sections: cite.section_heading ? [cite.section_heading] : [],
        pages: (() => {
          const page = formatPageLabel(cite.page_start, cite.page_end)
          return page ? [page] : []
        })(),
        chunkIds: [cite.chunk_id],
        count: 1,
        testIndex: cite.test_index === true,
      })
    }
  }

  return Array.from(grouped.values())
}

export function CitationCardList({ citations, onOpen }: CitationCardListProps) {
  if (citations.length === 0) {
    return (
      <p className="pilot-citation-empty">
        No citations were returned for this turn.
      </p>
    )
  }

  return <GroupedCitationList grouped={groupCitations(citations)} onOpen={onOpen} />
}

function GroupedCitationList({
  grouped,
  onOpen,
}: {
  grouped: GroupedCitation[]
  onOpen: (documentId: string, chunkIds: string[]) => void
}) {
  const [showAll, setShowAll] = useState(false)
  const visible = showAll ? grouped : grouped.slice(0, VISIBLE_LIMIT)
  const overflow = grouped.length - Math.min(grouped.length, VISIBLE_LIMIT)

  return (
    <>
      <ul className="pilot-citation-list" aria-label="Sources">
        {visible.map((doc) => (
          <li key={doc.documentId}>
            <button
              type="button"
              className="pilot-citation pilot-citation-clickable"
              onClick={() => onOpen(doc.documentId, doc.chunkIds)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onOpen(doc.documentId, doc.chunkIds)
                }
              }}
              aria-label={`Show evidence: ${doc.title}${
                doc.sections.length > 0 ? ` — ${doc.sections.join(', ')}` : ''
              }${doc.pages.length > 0 ? ` — ${doc.pages.join(', ')}` : ''}${
                doc.count > 1 ? ` — ${doc.count} sections referenced` : ''}${
                doc.testIndex ? ' — test index, not yet confirmed current' : ''
              }`}
            >
              <strong>{doc.title}</strong>
              {doc.testIndex ? (
                <span className="pilot-citation-tag">Test index</span>
              ) : null}
              {doc.sections.length > 0 ? (
                <small>{doc.sections.join(' · ')}</small>
              ) : null}
              {doc.pages.length > 0 ? (
                <small className="pilot-citation-pages">{doc.pages.join(', ')}</small>
              ) : null}
              {doc.count > 1 ? (
                <span className="pilot-citation-count">
                  {doc.count} sections referenced
                </span>
              ) : null}
              <span className="pilot-citation-action" aria-hidden="true">
                Show evidence
              </span>
            </button>
          </li>
        ))}
      </ul>
      {overflow > 0 ? (
        <button
          type="button"
          className="pilot-citation-overflow"
          aria-expanded={showAll}
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll
            ? 'Show fewer sources'
            : `+${overflow} more ${overflow === 1 ? 'source' : 'sources'}`}
        </button>
      ) : null}
    </>
  )
}
