/**
 * Staff-facing input text uses plain language (PRD UX-1: no scores or jargon).
 * The shells are not rendered here (they need the API client), so their placeholder strings are checked in the source.
 */
import { describe, expect, it } from 'vitest'

import legacyShell from '../avatar/AvatarShellLegacy.tsx?raw'
import shell from '../components/pilot/WireframeShell.tsx?raw'

const JARGON = /corpus|retriev|chunk|vector|embedding|grounding|threshold|RAG\b/i

function placeholders(source: string): string[] {
  return [...source.matchAll(/placeholder="([^"]*)"/g)].map((m) => m[1])
}

describe('plain-language input text', () => {
  it.each([
    ['WireframeShell', shell],
    ['AvatarShellLegacy', legacyShell],
  ])('%s placeholders contain no technical jargon', (_name, source) => {
    const found = placeholders(source)
    expect(found.length).toBeGreaterThan(0)
    for (const text of found) expect(text, text).not.toMatch(JARGON)
  })

  it('the question box invites a policy question in plain words', () => {
    expect(placeholders(shell)).toContain('Ask a question about a BPL policy…')
  })
})
