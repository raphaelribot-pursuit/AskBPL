import type { Components } from 'react-markdown'
import ReactMarkdown from 'react-markdown'

/**
 * Renders assistant answer/refusal text with lightweight markdown support
 * (bold, lists, emphasis). Images, links, code blocks, and tables are
 * intentionally omitted for closed-corpus policy answers.
 */

const MARKDOWN_COMPONENTS: Components = {
  p: ({ children }) => <p className="pilot-answer-p">{children}</p>,
  ul: ({ children }) => <ul className="pilot-answer-ul">{children}</ul>,
  ol: ({ children }) => <ol className="pilot-answer-ol">{children}</ol>,
  li: ({ children }) => <li className="pilot-answer-li">{children}</li>,
  strong: ({ children }) => <strong>{children}</strong>,
  em: ({ children }) => <em>{children}</em>,
}

type AnswerMarkdownProps = {
  children: string
}

export function AnswerMarkdown({ children }: AnswerMarkdownProps) {
  return (
    <div className="pilot-answer-text">
      <ReactMarkdown components={MARKDOWN_COMPONENTS}>{children}</ReactMarkdown>
    </div>
  )
}
