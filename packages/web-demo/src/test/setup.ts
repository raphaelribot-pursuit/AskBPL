import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest globals are off, so Testing Library's automatic cleanup never registers.
// Without this, components rendered in one test stay in the DOM for the next.
afterEach(() => {
  cleanup()
})
