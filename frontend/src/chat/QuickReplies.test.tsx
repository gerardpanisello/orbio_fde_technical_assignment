import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QuickReplies } from './QuickReplies'

const replies = [
  { id: 'yes', label: 'Sí' },
  { id: 'no', label: 'No' },
]

describe('QuickReplies', () => {
  it('renders one chip per reply and sends the tapped label', async () => {
    const onPick = vi.fn()
    render(<QuickReplies replies={replies} onPick={onPick} label="Respuestas rápidas" />)

    expect(screen.getAllByRole('button')).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', { name: 'Sí' }))
    expect(onPick).toHaveBeenCalledWith('Sí')
  })

  it('renders nothing without replies', () => {
    const { container } = render(<QuickReplies replies={[]} onPick={vi.fn()} label="x" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('cannot be tapped while the agent is typing', async () => {
    const onPick = vi.fn()
    render(<QuickReplies replies={replies} onPick={onPick} disabled label="x" />)
    await userEvent.click(screen.getByRole('button', { name: 'No' }))
    expect(onPick).not.toHaveBeenCalled()
  })
})
