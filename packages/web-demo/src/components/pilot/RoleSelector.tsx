import { ROLE_OPTIONS, ROLE_PROMPT_LABEL, type RoleKey } from '../../conversation/roles'

/**
 * RoleSelector (PRD ROLE-1, ROLE-4, ROLE-5).
 *
 * "Explain this for: General | Staff | Manager". It changes the framing of the next answer, not what can be found, and
 * it can be changed at any point in a conversation. It is a radio group so keyboard and screen-reader users get arrow
 * key movement and a spoken "selected" state.
 */

type RoleSelectorProps = {
  value: RoleKey
  onChange: (next: RoleKey) => void
  disabled?: boolean
}

export function RoleSelector({ value, onChange, disabled }: RoleSelectorProps) {
  return (
    <div className="pilot-role" role="radiogroup" aria-label={ROLE_PROMPT_LABEL.replace(/:$/, '')}>
      <span className="pilot-role-prompt" aria-hidden="true">
        {ROLE_PROMPT_LABEL}
      </span>
      {ROLE_OPTIONS.map((option, index) => {
        const selected = option.key === value
        return (
          <button
            key={option.key}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            disabled={disabled}
            className={`pilot-role-chip${selected ? ' pilot-role-chip-selected' : ''}`}
            onClick={() => onChange(option.key)}
            onKeyDown={(event) => {
              if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
              event.preventDefault()
              const step = event.key === 'ArrowRight' ? 1 : -1
              const next = ROLE_OPTIONS[(index + step + ROLE_OPTIONS.length) % ROLE_OPTIONS.length]
              onChange(next.key)
              const group = event.currentTarget.parentElement
              window.setTimeout(() => {
                group?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[ROLE_OPTIONS.indexOf(next)]?.focus()
              }, 0)
            }}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
