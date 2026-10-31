import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef } from 'react'

import bplLogoBlue from '../../assets/brand/BklynPublicLibrary_blue_RGB_hires.png'

/**
 * Modal (Wireframe v3 §2.2).
 *
 * Fixed 380px panel anchored 92px above the FAB. Owns:
 *   - Header: BPL logo (BPL Blue, on white, at the 1.25-inch minimum with clearance; docs/BRANDING.md),
 *     `Ask BPL` title, signed-in subtitle, minimize + close icons.
 *   - Scrollable body: `#FAFAF7` background, plays host to the transcript
 *     list. Renders behind the “↓ new message” jump control if the parent
 *     decides to surface one.
 *   - Footer: input region passed in via `footer` slot.
 *
 * Accessibility: `role="dialog"`, `aria-modal="false"` (the wireframe
 * intentionally lets the host page stay interactive — it’s an overlay, not
 * a true blocker), Escape closes, focus moves to the close button on open
 * and returns to the launching FAB on close. We trap Tab/Shift+Tab inside
 * the dialog while it is open so keyboard users do not fall back into the
 * host page (Wireframe §2.2 a11y note).
 */

type ModalProps = {
  open: boolean
  onClose: () => void
  /** Optional minimize affordance (renders a chevron in the header). */
  onMinimize?: () => void
  signedInLabel?: string
  /** Element to return focus to on close — typically the FAB. */
  returnFocusRef?: React.RefObject<HTMLElement | null>
  children: ReactNode
  footer: ReactNode
  /** Live region announcement updated when a new transcript row lands. */
  liveRegion?: string
}

export function Modal({
  open,
  onClose,
  onMinimize,
  signedInLabel,
  returnFocusRef,
  children,
  footer,
  liveRegion,
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)

  // Focus the close button on open, restore focus on close.
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const focusReturnEl = returnFocusRef?.current ?? null
    closeButtonRef.current?.focus()
    return () => {
      if (focusReturnEl) {
        focusReturnEl.focus()
      } else {
        previous?.focus?.()
      }
    }
  }, [open, returnFocusRef])

  // Escape closes; Tab cycles inside the dialog.
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !dialogRef.current) return

      const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (event.shiftKey && active === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    },
    [onClose],
  )

  if (!open) return null

  return (
    <>
      <div className="pilot-modal-backdrop" aria-hidden="true" />
      <div
        ref={dialogRef}
        className="pilot-modal"
        role="dialog"
        aria-modal="false"
        aria-labelledby="pilot-modal-title"
        onKeyDown={handleKeyDown}
      >
        <header className="pilot-modal-header">
          <img
            className="pilot-modal-logo"
            src={bplLogoBlue}
            alt="Brooklyn Public Library"
            width={120}
            height={44}
          />
          <div className="pilot-modal-title">
            <strong id="pilot-modal-title">Ask BPL</strong>
            {signedInLabel ? <span>{signedInLabel}</span> : null}
          </div>
          <div className="pilot-modal-actions">
            {onMinimize ? (
              <button
                type="button"
                className="pilot-icon-button"
                onClick={onMinimize}
                aria-label="Minimize Ask BPL"
                title="Minimize"
              >
                <span aria-hidden="true">▾</span>
              </button>
            ) : null}
            <button
              ref={closeButtonRef}
              type="button"
              className="pilot-icon-button"
              onClick={onClose}
              aria-label="Close Ask BPL"
              title="Close"
            >
              <span aria-hidden="true">✕</span>
            </button>
          </div>
        </header>

        <div className="pilot-modal-body-wrap">{children}</div>

        <footer className="pilot-modal-footer">{footer}</footer>

        <span className="pilot-sr-only" role="status" aria-live="polite">
          {liveRegion ?? ''}
        </span>
      </div>
    </>
  )
}
