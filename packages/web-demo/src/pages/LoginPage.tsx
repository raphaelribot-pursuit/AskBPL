import type { FormEvent } from 'react'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { BookGlyph } from '../components/pilot/AvatarTrigger'
import type { AttributionMode } from '../auth/types'
import { useAuth } from '../auth/useAuth'

/**
 * Screen 1 (Wireframe §3) — full-page sign-in.
 * Denward Systems × VizionScop3 — Ask BPL pilot v3.
 */

type LocationState = { from?: string } | null

function formatFastApiDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        try {
          return JSON.stringify(item)
        } catch {
          return String(item)
        }
      })
      .join('; ')
  }
  if (detail && typeof detail === 'object' && 'msg' in detail) {
    return String((detail as { msg: unknown }).msg)
  }
  try {
    return JSON.stringify(detail)
  } catch {
    return 'Request failed'
  }
}

export function LoginPage() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const navigate = useNavigate()
  const location = useLocation()
  const { session, signIn } = useAuth()

  const [email, setEmail] = useState(import.meta.env.VITE_PILOT_DEMO_EMAIL ?? '')
  const [accessCode, setAccessCode] = useState(import.meta.env.VITE_PILOT_DEMO_ACCESS_CODE ?? '')
  const [attribution, setAttribution] = useState<AttributionMode>('attributed')
  const [signingIn, setSigningIn] = useState(false)
  const [status, setStatus] = useState('')
  const [statusKind, setStatusKind] = useState<'info' | 'error'>('info')

  // If we already have a session, never show the login form — bounce to host.
  useEffect(() => {
    if (!session) return
    const state = location.state as LocationState
    navigate(state?.from && state.from !== '/login' ? state.from : '/', {
      replace: true,
    })
  }, [session, location.state, navigate])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (signingIn) return
    setStatus('')
    setStatusKind('info')
    setSigningIn(true)
    try {
      const res = await fetch(`${apiBase}/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          access_code: accessCode.trim(),
          attribution_mode: attribution,
          user_agent: navigator.userAgent?.slice(0, 240),
        }),
      })
      const body = (await res.json().catch(() => ({}))) as Record<string, unknown>
      if (!res.ok) {
        setStatus(`Sign-in failed: ${formatFastApiDetail(body.detail) || res.status}`)
        setStatusKind('error')
        return
      }
      const token = typeof body.token === 'string' ? body.token.trim() : ''
      if (!token) {
        setStatus(
          'Sign-in response had no token. Confirm the orchestrator is running and matches this demo client.',
        )
        setStatusKind('error')
        return
      }
      signIn({ token, email: email.trim(), attribution })
    } catch {
      setStatus(
        `Cannot reach the API at ${apiBase}. Start the orchestrator (e.g. port 8000) or set VITE_API_BASE_URL in .env.`,
      )
      setStatusKind('error')
    } finally {
      setSigningIn(false)
    }
  }

  return (
    <main className="askbpl-pilot-surface pilot-login">
      <section className="pilot-login-card" aria-labelledby="pilot-login-heading">
        <header className="pilot-login-brand">
          <div className="pilot-login-icon" aria-hidden="true">
            <BookGlyph />
          </div>
          <span className="pilot-eyebrow">Pilot v3</span>
          <h1 id="pilot-login-heading" className="pilot-title">
            Ask BPL — tester sign-in
          </h1>
          <p className="pilot-subtitle">
            Closed corpus answers from BPL policies and procedures.
          </p>
        </header>

        <form className="pilot-form" onSubmit={handleSubmit} noValidate>
          <p className="pilot-note">
            Attribution is binding for this signing session: <code>attributed</code>{' '}
            stores your question verbatim, <code>anonymous</code> stores only a
            hash server-side (ERD §4).
          </p>

          <div>
            <label className="pilot-label" htmlFor="si-email">
              Email
            </label>
            <input
              id="si-email"
              autoComplete="email"
              className="pilot-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div>
            <label className="pilot-label" htmlFor="si-pass">
              Access code
            </label>
            <input
              id="si-pass"
              autoComplete="off"
              className="pilot-input"
              type="password"
              value={accessCode}
              onChange={(e) => setAccessCode(e.target.value)}
            />
          </div>

          <fieldset className="pilot-fieldset">
            <legend className="pilot-sr-only">Attribution mode</legend>
            <label className="pilot-radio">
              <input
                type="radio"
                name="attrib"
                value="attributed"
                checked={attribution === 'attributed'}
                onChange={() => setAttribution('attributed')}
              />
              <span>
                <strong>Attributed</strong>
                <br />
                <span className="pilot-status">
                  Question retained for review.
                </span>
              </span>
            </label>
            <label className="pilot-radio">
              <input
                type="radio"
                name="attrib"
                value="anonymous"
                checked={attribution === 'anonymous'}
                onChange={() => setAttribution('anonymous')}
              />
              <span>
                <strong>Anonymous</strong>
                <br />
                <span className="pilot-status">
                  Hash only; no tester linkage stored (ERD §4).
                </span>
              </span>
            </label>
          </fieldset>

          <button
            className="pilot-button pilot-button-primary"
            type="submit"
            disabled={signingIn}
            aria-busy={signingIn}
          >
            {signingIn ? 'Signing in…' : 'Sign in'}
          </button>

          {status ? (
            <p
              className={`pilot-status${statusKind === 'error' ? ' is-error' : ''}`}
              role="status"
            >
              {status}
            </p>
          ) : null}
        </form>
      </section>
    </main>
  )
}
