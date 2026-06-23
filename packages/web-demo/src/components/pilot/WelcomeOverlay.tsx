import { BookGlyph } from './AvatarTrigger'

const WELCOME_DISMISSED_KEY = 'askbpl.welcome.dismissed'

export function isWelcomeDismissed(): boolean {
  if (typeof window === 'undefined') return true
  try {
    return window.localStorage.getItem(WELCOME_DISMISSED_KEY) === '1'
  } catch {
    return false
  }
}

export function markWelcomeDismissed(): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(WELCOME_DISMISSED_KEY, '1')
  } catch {
    // ignore
  }
}

type WelcomeOverlayProps = {
  onContinue: () => void
}

export function WelcomeOverlay({ onContinue }: WelcomeOverlayProps) {
  return (
    <>
      <div className="pilot-welcome-backdrop" aria-hidden="true" />
      <section
        className="pilot-welcome"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pilot-welcome-heading"
      >
        <div className="pilot-welcome-icon" aria-hidden="true">
          <BookGlyph />
        </div>
        <p className="pilot-eyebrow">Ask BPL</p>
        <h2 id="pilot-welcome-heading" className="pilot-welcome-title">
          Welcome to the policy assistant
        </h2>
        <p className="pilot-welcome-copy">
          Use the chat modal to ask questions about Brooklyn Public Library policies
          and procedures. Answers come only from Selvon&apos;s curated document corpus —
          not the open web.
        </p>
        <p className="pilot-welcome-copy">
          Tap the book icon anytime to open or minimize the assistant while you browse
          this page.
        </p>
        <button type="button" className="pilot-welcome-cta" onClick={onContinue}>
          Open Ask BPL
        </button>
      </section>
    </>
  )
}
