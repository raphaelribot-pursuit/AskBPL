/**
 * Role lens options (patch 0024; PRD ROLE-1, ROLE-4, ROLE-5, ROLE-11).
 *
 * The role only changes how the answer is explained. It never limits which policies can be searched, and it is
 * self-selected, so it is not a security setting. The server accepts these keys and treats anything else as General,
 * so a stale or edited value here can never break a question.
 *
 * PROPOSED DEFAULTS pending BPL decision D-09 (role set, "Staff" vs "Frontline" label, default role).
 * The default role is Staff: the team's working choice (patch 0028), not a BPL decision. It must match `default_role`
 * in the server's config/roles.yaml; the server applies its own default when no role is sent.
 */

export type RoleKey = 'general' | 'staff' | 'manager'

export type RoleOption = { key: RoleKey; label: string }

export const ROLE_OPTIONS: readonly RoleOption[] = [
  { key: 'general', label: 'General' },
  { key: 'staff', label: 'Staff' },
  { key: 'manager', label: 'Manager' },
]

export const DEFAULT_ROLE: RoleKey = 'staff'

/** Wording for the control (ROLE-5): low-friction, not a security-role prompt. */
export const ROLE_PROMPT_LABEL = 'Explain this for:'

const STORAGE_KEY = 'askbpl.role'

export function normalizeRole(value: unknown): RoleKey {
  if (typeof value !== 'string') return DEFAULT_ROLE
  const key = value.trim().toLowerCase()
  return ROLE_OPTIONS.some((o) => o.key === key) ? (key as RoleKey) : DEFAULT_ROLE
}

/** Remembered for this browser tab only (session storage); never required, never sent anywhere but the ask request. */
export function readStoredRole(): RoleKey {
  try {
    return normalizeRole(window.sessionStorage.getItem(STORAGE_KEY))
  } catch {
    return DEFAULT_ROLE
  }
}

export function storeRole(role: RoleKey): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, role)
  } catch {
    // Storage can be blocked; the choice then lasts only until the page reloads.
  }
}

export function roleLabel(key: unknown): string {
  const k = normalizeRole(key)
  return ROLE_OPTIONS.find((o) => o.key === k)?.label ?? ROLE_OPTIONS[0].label
}
