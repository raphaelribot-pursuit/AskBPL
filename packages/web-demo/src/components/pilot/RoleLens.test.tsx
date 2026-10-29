import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { askQuestion } from '../../conversation/askApi'
import { DEFAULT_ROLE, normalizeRole, readStoredRole, roleLabel, storeRole } from '../../conversation/roles'
import { rowFromAskResponse, roleLabelFromPayload, type AssistantAnswerRow } from '../../conversation/types'
import { PilotTranscript } from './PilotTranscript'
import { RoleSelector } from './RoleSelector'

const ok = (body: Record<string, unknown>) =>
  new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })

describe('normalizeRole', () => {
  it('keeps the three known roles and defaults everything else to General', () => {
    expect(normalizeRole('staff')).toBe('staff')
    expect(normalizeRole(' MANAGER ')).toBe('manager')
    for (const bad of [undefined, null, '', 'admin', 'executive', 7, {}, []]) {
      expect(normalizeRole(bad)).toBe(DEFAULT_ROLE)
    }
  })

  it('remembers the choice for the tab and survives blocked storage', () => {
    storeRole('manager')
    expect(readStoredRole()).toBe('manager')
    window.sessionStorage.setItem('askbpl.role', 'nonsense')
    expect(readStoredRole()).toBe(DEFAULT_ROLE)
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(readStoredRole()).toBe(DEFAULT_ROLE)
    spy.mockRestore()
    window.sessionStorage.clear()
  })

  it('labels the roles the way the control shows them', () => {
    expect(roleLabel('staff')).toBe('Staff')
    expect(roleLabel('general')).toBe('General')
    expect(roleLabel('zzz')).toBe(roleLabel(DEFAULT_ROLE))
  })

  it('defaults to Staff, the team working choice that matches the server config (0028), and keeps General selectable', () => {
    expect(DEFAULT_ROLE).toBe('staff')
    expect(normalizeRole(undefined)).toBe('staff')
    expect(normalizeRole('general')).toBe('general')
    window.sessionStorage.clear()
    expect(readStoredRole()).toBe('staff')
  })
})

describe('ask request', () => {
  it('sends the chosen role as user_role, and nothing extra when none is chosen', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockImplementation(async () => ok({ type: 'refusal', request_id: 'r' }))
    await askQuestion({ apiBase: 'https://x', question: 'Q?', rowId: 'a', userRole: 'manager', fetchImpl })
    await askQuestion({ apiBase: 'https://x', question: 'Q?', rowId: 'b', fetchImpl })
    const first = JSON.parse(String(fetchImpl.mock.calls[0][1]?.body))
    const second = JSON.parse(String(fetchImpl.mock.calls[1][1]?.body))
    expect(first.user_role).toBe('manager')
    expect('user_role' in second).toBe(false)
    expect(first.question).toBe('Q?')
  })
})

describe('answer row', () => {
  it('reads the lens label the server used (ROLE-9) and ignores malformed values', () => {
    const row = rowFromAskResponse({
      status: 200,
      id: 'r',
      payload: { type: 'answer', request_id: 'q', answer: 'Yes.', citations: [], routing: [], role: { key: 'staff', label: 'Staff' } },
    }) as AssistantAnswerRow
    expect(row.roleLabel).toBe('Staff')
    expect(roleLabelFromPayload({ label: 5 })).toBeNull()
    expect(roleLabelFromPayload('Manager')).toBeNull()
    expect(roleLabelFromPayload(null)).toBeNull()
    expect(roleLabelFromPayload({ label: '  ' })).toBeNull()
  })

  it('shows "Explained for" on an answer and nothing on a refusal', () => {
    const answer: AssistantAnswerRow = {
      kind: 'assistant_answer', id: 'a', requestId: 'q1', body: 'Yes.', citations: [], routing: [], roleLabel: 'Manager',
    }
    const { rerender } = render(
      <PilotTranscript rows={[answer]} pending={false} onFeedback={vi.fn()} onOpenCitation={vi.fn()} />,
    )
    expect(screen.getByTestId('role-badge').textContent).toBe('Explained for: Manager')
    rerender(
      <PilotTranscript
        rows={[{ ...answer, roleLabel: null }]}
        pending={false}
        onFeedback={vi.fn()}
        onOpenCitation={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('role-badge')).toBeNull()
  })
})

describe('RoleSelector', () => {
  it('is a labelled radio group with one selected role', () => {
    render(<RoleSelector value="staff" onChange={vi.fn()} />)
    expect(screen.getByRole('radiogroup', { name: 'Explain this for' })).toBeTruthy()
    const radios = screen.getAllByRole('radio')
    expect(radios.map((r) => r.textContent)).toEqual(['General', 'Staff', 'Manager'])
    expect(radios.map((r) => r.getAttribute('aria-checked'))).toEqual(['false', 'true', 'false'])
  })

  it('reports a click and arrow-key moves, and can be locked while a question is sent', () => {
    const onChange = vi.fn()
    const { rerender } = render(<RoleSelector value="general" onChange={onChange} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Manager' }))
    expect(onChange).toHaveBeenLastCalledWith('manager')
    fireEvent.keyDown(screen.getByRole('radio', { name: 'General' }), { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenLastCalledWith('manager')
    fireEvent.keyDown(screen.getByRole('radio', { name: 'General' }), { key: 'ArrowRight' })
    expect(onChange).toHaveBeenLastCalledWith('staff')
    rerender(<RoleSelector value="general" onChange={onChange} disabled />)
    expect(screen.getByRole('radio', { name: 'Staff' }).hasAttribute('disabled')).toBe(true)
  })
})
