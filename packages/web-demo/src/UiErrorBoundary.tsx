import type { ErrorInfo, ReactNode } from 'react'
import { Component } from 'react'

type Props = {
  children: ReactNode
  fallback: ReactNode
  /** Dev-only hook for console diagnostics */
  label?: string
}

type State = { hasError: boolean }

/**
 * Catches render/lifecycle errors in the subtree (including lazy() rejections
 * after Suspense resolves) so a single bad chunk does not blank the whole app.
 */
export class UiErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) {
      const tag = this.props.label ?? 'UiErrorBoundary'
      console.warn(`[${tag}]`, error.message, info.componentStack)
    }
  }

  render(): ReactNode {
    return this.state.hasError ? this.props.fallback : this.props.children
  }
}
