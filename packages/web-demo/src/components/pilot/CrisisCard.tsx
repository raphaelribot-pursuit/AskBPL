import type { CrisisResource, CrisisResourceRow } from '../../conversation/types'

/** Shown even if the server sends no resource list: a crisis card must never be empty (SAF-2). */
const FALLBACK_RESOURCE: CrisisResource = {
  name: '988 Suicide & Crisis Lifeline',
  contact: 'Call or text 988',
  description: 'Free, confidential support available 24/7',
}

/**
 * Crisis response (SAF-2, UX-9; patch 0041). Rendered when the crisis gate stops a question before retrieval.
 * Support resources only: no policy answer, no error label, no feedback buttons. Wording comes from the server
 * (`services/crisis_gate.py`; final EAP text awaits BPL).
 */
export function CrisisCard({ row }: { row: CrisisResourceRow }) {
  const resources = row.resources.length > 0 ? row.resources : [FALLBACK_RESOURCE]
  const headingId = `crisis-heading-${row.id}`
  return (
    <section className="pilot-crisis-card" aria-labelledby={headingId} data-row-kind="crisis_resource">
      <h3 id={headingId} className="pilot-crisis-title">
        Support is available
      </h3>
      {row.message ? <p>{row.message}</p> : null}
      <ul className="pilot-crisis-resources">
        {resources.map((r) => (
          <li key={`${r.name}-${r.contact}`}>
            <strong>{r.name}</strong>
            <span className="pilot-crisis-contact">{r.contact}</span>
            {r.description ? <span className="pilot-crisis-description">{r.description}</span> : null}
          </li>
        ))}
      </ul>
      {row.closing ? <p>{row.closing}</p> : null}
    </section>
  )
}
