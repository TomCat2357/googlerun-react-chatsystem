import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import LoginButton from '../Auth/LoginButton'

// Firebaseをモック
vi.mock('../../firebase/firebase', () => ({
  auth: {},
  googleProvider: {}
}))

// react-router-domをモック
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn()
}))

// Firebase Auth関数をモック
vi.mock('firebase/auth', () => ({
  signInWithPopup: vi.fn(),
  GoogleAuthProvider: vi.fn()
}))

describe('LoginButton', () => {
  const mockSignInWithPopup = vi.mocked(await import('firebase/auth')).signInWithPopup
  const mockNavigate = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(await import('react-router-dom')).useNavigate.mockReturnValue(mockNavigate)
  })

  it('ログインボタンが正しくレンダリングされる', () => {
    render(<LoginButton />)
    
    const button = screen.getByRole('button', { name: /Googleでログイン/i })
    expect(button).toBeInTheDocument()
    expect(button).toHaveTextContent('Googleでログイン')
  })

  it('ボタンクリック時にGoogleログインが実行される', async () => {
    const mockUser = { uid: 'test-uid', email: 'test@example.com' }
    mockSignInWithPopup.mockResolvedValue({ user: mockUser })

    render(<LoginButton />)
    
    const button = screen.getByRole('button', { name: /Googleでログイン/i })
    fireEvent.click(button)

    expect(mockSignInWithPopup).toHaveBeenCalled()
  })

  it('ログインエラー時にエラーメッセージが表示される', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockSignInWithPopup.mockRejectedValue(new Error('Login failed'))

    render(<LoginButton />)
    
    const button = screen.getByRole('button', { name: /Googleでログイン/i })
    fireEvent.click(button)

    // エラーログが出力されることを確認
    await vi.waitFor(() => {
      expect(consoleErrorSpy).toHaveBeenCalledWith('ログインエラー:', expect.any(Error))
    })

    consoleErrorSpy.mockRestore()
  })
})