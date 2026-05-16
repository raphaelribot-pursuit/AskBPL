import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Modal } from './Modal'

describe('Modal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <Modal open={false} onClose={() => {}} footer={null}>
        body
      </Modal>,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders dialog, body, and footer when open', () => {
    render(
      <Modal open onClose={() => {}} footer={<span data-testid="ft">footer</span>}>
        body text
      </Modal>,
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('body text')).toBeInTheDocument()
    expect(screen.getByTestId('ft')).toHaveTextContent('footer')
  })
})
