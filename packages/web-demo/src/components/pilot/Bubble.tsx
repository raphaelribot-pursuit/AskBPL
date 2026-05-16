import type { ReactNode } from 'react'

/**
 * Chat bubble (Wireframe v3 §2.4).
 *
 * `user` bubbles are accent-filled, right-aligned, and never host
 * sub-cards. `bot` bubbles can either render plain copy (when `children` is
 * a string) or wrap stacked sub-cards (citations, routing, feedback) inside
 * the bubble using `<Bubble.Stack>` — see `Stack` below. The bubble itself
 * stays at most 85% of the modal width.
 *
 * `tone="error"` switches the bot bubble to the wireframe danger palette
 * (Wireframe §4.6).
 */

type BubbleProps = {
  variant: 'user' | 'bot'
  tone?: 'default' | 'error'
  /** When true, renders the typing-dots animation instead of children. */
  typing?: boolean
  children?: ReactNode
}

export function Bubble({ variant, tone = 'default', typing, children }: BubbleProps) {
  const rowClass =
    variant === 'user' ? 'pilot-row pilot-row-user' : 'pilot-row pilot-row-bot'
  const bubbleClass = [
    'pilot-bubble',
    variant === 'user' ? 'pilot-bubble-user' : 'pilot-bubble-bot',
    tone === 'error' ? 'pilot-bubble-error' : null,
    typing ? 'pilot-bubble-typing' : null,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={rowClass} data-row-kind={variant === 'user' ? 'user_message' : undefined}>
      <div className={bubbleClass}>
        {typing ? (
          <span className="pilot-typing-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        ) : (
          children
        )}
      </div>
    </div>
  )
}

/**
 * Multi-section bot bubble: paragraph + citations + routing + feedback
 * (Wireframe §2.4 “bot bubble groups”). Renders inside a single `Bubble`
 * so the chrome stays unified.
 */
function Stack({ children }: { children: ReactNode }) {
  return <div className="pilot-bubble-stack">{children}</div>
}

Bubble.Stack = Stack
