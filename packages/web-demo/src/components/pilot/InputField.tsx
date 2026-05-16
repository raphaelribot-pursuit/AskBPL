import type { KeyboardEvent } from 'react'
import { useCallback, useEffect, useRef } from 'react'

/**
 * InputField (Wireframe v3 §2.3).
 *
 * Auto-growing textarea with Enter-to-submit and Shift+Enter for newline.
 * The send button mirrors the disabled state, and the parent owns the
 * `value` so the shell can clear it after a successful send (Userflow §6).
 *
 * On a 5xx the parent is expected to *restore* `value` so the tester does
 * not lose their question (Wireframe §4.6); this component does no error
 * handling itself.
 */

type InputFieldProps = {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  disabled?: boolean
  placeholder?: string
  /** Renders alongside the meta line — typically a “sample prompt” chip. */
  metaSlot?: React.ReactNode
}

const MAX_HEIGHT_PX = 120

export function InputField({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder,
  metaSlot,
}: InputFieldProps) {
  const ref = useRef<HTMLTextAreaElement | null>(null)

  // Auto-grow up to MAX_HEIGHT_PX, then scroll inside.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`
  }, [value])

  const handleKey = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault()
        if (!disabled && value.trim()) onSubmit()
      }
    },
    [disabled, onSubmit, value],
  )

  return (
    <>
      <div className="pilot-input-row">
        <textarea
          ref={ref}
          className="pilot-input-textarea"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          disabled={disabled}
          aria-label="Ask BPL — your question"
          rows={1}
        />
        <button
          type="button"
          className="pilot-button pilot-button-primary pilot-input-send"
          onClick={onSubmit}
          disabled={disabled || !value.trim()}
          aria-label="Send question"
        >
          {disabled ? 'Sending…' : 'Ask'}
        </button>
      </div>
      {metaSlot ? <div className="pilot-input-meta">{metaSlot}</div> : null}
    </>
  )
}
