import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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

// requestIdUtilsのモック
vi.mock('../../../utils/requestIdUtils', () => ({
  generateRequestId: () => 'F123456789ABC'
}))

describe('GenerateImagePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    
    // 基本的なAPIレスポンスのモック
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        images: [
          {
            url: 'https://example.com/generated-image.png',
            prompt: 'テスト画像生成プロンプト',
            seed: 12345,
            timestamp: '2024-01-01T00:00:00Z'
          }
        ],
        request_id: 'F123456789ABC'
      })
    })
  })

  it('ページが正しくレンダリングされる', () => {
    render(<GenerateImagePage />)
    
    expect(screen.getByText('画像生成')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/生成したい画像の詳細な説明を入力してください/)).toBeInTheDocument()
    expect(screen.getByText('画像を生成')).toBeInTheDocument()
  })

  it('プロンプト入力が正しく動作する', () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/生成したい画像の詳細な説明を入力してください/)
    const testPrompt = '美しい夕焼けの風景'
    
    fireEvent.change(promptInput, { target: { value: testPrompt } })
    expect(promptInput).toHaveValue(testPrompt)
  })

  it('画像生成リクエストが正しく送信される', async () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/生成したい画像の詳細な説明を入力してください/)
    const generateButton = screen.getByText('画像を生成')
    
    fireEvent.change(promptInput, { 
      target: { value: '美しい夕焼けの風景' } 
    })
    fireEvent.click(generateButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/image'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'Authorization': 'Bearer mock-token',
            'X-Request-ID': 'F123456789ABC'
          }),
          body: expect.stringContaining('美しい夕焼けの風景')
        })
      )
    })
  })

  it('生成された画像が正しく表示される', async () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const generateButton = screen.getByText('画像生成')
    
    fireEvent.change(promptInput, { 
      target: { value: '美しい夕焼けの風景' } 
    })
    fireEvent.click(generateButton)

    await waitFor(() => {
      expect(screen.getByAltText(/生成された画像/)).toBeInTheDocument()
    })

    const generatedImage = screen.getByAltText(/生成された画像/)
    expect(generatedImage).toHaveAttribute('src', 'https://example.com/generated-image.png')
  })

  it('プロンプトの長さ制限チェックが動作する', () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const longPrompt = 'あ'.repeat(1001) // 1001文字の長いプロンプト
    
    fireEvent.change(promptInput, { target: { value: longPrompt } })
    
    expect(screen.getByText(/プロンプトが長すぎます/)).toBeInTheDocument()
  })

  it('空のプロンプトでエラーが表示される', () => {
    render(<GenerateImagePage />)
    
    const generateButton = screen.getByText('画像生成')
    fireEvent.click(generateButton)
    
    expect(screen.getByText(/プロンプトを入力してください/)).toBeInTheDocument()
  })

  it('API エラーが適切に処理される', async () => {
    // エラーレスポンスのモック
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({
        detail: '画像生成に失敗しました'
      })
    })

    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const generateButton = screen.getByText('画像生成')
    
    fireEvent.change(promptInput, { 
      target: { value: '有効なプロンプト' } 
    })
    fireEvent.click(generateButton)

    await waitFor(() => {
      expect(screen.getByText(/画像生成に失敗しました/)).toBeInTheDocument()
    })
  })

  it('ローディング状態が正しく表示される', async () => {
    // 遅延レスポンスのモック
    global.fetch = vi.fn().mockImplementation(() => 
      new Promise(resolve => {
        setTimeout(() => {
          resolve({
            ok: true,
            json: () => Promise.resolve({
              images: [{
                url: 'https://example.com/generated-image.png',
                prompt: 'テスト画像生成プロンプト'
              }]
            })
          })
        }, 100)
      })
    )

    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const generateButton = screen.getByText('画像生成')
    
    fireEvent.change(promptInput, { 
      target: { value: '美しい夕焼けの風景' } 
    })
    fireEvent.click(generateButton)

    // ローディング状態の確認
    expect(screen.getByText(/生成中/)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.queryByText(/生成中/)).not.toBeInTheDocument()
    })
  })

  it('画像のダウンロード機能が動作する', async () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const generateButton = screen.getByText('画像生成')
    
    fireEvent.change(promptInput, { 
      target: { value: '美しい夕焼けの風景' } 
    })
    fireEvent.click(generateButton)

    await waitFor(() => {
      expect(screen.getByAltText(/生成された画像/)).toBeInTheDocument()
    })

    const downloadButton = screen.getByText(/ダウンロード/)
    expect(downloadButton).toBeInTheDocument()
    
    fireEvent.click(downloadButton)
    // ダウンロード機能の動作確認（実際のファイルダウンロードはモック）
  })

  it('画像生成パラメータの設定が反映される', () => {
    render(<GenerateImagePage />)
    
    // サイズ設定
    const sizeSelect = screen.getByLabelText(/画像サイズ/)
    fireEvent.change(sizeSelect, { target: { value: '1024x1024' } })
    expect(sizeSelect).toHaveValue('1024x1024')
    
    // 品質設定
    const qualitySelect = screen.getByLabelText(/品質/)
    fireEvent.change(qualitySelect, { target: { value: 'high' } })
    expect(qualitySelect).toHaveValue('high')
  })

  it('複数画像生成が正しく動作する', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        images: [
          {
            url: 'https://example.com/generated-image-1.png',
            prompt: 'テスト画像生成プロンプト'
          },
          {
            url: 'https://example.com/generated-image-2.png',
            prompt: 'テスト画像生成プロンプト'
          }
        ]
      })
    })

    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const countSelect = screen.getByLabelText(/生成数/)
    const generateButton = screen.getByText('画像生成')
    
    fireEvent.change(promptInput, { 
      target: { value: '美しい夕焼けの風景' } 
    })
    fireEvent.change(countSelect, { target: { value: '2' } })
    fireEvent.click(generateButton)

    await waitFor(() => {
      const images = screen.getAllByAltText(/生成された画像/)
      expect(images).toHaveLength(2)
    })
  })

  it('履歴機能が正しく動作する', async () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const generateButton = screen.getByText('画像生成')
    
    // 最初の画像生成
    fireEvent.change(promptInput, { 
      target: { value: '美しい夕焼けの風景' } 
    })
    fireEvent.click(generateButton)

    await waitFor(() => {
      expect(screen.getByAltText(/生成された画像/)).toBeInTheDocument()
    })

    // 履歴タブに切り替え
    fireEvent.click(screen.getByText('履歴'))
    
    // 履歴に生成した画像が表示される
    await waitFor(() => {
      expect(screen.getByText('美しい夕焼けの風景')).toBeInTheDocument()
    })
  })

  it('ネガティブプロンプト機能が動作する', async () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const negativePromptInput = screen.getByPlaceholderText(/除外したい要素/)
    const generateButton = screen.getByText('画像生成')
    
    fireEvent.change(promptInput, { 
      target: { value: '美しい風景' } 
    })
    fireEvent.change(negativePromptInput, { 
      target: { value: 'blurry, low quality' } 
    })
    fireEvent.click(generateButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/image'),
        expect.objectContaining({
          body: expect.stringMatching(/blurry, low quality/)
        })
      )
    })
  })

  it('シード値の設定が反映される', async () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const seedInput = screen.getByLabelText(/シード値/)
    const generateButton = screen.getByText('画像生成')
    
    fireEvent.change(promptInput, { 
      target: { value: '美しい風景' } 
    })
    fireEvent.change(seedInput, { 
      target: { value: '42' } 
    })
    fireEvent.click(generateButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/image'),
        expect.objectContaining({
          body: expect.stringMatching(/42/)
        })
      )
    })
  })

  it('スタイルプリセットの適用が動作する', async () => {
    render(<GenerateImagePage />)
    
    const promptInput = screen.getByPlaceholderText(/画像の説明を入力/)
    const styleSelect = screen.getByLabelText(/スタイル/)
    const generateButton = screen.getByText('画像生成')
    
    fireEvent.change(promptInput, { 
      target: { value: '美しい風景' } 
    })
    fireEvent.change(styleSelect, { target: { value: 'anime' } })
    fireEvent.click(generateButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/image'),
        expect.objectContaining({
          body: expect.stringMatching(/anime/)
        })
      )
    })
  })
})