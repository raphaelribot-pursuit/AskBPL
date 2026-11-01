import { describe, expect, it } from 'vitest'

import { DocumentFetchError, fetchDocumentText, sourceUnavailableMessage } from './askApi'

const notOk = (status: number) => (async () => new Response('{}', { status })) as unknown as typeof fetch

describe('source unavailable state (UX-9)', () => {
  it('raises a typed error carrying the HTTP status when a source cannot be opened', async () => {
    const err = await fetchDocumentText({ apiBase: 'http://x', documentId: 'd1', mock: false, fetchImpl: notOk(404) }).catch((e) => e)

    expect(err).toBeInstanceOf(DocumentFetchError)
    expect((err as DocumentFetchError).status).toBe(404)
  })

  it('tells staff in plain words that a missing source is no longer available', () => {
    const message = sourceUnavailableMessage(new DocumentFetchError(404))

    expect(message).toMatch(/no longer available/i)
    expect(message).not.toMatch(/404|fetch|failed/i)
  })

  it('tells staff to try again when the source could not be loaded for another reason', () => {
    expect(sourceUnavailableMessage(new DocumentFetchError(503))).toMatch(/try again/i)
    expect(sourceUnavailableMessage(new TypeError('network down'))).toMatch(/try again/i)
  })
})
