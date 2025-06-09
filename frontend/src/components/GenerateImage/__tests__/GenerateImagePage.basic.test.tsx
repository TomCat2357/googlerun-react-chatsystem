import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import GenerateImagePage from '../GenerateImagePage'

// Firebase認証のモック
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: { uid: 'test-uid' },
    loading: false
  })
}))

// useTokenのモック
vi.mock('../../../hooks/useToken', () => ({
  useToken: () => 'mock-token'
}))

// Configのモック
vi.mock('../../../config', () => ({
  getServerConfig: () => ({
    MAX_IMAGES: 5,
    MAX_IMAGE_SIZE: 5242880,
    MAX_LONG_EDGE: 1568
  }),
  API_BASE_URL: 'http://localhost:3000/api'
}))

describe('GenerateImagePage Basic Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('ページが正しくレンダリングされる', () => {
    render(<GenerateImagePage />)
    
    // 基本的な要素の存在確認
    expect(screen.getByText('画像生成')).toBeInTheDocument()
    expect(screen.getByText('生成設定')).toBeInTheDocument()
    expect(screen.getByText('生成結果')).toBeInTheDocument()
  })

  it('プロンプト入力フィールドが存在する', () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/生成したい画像の詳細な説明を入力してください/)
    expect(promptInput).toBeInTheDocument()
    expect(promptInput.tagName).toBe('TEXTAREA')
  })

  it('生成ボタンが存在する', () => {
    render(<GenerateImagePage />)
    
    const generateButton = screen.getByText('画像を生成')
    expect(generateButton).toBeInTheDocument()
    expect(generateButton.tagName).toBe('BUTTON')
  })

  it('フォーム要素が正しく表示される', () => {
    render(<GenerateImagePage />)
    
    // 各設定項目の確認
    expect(screen.getByText('プロンプト (必須)')).toBeInTheDocument()
    expect(screen.getByText('ネガティブプロンプト (省略可)')).toBeInTheDocument()
    expect(screen.getByText('シード (省略可)')).toBeInTheDocument()
    expect(screen.getByText('モデル')).toBeInTheDocument()
    expect(screen.getByText('生成枚数')).toBeInTheDocument()
    expect(screen.getByText('アスペクト比')).toBeInTheDocument()
  })

  it('プロンプト入力が動作する', () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/生成したい画像の詳細な説明を入力してください/)
    const testPrompt = '美しい夕焼けの風景'
    
    fireEvent.change(promptInput, { target: { value: testPrompt } })
    expect(promptInput).toHaveValue(testPrompt)
  })

  it('ネガティブプロンプト入力が動作する', () => {
    render(<GenerateImagePage />)
    
    const negativePromptInput = screen.getByPlaceholderText(/生成したくない要素を入力してください/)
    const testNegativePrompt = 'blurry, low quality'
    
    fireEvent.change(negativePromptInput, { target: { value: testNegativePrompt } })
    expect(negativePromptInput).toHaveValue(testNegativePrompt)
  })

  it('シード値入力が動作する', () => {
    render(<GenerateImagePage />)
    
    const seedInput = screen.getByPlaceholderText(/空欄の場合はランダム/)
    const testSeed = '12345'
    
    fireEvent.change(seedInput, { target: { value: testSeed } })
    expect(seedInput).toHaveValue(testSeed)
  })

  it('初期状態でボタンが無効化されている', () => {
    render(<GenerateImagePage />)
    
    const generateButton = screen.getByText('画像を生成')
    expect(generateButton).toBeDisabled()
  })

  it('生成結果エリアが初期表示される', () => {
    render(<GenerateImagePage />)
    
    expect(screen.getByText('画像が生成されていません')).toBeInTheDocument()
    expect(screen.getByText('左側のフォームからプロンプトを入力して画像を生成してください')).toBeInTheDocument()
  })

  it('ウォーターマーク設定が表示される', () => {
    render(<GenerateImagePage />)
    
    const watermarkCheckbox = screen.getByText('ウォーターマークを追加').closest('label')?.querySelector('input')
    expect(watermarkCheckbox).toBeInTheDocument()
    expect(watermarkCheckbox?.type).toBe('checkbox')
  })

  it('各セレクト要素が表示される', () => {
    render(<GenerateImagePage />)
    
    // セレクトボックスの存在確認
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThan(0)
    
    // 特定のセレクト要素の確認
    expect(screen.getByText('モデル').closest('div')?.querySelector('select')).toBeInTheDocument()
    expect(screen.getByText('生成枚数').closest('div')?.querySelector('select')).toBeInTheDocument()
    expect(screen.getByText('アスペクト比').closest('div')?.querySelector('select')).toBeInTheDocument()
  })

  it('レスポンシブレイアウトのクラスが適用されている', () => {
    const { container } = render(<GenerateImagePage />)
    
    // グリッドレイアウトの確認
    const gridContainer = container.querySelector('.grid.grid-cols-1.md\\:grid-cols-3')
    expect(gridContainer).toBeInTheDocument()
    
    // カラムスパンの確認
    const leftPanel = container.querySelector('.md\\:col-span-1')
    const rightPanel = container.querySelector('.md\\:col-span-2')
    
    expect(leftPanel).toBeInTheDocument()
    expect(rightPanel).toBeInTheDocument()
  })

  it('ダークテーマのスタイルが適用されている', () => {
    const { container } = render(<GenerateImagePage />)
    
    // 背景色の確認
    expect(container.querySelector('.bg-dark-primary')).toBeInTheDocument()
    expect(container.querySelector('.bg-gray-800')).toBeInTheDocument()
    
    // テキスト色の確認
    expect(container.querySelector('.text-gray-100')).toBeInTheDocument()
    expect(container.querySelector('.text-gray-300')).toBeInTheDocument()
  })
})