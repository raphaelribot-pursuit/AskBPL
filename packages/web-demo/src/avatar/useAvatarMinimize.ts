import { useCallback, useEffect, useState } from 'react'
import { STORAGE_KEYS } from './avatar.constants'
import type { MinimizeMode } from './avatar.types'
import type { AvatarSendFn } from './useAvatarStateMachine'

/**
 * Implements AskBPL_Avatar_Spec.md §7. Owns the persisted minimize mode and
 * exposes restore + change-mode helpers. The state machine handles the
 * dormancy decisions; this hook just persists and dispatches.
 */

const isMinimizeMode = (value: string | null): value is MinimizeMode =>
  value === 'none' || value === 'pill' || value === 'dock'

const readPersistedMode = (): MinimizeMode => {
  if (typeof window === 'undefined') return 'none'
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEYS.minimized)
    return isMinimizeMode(raw) ? raw : 'none'
  } catch {
    return 'none'
  }
}

const writePersistedMode = (mode: MinimizeMode): void => {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(STORAGE_KEYS.minimized, mode)
  } catch {
    // ignore
  }
}

export type UseAvatarMinimize = {
  mode: MinimizeMode
  isMinimized: boolean
  minimizeTo: (mode: Exclude<MinimizeMode, 'none'>) => void
  restore: () => void
  toggle: () => void
}

export type UseAvatarMinimizeOptions = {
  send: AvatarSendFn
  /**
   * Optional initial mode override. When omitted the hook reads from
   * sessionStorage. Pass `'none'` to skip restoration in tests.
   */
  initialMode?: MinimizeMode
  /** Called once on mount with the restored mode (skipped if `'none'`). */
  onRestoreMount?: (mode: MinimizeMode) => void
}

export function useAvatarMinimize(options: UseAvatarMinimizeOptions): UseAvatarMinimize {
  const { send, initialMode, onRestoreMount } = options
  const [mode, setMode] = useState<MinimizeMode>(() => initialMode ?? readPersistedMode())

  // On first mount, replay the persisted mode into the state machine so the
  // Spline scene pauses immediately if the user reloaded into a minimized
  // session (spec §7 persistence).
  useEffect(() => {
    if (mode !== 'none') {
      send({ type: 'MINIMIZE', mode })
      onRestoreMount?.(mode)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const minimizeTo = useCallback(
    (next: Exclude<MinimizeMode, 'none'>) => {
      setMode(next)
      writePersistedMode(next)
      send({ type: 'MINIMIZE', mode: next })
    },
    [send],
  )

  const restore = useCallback(() => {
    setMode('none')
    writePersistedMode('none')
    send({ type: 'RESTORE' })
  }, [send])

  const toggle = useCallback(() => {
    if (mode === 'none') {
      minimizeTo('pill')
    } else {
      restore()
    }
  }, [mode, minimizeTo, restore])

  return {
    mode,
    isMinimized: mode !== 'none',
    minimizeTo,
    restore,
    toggle,
  }
}
