import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext'
import { User } from 'firebase/auth'

// Firebaseをモック
vi.mock('../../firebase/firebase', () => ({
  auth: {
    onAuthStateChanged: vi.fn(),
    signOut: vi.fn()
  }
}))

// テスト用コンポーネント
const TestComponent = () => {
  const { user, loading, signOut } = useAuth()
  
  if (loading) return <div>Loading...</div>
  
  return (
    <div>
      <div data-testid="user-status">
        {user ? `Logged in: ${user.uid}` : 'Not logged in'}
      </div>
      <button onClick={signOut} data-testid="signout-btn">
        Sign Out
      </button>
    </div>
  )
}

describe('AuthContext', () => {
  const mockAuth = vi.mocked(await import('../../firebase/firebase')).auth
  
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('ローディング状態が正しく表示される', () => {
    mockAuth.onAuthStateChanged.mockImplementation((callback) => {
      // コールバックを即座実行しない（ローディング状態をシミュレート）
      return () => {}
    })

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    )

    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('ログイン済みユーザーが正しく表示される', async () => {
    const mockUser = { uid: 'test-user-123' } as User

    mockAuth.onAuthStateChanged.mockImplementation((callback) => {
      callback(mockUser)
      return () => {}
    })

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('user-status')).toHaveTextContent('Logged in: test-user-123')
    })
  })

  it('ログアウト機能が正しく動作する', async () => {
    const mockUser = { uid: 'test-user-123' } as User
    mockAuth.signOut.mockResolvedValue()

    mockAuth.onAuthStateChanged.mockImplementation((callback) => {
      callback(mockUser)
      return () => {}
    })

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('signout-btn')).toBeInTheDocument()
    })

    const signOutBtn = screen.getByTestId('signout-btn')
    signOutBtn.click()

    expect(mockAuth.signOut).toHaveBeenCalled()
  })
})