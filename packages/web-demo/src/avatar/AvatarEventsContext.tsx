import { createContext, useContext, useMemo } from 'react'
import type { ReactNode } from 'react'
import type { AvatarSendFn } from './useAvatarStateMachine'

/**
 * Tiny event bus so descendants of the modal shell can emit lifecycle
 * `AvatarEvent`s without prop-drilling. Spec §5 keeps the avatar a pure
 * consumer — it never owns request state.
 */

type AvatarEventsApi = {
  emit: AvatarSendFn
}

const AvatarEventsContext = createContext<AvatarEventsApi | null>(null)

export function AvatarEventsProvider({
  emit,
  children,
}: {
  emit: AvatarSendFn
  children: ReactNode
}) {
  const value = useMemo<AvatarEventsApi>(() => ({ emit }), [emit])
  return <AvatarEventsContext.Provider value={value}>{children}</AvatarEventsContext.Provider>
}

const noopEmit: AvatarSendFn = () => undefined

// eslint-disable-next-line react-refresh/only-export-components
export function useAvatarEvents(): AvatarSendFn {
  const ctx = useContext(AvatarEventsContext)
  if (!ctx) return noopEmit
  return ctx.emit
}
