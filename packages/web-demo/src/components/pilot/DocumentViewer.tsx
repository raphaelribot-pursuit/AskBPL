import { useEffect, useMemo, useRef, useState } from 'react'
import type { Components } from 'react-markdown'
import ReactMarkdown from 'react-markdown'

import {
  fetchDocumentText,
  isMockEnabled,
  type DocumentText,
} from '../../conversation/askApi'

const CHUNK_MARKDOWN: Components = {
  p: ({ children }) => <p className="doc-chunk-p">{children}</p>,
  ul: ({ children }) => <ul className="doc-chunk-ul">{children}</ul>,
  li: ({ children }) => <li className="doc-chunk-li">{children}</li>,
  strong: ({ children }) => <strong>{children}</strong>,
}

export type DocumentViewerProps = {
  apiBase: string
  documentId: string
  highlightChunkIds: string[]
  token: string
  onClose: () => void
}

export function DocumentViewer({
  apiBase,
  documentId,
  highlightChunkIds,
  token,
  onClose,
}: DocumentViewerProps) {
  const [doc, setDoc] = useState<DocumentText | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const highlightRef = useRef<HTMLDivElement | null>(null)

  const highlightSet = useMemo(
    () => new Set(highlightChunkIds),
    [highlightChunkIds],
  )

  const firstHighlightChunkId = useMemo(() => {
    if (!doc) return null
    for (const id of highlightChunkIds) {
      if (doc.chunks.some((c) => c.chunk_id === id)) return id
    }
    return highlightChunkIds[0] ?? null
  }, [doc, highlightChunkIds])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setDoc(null)

    fetchDocumentText({
      apiBase,
      documentId,
      token,
      mock: isMockEnabled(),
    })
      .then((payload) => {
        if (!cancelled) setDoc(payload)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load document')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [apiBase, documentId, token])

  useEffect(() => {
    if (!doc || !firstHighlightChunkId) return
    const timer = window.setTimeout(() => {
      highlightRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 100)
    return () => window.clearTimeout(timer)
  }, [doc, firstHighlightChunkId])

  return (
    <aside className="doc-viewer" aria-label="Source document">
      <div className="doc-viewer-header">
        <h3>{doc?.title ?? 'Source document'}</h3>
        <button
          type="button"
          onClick={onClose}
          className="doc-viewer-close"
          aria-label="Close viewer"
        >
          ×
        </button>
      </div>
      <div className="doc-viewer-body">
        {loading ? <p className="doc-viewer-status">Loading document…</p> : null}
        {error ? (
          <p className="doc-viewer-status doc-viewer-error" role="alert">
            {error}
          </p>
        ) : null}
        {!loading && !error && doc
          ? doc.chunks.map((chunk) => {
              const isHighlighted = highlightSet.has(chunk.chunk_id)
              return (
                <div
                  key={chunk.chunk_id}
                  ref={
                    chunk.chunk_id === firstHighlightChunkId ? highlightRef : undefined
                  }
                  className={`doc-chunk${isHighlighted ? ' doc-chunk-highlighted' : ''}`}
                >
                  {chunk.section_heading ? (
                    <h4 className="doc-chunk-heading">{chunk.section_heading}</h4>
                  ) : null}
                  <ReactMarkdown components={CHUNK_MARKDOWN}>{chunk.text}</ReactMarkdown>
                </div>
              )
            })
          : null}
      </div>
    </aside>
  )
}
