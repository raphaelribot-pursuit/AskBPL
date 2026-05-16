/**
 * AvatarTrigger — 56×56 floating book FAB anchored bottom-right
 * (Wireframe v3 §2.1). Becomes the only visible chat affordance when the
 * modal is closed; the modal opens above it (anchored to the same corner).
 */

type AvatarTriggerProps = {
  onClick: () => void
  /** Hide-from-AT when the modal is open so screen readers focus the modal. */
  hidden?: boolean
  /** Forwarded so the modal can return focus to the FAB on close. */
  buttonRef?: React.Ref<HTMLButtonElement>
}

export function AvatarTrigger({ onClick, hidden, buttonRef }: AvatarTriggerProps) {
  return (
    <button
      ref={buttonRef}
      type="button"
      className="pilot-fab"
      onClick={onClick}
      aria-label="Open Ask BPL"
      title="Open Ask BPL"
      aria-hidden={hidden ? true : undefined}
      tabIndex={hidden ? -1 : undefined}
    >
      <BookGlyph />
    </button>
  )
}

function BookGlyph() {
  return (
    <svg viewBox="0 0 24 24" role="presentation" aria-hidden="true" focusable={false}>
      <path
        fill="currentColor"
        d="M5 4.5A2.5 2.5 0 0 1 7.5 2H19a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H7.5A1.5 1.5 0 0 0 6 20.5h13a1 1 0 1 1 0 2H6.5A2.5 2.5 0 0 1 4 20V5a.5.5 0 0 1 .25-.43A2.5 2.5 0 0 1 5 4.5Zm2.5-.5a.5.5 0 0 0-.5.5v12.06A3.4 3.4 0 0 1 7.5 16H18V4H7.5Z"
      />
    </svg>
  )
}
