import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import LoginPage from '../LoginPage'

// Firebase認証のモック
const mockSignInWithEmailAndPassword = vi.fn()
const mockSignInWithPopup = vi.fn()
const mockCreateUserWithEmailAndPassword = vi.fn()

vi.mock('firebase/auth', () => ({
  signInWithEmailAndPassword: mockSignInWithEmailAndPassword,
  signInWithPopup: mockSignInWithPopup,
  createUserWithEmailAndPassword: mockCreateUserWithEmailAndPassword,
  GoogleAuthProvider: vi.fn()
}))

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: null,
    loading: false,
    error: null
  })
}))

vi.mock('../../../firebase/firebase', () => ({
  auth: {},
  googleProvider: {}
}))

const MockLoginPageWithRouter = () => (
  <BrowserRouter>
    <LoginPage />
  </BrowserRouter>
)

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSignInWithEmailAndPassword.mockResolvedValue({
      user: { uid: 'test-uid', email: 'test@example.com' }
    })
    mockSignInWithPopup.mockResolvedValue({
      user: { uid: 'test-uid', email: 'test@example.com' }
    })
    mockCreateUserWithEmailAndPassword.mockResolvedValue({
      user: { uid: 'test-uid', email: 'test@example.com' }
    })
  })

  it('ログインページが正しくレンダリングされる', () => {
    render(<MockLoginPageWithRouter />)
    
    expect(screen.getByText(/ログイン/)).toBeInTheDocument()
    expect(screen.getByLabelText(/メールアドレス/)).toBeInTheDocument()
    expect(screen.getByLabelText(/パスワード/)).toBeInTheDocument()
  })

  it('メールアドレス入力が動作する', () => {
    render(<MockLoginPageWithRouter />)
    
    const emailInput = screen.getByLabelText(/メールアドレス/)
    const testEmail = 'test@example.com'
    
    fireEvent.change(emailInput, { target: { value: testEmail } })
    expect(emailInput).toHaveValue(testEmail)
  })

  it('パスワード入力が動作する', () => {
    render(<MockLoginPageWithRouter />)
    
    const passwordInput = screen.getByLabelText(/パスワード/)
    const testPassword = 'testPassword123'
    
    fireEvent.change(passwordInput, { target: { value: testPassword } })
    expect(passwordInput).toHaveValue(testPassword)
  })

  it('ログインフォーム送信が動作する', async () => {
    render(<MockLoginPageWithRouter />)
    
    const emailInput = screen.getByLabelText(/メールアドレス/)
    const passwordInput = screen.getByLabelText(/パスワード/)
    const loginButton = screen.getByRole('button', { name: /ログイン/ })
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(loginButton)

    await waitFor(() => {
      expect(mockSignInWithEmailAndPassword).toHaveBeenCalledWith(
        {},
        'test@example.com',
        'password123'
      )
    })
  })

  it('Googleログインボタンが動作する', async () => {
    render(<MockLoginPageWithRouter />)
    
    const googleLoginButton = screen.getByText(/Googleでログイン/)
    fireEvent.click(googleLoginButton)

    await waitFor(() => {
      expect(mockSignInWithPopup).toHaveBeenCalled()
    })
  })

  it('フォームバリデーションが動作する', async () => {
    render(<MockLoginPageWithRouter />)
    
    const loginButton = screen.getByRole('button', { name: /ログイン/ })
    
    // 空フォームで送信
    fireEvent.click(loginButton)
    
    await waitFor(() => {
      expect(screen.getByText(/メールアドレスを入力してください/)).toBeInTheDocument()
    })
  })

  it('無効なメールアドレスでバリデーションエラーが表示される', async () => {
    render(<MockLoginPageWithRouter />)
    
    const emailInput = screen.getByLabelText(/メールアドレス/)
    const loginButton = screen.getByRole('button', { name: /ログイン/ })
    
    fireEvent.change(emailInput, { target: { value: 'invalid-email' } })
    fireEvent.click(loginButton)
    
    await waitFor(() => {
      expect(screen.getByText(/有効なメールアドレスを入力してください/)).toBeInTheDocument()
    })
  })

  it('パスワードの強度チェックが動作する', async () => {
    render(<MockLoginPageWithRouter />)
    
    const passwordInput = screen.getByLabelText(/パスワード/)
    
    // 弱いパスワード
    fireEvent.change(passwordInput, { target: { value: '123' } })
    
    await waitFor(() => {
      expect(screen.getByText(/パスワードは8文字以上で入力してください/)).toBeInTheDocument()
    })
  })

  it('パスワード表示切り替えが動作する', () => {
    render(<MockLoginPageWithRouter />)
    
    const passwordInput = screen.getByLabelText(/パスワード/)
    const toggleButton = screen.getByRole('button', { name: /パスワードを表示/ })
    
    expect(passwordInput.type).toBe('password')
    
    fireEvent.click(toggleButton)
    expect(passwordInput.type).toBe('text')
    
    fireEvent.click(toggleButton)
    expect(passwordInput.type).toBe('password')
  })

  it('新規登録モードへの切り替えが動作する', () => {
    render(<MockLoginPageWithRouter />)
    
    const signupLink = screen.getByText(/新規登録/)
    fireEvent.click(signupLink)
    
    expect(screen.getByText(/アカウント作成/)).toBeInTheDocument()
  })

  it('新規登録フォームが動作する', async () => {
    render(<MockLoginPageWithRouter />)
    
    // 新規登録モードに切り替え
    const signupLink = screen.getByText(/新規登録/)
    fireEvent.click(signupLink)
    
    const emailInput = screen.getByLabelText(/メールアドレス/)
    const passwordInput = screen.getByLabelText(/パスワード/)
    const signupButton = screen.getByRole('button', { name: /アカウント作成/ })
    
    fireEvent.change(emailInput, { target: { value: 'newuser@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'newpassword123' } })
    fireEvent.click(signupButton)

    await waitFor(() => {
      expect(mockCreateUserWithEmailAndPassword).toHaveBeenCalledWith(
        {},
        'newuser@example.com',
        'newpassword123'
      )
    })
  })

  it('ログインエラーが適切に表示される', async () => {
    mockSignInWithEmailAndPassword.mockRejectedValue(
      new Error('Invalid credentials')
    )

    render(<MockLoginPageWithRouter />)
    
    const emailInput = screen.getByLabelText(/メールアドレス/)
    const passwordInput = screen.getByLabelText(/パスワード/)
    const loginButton = screen.getByRole('button', { name: /ログイン/ })
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'wrongpassword' } })
    fireEvent.click(loginButton)

    await waitFor(() => {
      expect(screen.getByText(/ログインに失敗しました/)).toBeInTheDocument()
    })
  })

  it('パスワードリセット機能が動作する', async () => {
    render(<MockLoginPageWithRouter />)
    
    const forgotPasswordLink = screen.getByText(/パスワードを忘れた方/)
    fireEvent.click(forgotPasswordLink)
    
    expect(screen.getByText(/パスワードリセット/)).toBeInTheDocument()
    
    const emailInput = screen.getByLabelText(/メールアドレス/)
    const resetButton = screen.getByRole('button', { name: /リセットメール送信/ })
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.click(resetButton)
    
    await waitFor(() => {
      expect(screen.getByText(/リセットメールを送信しました/)).toBeInTheDocument()
    })
  })

  it('ローディング状態が正しく表示される', async () => {
    // ログイン処理を遅延させる
    mockSignInWithEmailAndPassword.mockReturnValue(
      new Promise(resolve => setTimeout(resolve, 100))
    )

    render(<MockLoginPageWithRouter />)
    
    const emailInput = screen.getByLabelText(/メールアドレス/)
    const passwordInput = screen.getByLabelText(/パスワード/)
    const loginButton = screen.getByRole('button', { name: /ログイン/ })
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(loginButton)

    // ローディング表示の確認
    expect(screen.getByText(/ログイン中/)).toBeInTheDocument()
    expect(loginButton).toBeDisabled()
  })

  it('利用規約とプライバシーポリシーのリンクが表示される', () => {
    render(<MockLoginPageWithRouter />)
    
    expect(screen.getByText(/利用規約/)).toBeInTheDocument()
    expect(screen.getByText(/プライバシーポリシー/)).toBeInTheDocument()
  })

  it('アクセシビリティ属性が適切に設定されている', () => {
    render(<MockLoginPageWithRouter />)
    
    // フォーム要素のラベル付け
    const emailInput = screen.getByLabelText(/メールアドレス/)
    const passwordInput = screen.getByLabelText(/パスワード/)
    
    expect(emailInput).toHaveAttribute('type', 'email')
    expect(passwordInput).toHaveAttribute('type', 'password')
    
    // 必須フィールドのマーク
    expect(emailInput).toHaveAttribute('required')
    expect(passwordInput).toHaveAttribute('required')
    
    // エラーメッセージとの関連付け
    const errorElements = screen.queryAllByRole('alert')
    errorElements.forEach(element => {
      expect(element).toBeInTheDocument()
    })
  })

  it('レスポンシブデザインが適用されている', () => {
    const { container } = render(<MockLoginPageWithRouter />)
    
    // レスポンシブクラスの確認
    expect(container.querySelector('[class*="max-w"]')).toBeInTheDocument()
    expect(container.querySelector('[class*="mx-auto"]')).toBeInTheDocument()
  })
})