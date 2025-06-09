import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ChatInput from '../Chat/ChatInput'

// Contextをモック
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { uid: 'test-uid' },
    loading: false
  })
}))

// Configをモック
vi.mock('../../../config', () => ({
  getServerConfig: () => ({
    MAX_IMAGES: 5,
    MAX_AUDIOS: 3,
    MAX_TEXTS: 10,
    MAX_IMAGE_SIZE: 5242880,
    MAX_LONG_EDGE: 1568
  })
}))

describe('ChatInput', () => {
  const mockProps = {
    input: '',
    setInput: vi.fn(),
    isProcessing: false,
    selectedFiles: [],
    addFiles: vi.fn(),
    sendMessage: vi.fn(),
    stopGeneration: vi.fn(),
    setErrorMessage: vi.fn(),
    maxLimits: {
      MAX_IMAGES: 5,
      MAX_AUDIO_FILES: 3,
      MAX_TEXT_FILES: 10,
      MAX_IMAGE_SIZE: 5242880,
      MAX_LONG_EDGE: 1568
    }
  }

  it('入力フィールドが正しくレンダリングされる', () => {
    render(<ChatInput {...mockProps} />)
    
    const textarea = screen.getByPlaceholderText('メッセージを入力...')
    expect(textarea).toBeInTheDocument()
  })

  it('テキスト入力時にsetInputが呼ばれる', () => {
    const mockSetInput = vi.fn()
    const propsWithMock = { ...mockProps, setInput: mockSetInput }

    render(<ChatInput {...propsWithMock} />)
    
    const textarea = screen.getByPlaceholderText('メッセージを入力...')
    fireEvent.change(textarea, { target: { value: 'テストメッセージ' } })
    
    expect(mockSetInput).toHaveBeenCalledWith('テストメッセージ')
  })
})