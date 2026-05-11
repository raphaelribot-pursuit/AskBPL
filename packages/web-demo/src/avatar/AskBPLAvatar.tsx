import { AvatarScene } from './AvatarScene'
import type { AvatarSnapshot } from './useAvatarStateMachine'

/**
 * The visible avatar element — Spline scene (or SVG fallback) plus the
 * "drag me" affordance. Rendered both inside the modal toolbar and as the
 * minimized pill/dock face.
 */

type AskBPLAvatarProps = {
  snapshot: AvatarSnapshot
  reducedMotion: boolean
  size?: 'thumb' | 'standard' | 'pill'
  /**
   * If true, the underlying Spline scene is paused (no idle animation).
   * Driven by minimize state per spec §7.
   */
  paused?: boolean
}

const sizeClass: Record<NonNullable<AskBPLAvatarProps['size']>, string> = {
  thumb: 'avatar-face thumb',
  standard: 'avatar-face standard',
  pill: 'avatar-face pill',
}

export function AskBPLAvatar({
  snapshot,
  reducedMotion,
  size = 'standard',
  paused,
}: AskBPLAvatarProps) {
  const effectivePaused = paused ?? snapshot.minimized !== 'none'
  return (
    <div className={sizeClass[size]} data-state={snapshot.state}>
      <AvatarScene
        state={snapshot.state}
        paused={effectivePaused}
        reducedMotion={reducedMotion}
      />
    </div>
  )
}
