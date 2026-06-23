import { describe, expect, it } from 'vitest'

import {
  apiSessionHeaders,
  getStoredSessionId,
  setStoredSessionId,
} from './demoSession'

describe('demoSession', () => {
  it('stores and reads the public demo session id', () => {
    setStoredSessionId('11111111-1111-1111-1111-111111111111')

    expect(getStoredSessionId()).toBe('11111111-1111-1111-1111-111111111111')
  })

  it('adds X-Session-ID to JSON request headers when present', () => {
    expect(apiSessionHeaders('abc')).toEqual({
      'Content-Type': 'application/json',
      'X-Session-ID': 'abc',
    })
  })
})
