import type { CitationPayload } from '../../conversation/types'

/**
 * CitationCard (Wireframe v3 §2.5). Up to 3 unique documents surface inline;
 * extras collapse into a `+N more sources` footer. Multiple chunks from the
 * same document render as one card with section headings and a count.
 *
 * Clicking a card opens the in-app document viewer (parent supplies handler).
 */

const VISIBLE_LIMIT = 3

type GroupedCitation = {
  title: string
  documentId: string
  sections: string[]
  chunkIds: string[]
  count: number
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
        chunkIds: [cite.chunk_id],
        count: 1,
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

  const grouped = groupCitations(citations)
  const visible = grouped.slice(0, VISIBLE_LIMIT)
  const overflow = grouped.length - visible.length

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
              aria-label={`View source: ${doc.title}${
                doc.sections.length > 0 ? ` — ${doc.sections.join(', ')}` : ''
              }${doc.count > 1 ? ` — ${doc.count} sections referenced` : ''}`}
            >
              <strong>{doc.title}</strong>
              {doc.sections.length > 0 ? (
                <small>{doc.sections.join(' · ')}</small>
              ) : null}
              {doc.count > 1 ? (
                <span className="pilot-citation-count">
                  {doc.count} sections referenced
                </span>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
      {overflow > 0 ? (
        <p className="pilot-citation-overflow">
          +{overflow} more {overflow === 1 ? 'source' : 'sources'}
        </p>
      ) : null}
    </>
  )
}
