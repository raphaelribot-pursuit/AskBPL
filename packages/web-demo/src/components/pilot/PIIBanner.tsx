import type { PiiBannerRow } from '../../conversation/types'

/**
 * PIIBanner (Wireframe v3 §2.7, §5.3).
 *
 * Sibling of the user bubble — never a bot bubble — so the conversation
 * does not imply the assistant answered. We map raw category enum values
 * (e.g. `EMAIL_ADDRESS`) to the plain-English labels the wireframe shows
 * testers; unknown categories pass through capitalized.
 */

const PII_CATEGORY_LABELS: Record<string, string> = {
  EMAIL_ADDRESS: 'email address',
  PHONE_NUMBER: 'phone number',
  US_SSN: 'social security number',
  PERSON: "person's name",
  CREDIT_CARD: 'credit card number',
  IP_ADDRESS: 'IP address',
  DATE_TIME: 'date of birth',
  US_BANK_NUMBER: 'bank account number',
  STREET_ADDRESS: 'mailing address',
}

function humanize(category: string): string {
  if (PII_CATEGORY_LABELS[category]) return PII_CATEGORY_LABELS[category]
  return category.toLowerCase().replace(/_/g, ' ')
}

export function PIIBanner({ row }: { row: PiiBannerRow }) {
  return (
    <aside
      className="pilot-pii"
      role="status"
      aria-live="polite"
      data-row-kind="pii_banner"
    >
      <strong>This question was blocked for privacy.</strong>
      <p>
        We don’t process personal information like names, contact details, or
        identifiers. Rephrase the question without those details and try
        again.
      </p>
      {row.categories.length > 0 ? (
        <ul>
          {row.categories.map((cat, idx) => (
            <li key={`${cat}-${idx}`}>{humanize(cat)}</li>
          ))}
        </ul>
      ) : null}
    </aside>
  )
}
