/**
 * TestIndexNotice (PRD OD-11).
 *
 * While BPL has not confirmed that the pilot documents are current, every answer
 * drawn from them must say so, before the staff member reads the answer. The
 * label text comes from the orchestrator so wording lives in one place.
 */

type TestIndexNoticeProps = {
  label: string
  /** `answer` sits at the top of a bot bubble; `viewer` sits above document text. */
  variant?: 'answer' | 'viewer'
}

export function TestIndexNotice({ label, variant = 'answer' }: TestIndexNoticeProps) {
  return (
    <aside
      className={`pilot-test-index pilot-test-index-${variant}`}
      role="note"
      data-testid="test-index-notice"
    >
      <strong>{label}</strong>
      <p>
        This comes from policy documents BPL hasn’t yet confirmed are the
        current versions. Check with the policy owner before you act on it.
      </p>
    </aside>
  )
}
