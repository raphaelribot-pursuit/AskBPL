/**
 * Pilot session types (Wireframe 3.7 — token in memory only).
 */

export type AttributionMode = 'attributed' | 'anonymous'

export type AuthSession = {
  token: string
  email: string
  attribution: AttributionMode
}

export type AuthContextValue = {
  session: AuthSession | null
  signIn: (session: AuthSession) => void
  signOut: () => void
}
