const SESSION_STORAGE_KEY = 'askbpl.demo.session_id'

export function getStoredSessionId(): string | null {
  if (typeof window === 'undefined') return null
  try {
    const value = window.sessionStorage.getItem(SESSION_STORAGE_KEY)
    return value?.trim() ? value.trim() : null
  } catch {
    return null
  }
}

export function setStoredSessionId(sessionId: string): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId.trim())
  } catch {
    // sessionStorage may be unavailable in strict privacy modes
  }
}

export function clearStoredSessionId(): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY)
  } catch {
    // ignore
  }
}

export function persistSessionIdFromResponse(response: Response): void {
  const sessionId = response.headers.get('X-Session-ID')
  if (sessionId?.trim()) {
    setStoredSessionId(sessionId.trim())
  }
}

export function apiSessionHeaders(sessionId: string | null): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (sessionId) {
    headers['X-Session-ID'] = sessionId
  }
  return headers
}

export function apiSessionHeadersReadOnly(sessionId: string | null): Record<string, string> {
  if (!sessionId) return {}
  return { 'X-Session-ID': sessionId }
}
