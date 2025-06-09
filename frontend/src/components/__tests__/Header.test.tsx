import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import Header from '../Header/Header'

// AuthContextをモック
const mockUseAuth = vi.fn()
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth()
}))

// テスト用ラッパー
const TestWrapper = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
)

describe('Header', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })


  it('ログイン済みユーザーの場合、ログアウトボタンが表示される', () => {
    mockUseAuth.mockReturnValue({
      user: { uid: 'test-uid', email: 'test@example.com' },
      loading: false,
      signOut: vi.fn()
    })

    render(
      <TestWrapper>
        <Header />
      </TestWrapper>
    )

    expect(screen.getByRole('button', { name: /ログアウト/i })).toBeInTheDocument()
  })

  it('未ログインユーザーの場合、ログインボタンが表示される', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      loading: false,
      signOut: vi.fn()
    })

    render(
      <TestWrapper>
        <Header />
      </TestWrapper>
    )

    expect(screen.getByRole('button', { name: /ログイン/i })).toBeInTheDocument()
  })

  it('ローディング中はローディング表示がされる', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      loading: true,
      signOut: vi.fn()
    })

    render(
      <TestWrapper>
        <Header />
      </TestWrapper>
    )

    expect(screen.getByText(/読み込み中/i)).toBeInTheDocument()
  })

  it('ログアウトボタンをクリックするとsignOutが呼ばれる', () => {
    const mockSignOut = vi.fn()
    mockUseAuth.mockReturnValue({
      user: { uid: 'test-uid', email: 'test@example.com' },
      loading: false,
      signOut: mockSignOut
    })

    render(
      <TestWrapper>
        <Header />
      </TestWrapper>
    )

    const logoutButton = screen.getByRole('button', { name: /ログアウト/i })
    fireEvent.click(logoutButton)

    expect(mockSignOut).toHaveBeenCalled()
  })
})