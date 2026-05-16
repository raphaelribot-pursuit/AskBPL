import { AvatarShellLegacy } from './avatar/AvatarShellLegacy'
import { WireframeShell } from './components/pilot/WireframeShell'

/**
 * Ask BPL pilot shell — dispatcher.
 *
 * The default surface is the **wireframe v3 modal** (`WireframeShell`):
 * a 56px book FAB at `bottom: 24px; right: 24px` and, when opened, a fixed
 * 380px modal anchored 92px above the FAB. This is what the tester sees
 * after sign-in (Userflow Flow A → Wireframe §2 / §4 / §5).
 *
 * The previous draggable Spline-capable shell still ships, but is now
 * **opt-in** behind `VITE_ENABLE_AVATAR_SHELL=true`. It moved to
 * `avatar/AvatarShellLegacy.tsx` byte-for-byte so the avatar-spec work is
 * preserved for future demos without leaking into the pilot UI.
 *
 * Public surface (re-exports) is kept stable so existing call sites and
 * tests continue to compile.
 */

export type { AttributionMode } from './auth/types'
export type { CitationPayload, RoutingPayload } from './conversation/types'
export { DEFAULT_INSET_PX } from './avatar/avatar.constants'
export { BookGlyph } from './avatar/AvatarShellLegacy'

export type AskPilotShellProps = {
  apiBase: string
  docsBase: string
}

const isAvatarShellEnabled = (): boolean => {
  return import.meta.env.VITE_ENABLE_AVATAR_SHELL === 'true'
}

export function AskPilotShell({ apiBase, docsBase }: AskPilotShellProps) {
  if (isAvatarShellEnabled()) {
    return <AvatarShellLegacy apiBase={apiBase} docsBase={docsBase} />
  }
  return <WireframeShell apiBase={apiBase} docsBase={docsBase} />
}
