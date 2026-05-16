import { createContext } from 'react'

import type { AuthContextValue } from './types'

/** Internal; consumers should use `useAuth()` from `./useAuth`. */
export const AuthReactContext = createContext<AuthContextValue | null>(null)
