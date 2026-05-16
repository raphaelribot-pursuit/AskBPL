import { useContext } from 'react'

import { AuthReactContext } from './auth-react-context'
import type { AuthContextValue } from './types'

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthReactContext)
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>')
  }
  return ctx
}
