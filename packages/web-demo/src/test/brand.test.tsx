/**
 * BPL brand guards (docs/BRANDING.md). The rules come from BPL's "Logo Usage" guide (D-08, received 2026-10-31).
 * jsdom does not apply stylesheets, so the CSS rules are checked from the stylesheet text.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import logoDataUrl from '../assets/brand/BklynPublicLibrary_blue_RGB_hires.png?inline'
import { Modal } from '../components/pilot/Modal'
import brandCss from '../theme/bpl-brand.css?raw'
import sharepointCss from '../theme/sharepoint-tokens.css?raw'

// SHA-256 of the file exactly as BPL supplied it ("Do not remake the logo").
const LOGO_SHA256 = '5e17a696056fa72b041d8dcca72337a8949f3a22a1c9db73f8afb031181e6ecc'
const LOGO_W = 2100
const LOGO_H = 769
const N_HEIGHT_RATIO = 0.432 // height of the "n" / logo height, measured on the supplied artwork

function token(name: string): string {
  const m = brandCss.match(new RegExp(`${name}:\\s*([^;]+);`))
  if (!m) throw new Error(`${name} not defined in bpl-brand.css`)
  return m[1].trim()
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const f = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('BPL brand', () => {
  it('uses BPL Blue as given in the guide (RGB 60/93/170)', () => {
    expect(token('--bpl-blue').toLowerCase()).toBe('#3c5daa')
  })

  it('keeps every brand text pairing at WCAG AA contrast (4.5:1)', () => {
    const blue = token('--bpl-blue')
    const dark = token('--bpl-blue-dark')
    const soft = token('--bpl-blue-soft')
    for (const [fg, bg] of [
      ['#ffffff', blue],
      ['#ffffff', dark],
      [blue, '#ffffff'],
      [blue, soft],
      [dark, soft],
    ]) {
      expect(contrast(fg, bg), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('never shows the logo below 1.25 inches (120 CSS px) and keeps clearance of at least the "n" height', () => {
    const width = parseFloat(token('--bpl-logo-width'))
    const clearance = parseFloat(token('--bpl-logo-clearance'))
    expect(width).toBeGreaterThanOrEqual(120)
    expect(clearance).toBeGreaterThanOrEqual(Math.ceil(width * (LOGO_H / LOGO_W) * N_HEIGHT_RATIO))
    expect(brandCss).toMatch(/\.pilot-modal-logo\s*\{[^}]*height:\s*auto/) // aspect ratio kept
    expect(brandCss).toMatch(/\.pilot-modal \.pilot-modal-header\s*\{[^}]*background:\s*#ffffff/) // colour logo on white
  })

  it('ships the logo byte-for-byte as BPL supplied it', async () => {
    const bytes = Uint8Array.from(atob(logoDataUrl.split(',')[1]), (c) => c.charCodeAt(0))
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))
    expect(Array.from(digest, (x) => x.toString(16).padStart(2, '0')).join('')).toBe(LOGO_SHA256)
  })

  it('recolours only the widget: the SharePoint host page keeps its own palette', () => {
    const rootBlock = brandCss.match(/:root\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(rootBlock).not.toMatch(/--sp-|--accent|--wf-/)
    expect(sharepointCss).toMatch(/--sp-blue-primary:\s*#0078d4/i)
  })

  it('shows the logo with a text alternative in the Ask BPL header', () => {
    render(
      <Modal open onClose={() => {}} footer={null}>
        body
      </Modal>,
    )
    const logo = screen.getByRole('img', { name: 'Brooklyn Public Library' })
    expect(logo).toHaveClass('pilot-modal-logo')
    expect(logo.getAttribute('src')).toMatch(/BklynPublicLibrary_blue_RGB_hires/)
    expect(Number(logo.getAttribute('width'))).toBeGreaterThanOrEqual(120)
    expect(screen.getByText('Ask BPL')).toBeInTheDocument()
  })
})
