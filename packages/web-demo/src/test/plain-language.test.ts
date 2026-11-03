/**
 * Staff-facing input text uses plain language (PRD UX-1: no scores or jargon).
 * The shells are not rendered here (they need the API client), so their placeholder strings are checked in the source.
 */
import { describe, expect, it } from 'vitest'

import legacyShell from '../avatar/AvatarShellLegacy.tsx?raw'
import citationCard from '../components/pilot/CitationCard.tsx?raw'
import documentViewer from '../components/pilot/DocumentViewer.tsx?raw'
import shell from '../components/pilot/WireframeShell.tsx?raw'
import welcome from '../components/pilot/WelcomeOverlay.tsx?raw'
import askChat from '../conversation/useAskChat.ts?raw'
import types from '../conversation/types.ts?raw'

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

/**
 * Patch 0055 (UX-1 audit): every string the default staff screen shows or announces, checked for technical terms.
 * Covers visible text between tags, quoted strings, aria-labels and the screen-reader announcements. The opt-in legacy
 * avatar shell (VITE_ENABLE_AVATAR_SHELL) is not the staff screen and is excluded.
 */
const STAFF_JARGON =
  /\b(corpus|retriev\w*|chunks?|vectors?|embeddings?|grounding|threshold|RAG|LLM|tokens?|JSON|UUID|payloads?|orchestrator|pinecone|anthropic|openai|test index|citations?|prompts?|out of corpus)\b/i

function visibleStrings(source: string): string[] {
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
  const quoted = [...code.matchAll(/'([^'\n]{4,})'|"([^"\n]{4,})"|`([^`\n]{4,})`/g)].map((m) => m[1] ?? m[2] ?? m[3])
  const jsxText = [...code.matchAll(/>\s*([^<>{}\n][^<>{}]*?)\s*</g)].map((m) => m[1])
  // Keep only text with at least two words (drops class names, ids, imports and keys).
  const isClassList = (s: string) => s.trim().split(/\s+/).every((w) => /^[a-z0-9]+(-[a-z0-9]+)+$/.test(w))
  return [...quoted, ...jsxText].filter(
    (s) => /[A-Za-z]{2,}\s+[A-Za-z]{2,}/.test(s) && !/^[./@]|className|\bimport\b/.test(s) && !isClassList(s),
  )
}

describe('default staff screen: no technical jargon (UX-1)', () => {
  it.each([
    ['WireframeShell', shell],
    ['CitationCard', citationCard],
    ['DocumentViewer', documentViewer],
    ['useAskChat (screen-reader announcements)', askChat],
    ['conversation/types (labels and fallbacks)', types],
  ])('%s', (_name, source) => {
    const strings = visibleStrings(source)
    expect(strings.length).toBeGreaterThan(0)
    for (const s of strings) expect(s, s).not.toMatch(STAFF_JARGON)
  })

  it('announces the crisis card to screen readers', () => {
    expect(askChat).toMatch(/case 'crisis_resource':\s*\n(?:\s*\/\/.*\n)*\s*return 'Support resources are shown\.'/)
  })
})

/** Patch 0065 (UX-2, SAF-6; team decision 2026-11-02): the intro must not claim more than the trust label does. */
describe('intro wording matches the trust label', () => {
  it.each([
    ['WelcomeOverlay', welcome],
    ['WireframeShell hint', shell],
  ])('%s says the documents are loaded for testing and never "authorized"', (_name, source) => {
    expect(source).not.toMatch(/authori[sz]ed/i)
    expect(source.replace(/\s+/g, ' ')).toMatch(/BPL policy documents loaded for testing/)
  })

  it('the welcome screen says BPL has not yet confirmed the documents are current', () => {
    expect(welcome.replace(/\s+/g, ' ')).toMatch(/BPL has not yet confirmed they are current/)
  })
})
