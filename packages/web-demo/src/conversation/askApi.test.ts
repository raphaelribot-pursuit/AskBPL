import { describe, expect, it, vi } from 'vitest'

import { askQuestion, networkErrorMessage } from './askApi'

describe('networkErrorMessage', () => {
  it('returns timeout guidance for AbortSignal timeout errors', () => {
    const err = new DOMException('Timed out', 'TimeoutError')

    expect(networkErrorMessage(err)).toBe(
      'Your question is taking longer than expected. Please try again.',
    )
  })

  it('returns cold-start guidance for generic fetch failures', () => {
    expect(networkErrorMessage(new TypeError('Failed to fetch'))).toBe(
      'Unable to reach the server. It may be starting up — please wait 30 seconds and try again.',
    )
  })
})

describe('askQuestion network retry', () => {
  it('retries once after a transient fetch failure', async () => {
    vi.useFakeTimers()
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            type: 'refusal_oo_corpus',
            request_id: 'req-1',
            refusal_explanation: 'No excerpts.',
            routing: [],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )

    const outcomePromise = askQuestion({
      apiBase: 'https://api.example.com',
      token: 'token',
      question: 'What is the gift policy?',
      rowId: 'row-1',
      fetchImpl,
    })

    await vi.runAllTimersAsync()
    const outcome = await outcomePromise

    expect(fetchImpl).toHaveBeenCalledTimes(2)
    expect(outcome.kind).toBe('row')
    vi.useRealTimers()
  })
})
