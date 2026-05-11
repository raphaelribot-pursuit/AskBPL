import { useCallback, useEffect, useRef, useState } from 'react'
import { useDrag } from '@use-gesture/react'
import { DEFAULT_INSET_PX, SAFE_AREA_INSET_PX, STORAGE_KEYS } from './avatar.constants'
import type { AvatarPosition } from './avatar.types'
import type { AvatarSendFn } from './useAvatarStateMachine'

/**
 * Implements AskBPL_Avatar_Spec.md §6 — pointer drag with viewport bounds,
 * sessionStorage persistence, and machine notifications. The shell positions
 * the entire modal as one unit, so the returned `position` is the top-left
 * of that shell.
 */

type Size = { width: number; height: number }

type Snap = 'corners' | 'off'

export type UseAvatarDragOptions = {
  send: AvatarSendFn
  shellSize: Size
  /**
   * Snap-to-corner if released within 80px of a viewport corner. Default
   * "off" per spec §6.
   */
  snap?: Snap
  /** Disable drag entirely, e.g. while edge-docked. */
  disabled?: boolean
}

export type UseAvatarDrag = {
  position: AvatarPosition
  isDragging: boolean
  bind: ReturnType<typeof useDrag>
  setPositionTo: (next: AvatarPosition) => void
  /** Programmatic 10px nudges for keyboard parity (spec §9). */
  nudge: (dx: number, dy: number) => void
}

const SNAP_DISTANCE = 80

const readPersistedPosition = (): AvatarPosition | null => {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEYS.position)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<AvatarPosition>
    if (typeof parsed.x !== 'number' || typeof parsed.y !== 'number') return null
    return { x: parsed.x, y: parsed.y }
  } catch {
    return null
  }
}

const writePersistedPosition = (next: AvatarPosition): void => {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(STORAGE_KEYS.position, JSON.stringify(next))
  } catch {
    // sessionStorage may be unavailable in some embeds; ignore.
  }
}

const computeDefault = (shellSize: Size): AvatarPosition => {
  if (typeof window === 'undefined') return { x: 0, y: 0 }
  const x = Math.max(SAFE_AREA_INSET_PX, window.innerWidth - shellSize.width - DEFAULT_INSET_PX)
  const y = Math.max(SAFE_AREA_INSET_PX, window.innerHeight - shellSize.height - DEFAULT_INSET_PX)
  return { x, y }
}

const clampToViewport = (next: AvatarPosition, shellSize: Size): AvatarPosition => {
  if (typeof window === 'undefined') return next
  const maxX = Math.max(SAFE_AREA_INSET_PX, window.innerWidth - shellSize.width - SAFE_AREA_INSET_PX)
  const maxY = Math.max(SAFE_AREA_INSET_PX, window.innerHeight - shellSize.height - SAFE_AREA_INSET_PX)
  return {
    x: Math.min(Math.max(SAFE_AREA_INSET_PX, next.x), maxX),
    y: Math.min(Math.max(SAFE_AREA_INSET_PX, next.y), maxY),
  }
}

const cornerSnap = (next: AvatarPosition, shellSize: Size): AvatarPosition => {
  if (typeof window === 'undefined') return next
  const { innerWidth, innerHeight } = window
  const candidates: AvatarPosition[] = [
    { x: SAFE_AREA_INSET_PX, y: SAFE_AREA_INSET_PX },
    { x: innerWidth - shellSize.width - SAFE_AREA_INSET_PX, y: SAFE_AREA_INSET_PX },
    { x: SAFE_AREA_INSET_PX, y: innerHeight - shellSize.height - SAFE_AREA_INSET_PX },
    {
      x: innerWidth - shellSize.width - SAFE_AREA_INSET_PX,
      y: innerHeight - shellSize.height - SAFE_AREA_INSET_PX,
    },
  ]
  for (const candidate of candidates) {
    if (Math.hypot(next.x - candidate.x, next.y - candidate.y) <= SNAP_DISTANCE) {
      return candidate
    }
  }
  return next
}

export function useAvatarDrag(options: UseAvatarDragOptions): UseAvatarDrag {
  const { send, shellSize, snap = 'off', disabled = false } = options
  const [position, setPosition] = useState<AvatarPosition>(() => {
    const persisted = readPersistedPosition()
    return persisted ?? computeDefault(shellSize)
  })
  const [isDragging, setIsDragging] = useState(false)
  const dragStartedRef = useRef(false)

  // Re-clamp when the viewport resizes so the shell never strands offscreen.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const handle = () => setPosition((prev) => clampToViewport(prev, shellSize))
    window.addEventListener('resize', handle)
    return () => window.removeEventListener('resize', handle)
  }, [shellSize])

  // Re-clamp when the shell changes size (e.g. minimize → restore). This is a
  // genuine sync between the externally-measured shell size and our React
  // position state, so the rule-flagged setState in this effect is intentional.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPosition((prev) => {
      const next = clampToViewport(prev, shellSize)
      return next.x === prev.x && next.y === prev.y ? prev : next
    })
  }, [shellSize])

  const setPositionTo = useCallback(
    (next: AvatarPosition) => {
      const clamped = clampToViewport(next, shellSize)
      setPosition(clamped)
      writePersistedPosition(clamped)
    },
    [shellSize],
  )

  const nudge = useCallback(
    (dx: number, dy: number) => {
      setPositionTo({ x: position.x + dx, y: position.y + dy })
    },
    [position.x, position.y, setPositionTo],
  )

  const bind = useDrag(
    ({ first, last, movement: [mx, my], memo }) => {
      if (disabled) return memo
      const origin = (memo as AvatarPosition | undefined) ?? position

      if (first && !dragStartedRef.current) {
        dragStartedRef.current = true
        setIsDragging(true)
        send({ type: 'DRAG_START' })
      }

      const next = clampToViewport({ x: origin.x + mx, y: origin.y + my }, shellSize)

      if (last) {
        const final = snap === 'corners' ? cornerSnap(next, shellSize) : next
        setPosition(final)
        writePersistedPosition(final)
        setIsDragging(false)
        dragStartedRef.current = false
        send({ type: 'DRAG_END' })
        return origin
      }

      setPosition(next)
      return origin
    },
    {
      filterTaps: true,
      pointer: { keys: false },
      preventDefault: true,
    },
  )

  return { position, isDragging, bind, setPositionTo, nudge }
}
