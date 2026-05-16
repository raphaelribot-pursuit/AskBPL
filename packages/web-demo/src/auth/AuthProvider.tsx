import type { ReactNode } from 'react'
import { useCallback, useMemo, useState } from 'react'

import { AuthReactContext } from './auth-react-context'
import type { AuthContextValue, AuthSession } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null)

  const signIn = useCallback((next: AuthSession) => setSession(next), [])
  const signOut = useCallback(() => setSession(null), [])

  const value = useMemo<AuthContextValue>(
    () => ({ session, signIn, signOut }),
    [session, signIn, signOut],
  )

  return <AuthReactContext.Provider value={value}>{children}</AuthReactContext.Provider>
}
