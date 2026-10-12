import { render, screen } from '@testing-library/react'
import { ChannelBadge } from './Badges'

describe('ChannelBadge (spec 016)', () => {
  it('names the channel, never a phone number', () => {
    render(<ChannelBadge channel="whatsapp" />)
    expect(screen.getByText('WhatsApp')).toHaveAttribute('title', 'Habla con Sofi por WhatsApp')
  })

  it('labels the web chat', () => {
    render(<ChannelBadge channel="web" />)
    expect(screen.getByText('Chat web')).toBeInTheDocument()
  })
})
