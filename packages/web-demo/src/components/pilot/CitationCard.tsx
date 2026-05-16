import type { CitationPayload } from '../../conversation/types'

/**
 * CitationCard (Wireframe v3 §2.5). Up to 3 citations surface inline; any
 * extras collapse into a `+N more sources` footer per the wireframe rule
 * (we cap inline cards rather than scroll a long list inside the bubble).
 *
 * Clicking a card always opens in a new tab through the parent-supplied
 * `onOpen` handler so the host page is never replaced.
 */

const VISIBLE_LIMIT = 3

type CitationCardListProps = {
  citations: CitationPayload[]
  onOpen: (citation: CitationPayload) => void
}

export function CitationCardList({ citations, onOpen }: CitationCardListProps) {
  if (citations.length === 0) {
    return (
      <p className="pilot-citation-empty">
        No citations were returned for this turn.
      </p>
    )
  }

  const visible = citations.slice(0, VISIBLE_LIMIT)
  const overflow = citations.length - visible.length

  return (
    <>
      <ul className="pilot-citation-list" aria-label="Sources">
        {visible.map((citation, idx) => (
          <li key={`${citation.chunk_id}-${idx}`}>
            <button
              type="button"
              className="pilot-citation"
              onClick={() => onOpen(citation)}
              aria-label={`Open source: ${citation.document_title ?? 'Document'}${
                citation.section_heading ? ` — ${citation.section_heading}` : ''
              } (opens in a new tab)`}
            >
              <strong>{citation.document_title ?? 'Document'}</strong>
              {citation.section_heading ? (
                <small>{citation.section_heading}</small>
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
