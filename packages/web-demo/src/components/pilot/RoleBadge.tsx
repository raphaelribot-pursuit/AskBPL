/**
 * RoleBadge (PRD ROLE-9): which role lens framed this answer, e.g. "Explained for: Manager".
 * Shown on answers only. A refusal never carries a lens, because the role cannot change whether a question is answered.
 */

export function RoleBadge({ label }: { label: string }) {
  return (
    <p className="pilot-role-badge" data-testid="role-badge">
      Explained for: <strong>{label}</strong>
    </p>
  )
}
