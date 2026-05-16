import type { RoutingPayload } from '../../conversation/types'

/**
 * RoutingCard (Wireframe v3 §2.6).
 *
 * Title is `Routed to` when the orchestrator surfaced one or more contacts,
 * and falls back to `Try contacting` empty-state copy when no routing was
 * provided (Userflow RTG-5). Lives inside a bot bubble for both refusals
 * and informational answers that include routing context.
 */

type RoutingCardProps = {
  routing: RoutingPayload[]
  /** Refusal turns lead with “Routed to”; answer turns prefer “See also”. */
  variant: 'refusal' | 'answer'
}

export function RoutingCard({ routing, variant }: RoutingCardProps) {
  if (routing.length === 0) {
    if (variant !== 'refusal') return null
    return (
      <div className="pilot-routing" role="note">
        <p className="pilot-routing-title">Try contacting</p>
        <p className="pilot-status">
          Routing teams were not surfaced for this turn — reach out to your
          Department for guidance.
        </p>
      </div>
    )
  }

  const title = variant === 'refusal' ? 'Routed to' : 'See also'
  return (
    <div className="pilot-routing" role="note">
      <p className="pilot-routing-title">{title}</p>
      <ul className="pilot-routing-list">
        {routing.map((team) => (
          <li key={team.team_id} className="pilot-routing-item">
            <strong>{team.team}</strong>
            <p>{team.contact_hint}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
