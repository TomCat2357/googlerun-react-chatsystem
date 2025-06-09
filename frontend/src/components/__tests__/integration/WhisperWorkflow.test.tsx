import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import WhisperPage from '../../Whisper/WhisperPage'

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
    WHISPER_MAX_BYTES: 50 * 1024 * 1024,
    WHISPER_MAX_SECONDS: 300
  }),
  API_BASE_URL: 'http://localhost:3000/api'
}))

// requestIdUtilsのモック
vi.mock('../../../utils/requestIdUtils', () => ({
  generateRequestId: () => 'F123456789ABC'
}))

describe('Whisper統合ワークフロー', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    
    // APIレスポンスのモック設定
    global.fetch = vi.fn()
      .mockImplementationOnce(() => Promise.resolve({
        ok: true,
        text: () => Promise.resolve('gs://bucket/uploaded-file.wav')
      }))
      .mockImplementationOnce(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          jobId: 'job-123',
          fileHash: 'hash-456'
        })
      }))
      .mockImplementationOnce(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          jobs: [{
            jobId: 'job-123',
            fileHash: 'hash-456',
            filename: 'test.wav',
            status: 'completed',
            createdAt: '2024-01-01T00:00:00Z'
          }]
        })
      }))
  })

  it('音声ファイルアップロードから結果表示までの完全ワークフロー', async () => {
    render(<WhisperPage />)

    // 1. 音声アップロードタブが表示されることを確認
    expect(screen.getByText('音声アップロード')).toBeInTheDocument()
    
    // 2. ファイルを選択
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['test audio'], 'test.wav', { type: 'audio/wav' })
    Object.defineProperty(mockFile, 'size', { value: 1024 * 1024 })

    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    // 3. ファイル情報が表示されることを確認
    await waitFor(() => {
      expect(screen.getByText('test.wav')).toBeInTheDocument()
    })

    // 4. メタデータを入力
    const descriptionInput = screen.getByLabelText(/説明/)
    fireEvent.change(descriptionInput, { target: { value: 'テスト音声ファイル' } })

    // 5. アップロードボタンをクリック
    const uploadButton = screen.getByText('文字起こし開始')
    fireEvent.click(uploadButton)

    // 6. アップロード成功後、ジョブ一覧タブに自動切り替え
    await waitFor(() => {
      expect(screen.getByText('処理結果一覧')).toBeInTheDocument()
    })

    // 7. ジョブ一覧にアップロードしたファイルが表示される
    await waitFor(() => {
      expect(screen.getByText('test.wav')).toBeInTheDocument()
      expect(screen.getByText('完了')).toBeInTheDocument()
    })
  })

  it('エラーハンドリングが正しく動作する', async () => {
    // エラーレスポンスのモック
    global.fetch = vi.fn().mockRejectedValue(new Error('Network Error'))

    render(<WhisperPage />)

    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['test audio'], 'test.wav', { type: 'audio/wav' })
    Object.defineProperty(mockFile, 'size', { value: 1024 * 1024 })

    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    const uploadButton = screen.getByText('文字起こし開始')
    fireEvent.click(uploadButton)

    // エラーメッセージが表示される
    await waitFor(() => {
      expect(screen.getByText(/エラー/)).toBeInTheDocument()
    })
  })

  it('ファイルサイズ制限チェックが動作する', async () => {
    render(<WhisperPage />)

    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const largeFile = new File(['large audio content'], 'large.wav', { type: 'audio/wav' })
    Object.defineProperty(largeFile, 'size', { value: 60 * 1024 * 1024 }) // 60MB

    fireEvent.change(fileInput, { target: { files: [largeFile] } })

    // ファイルサイズエラーが表示される
    await waitFor(() => {
      expect(screen.getByText(/ファイルサイズが大きすぎます/)).toBeInTheDocument()
    })
  })

  it('ジョブのキャンセル機能が動作する', async () => {
    // 処理中のジョブを含むレスポンス
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        jobs: [{
          jobId: 'job-processing',
          fileHash: 'hash-processing',
          filename: 'processing.wav',
          status: 'processing',
          createdAt: '2024-01-01T00:00:00Z'
        }]
      })
    })

    render(<WhisperPage />)

    // 処理結果一覧タブに切り替え
    fireEvent.click(screen.getByText('処理結果一覧'))

    // キャンセルボタンが表示される
    await waitFor(() => {
      expect(screen.getByText('キャンセル')).toBeInTheDocument()
    })

    // キャンセルボタンをクリック
    const cancelButton = screen.getByText('キャンセル')
    fireEvent.click(cancelButton)

    // 確認ダイアログをモック（実際の実装に応じて調整）
    window.confirm = vi.fn().mockReturnValue(true)

    // キャンセルAPIが呼ばれることを確認
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/cancel'),
      expect.objectContaining({
        method: 'POST'
      })
    )
  })

  it('言語設定とメタデータが正しく処理される', async () => {
    render(<WhisperPage />)

    // 言語を英語に変更
    const languageSelect = screen.getByLabelText(/言語/)
    fireEvent.change(languageSelect, { target: { value: 'en' } })

    // 初期プロンプトを入力
    const promptInput = screen.getByLabelText(/初期プロンプト/)
    fireEvent.change(promptInput, { target: { value: 'This is a test prompt' } })

    // ファイルを選択
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['test audio'], 'test.wav', { type: 'audio/wav' })
    Object.defineProperty(mockFile, 'size', { value: 1024 * 1024 })

    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    const uploadButton = screen.getByText('文字起こし開始')
    fireEvent.click(uploadButton)

    // APIリクエストに言語とプロンプトが含まれることを確認
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('en'),
          body: expect.stringContaining('This is a test prompt')
        })
      )
    })
  })

  it('話者数設定が正しく処理される', async () => {
    render(<WhisperPage />)

    // 話者数を固定に設定
    const speakerCountRadio = screen.getByLabelText(/固定/)
    fireEvent.click(speakerCountRadio)

    // 話者数を3に設定
    const speakerInput = screen.getByLabelText(/話者数/)
    fireEvent.change(speakerInput, { target: { value: '3' } })

    // ファイルを選択してアップロード
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['test audio'], 'test.wav', { type: 'audio/wav' })
    Object.defineProperty(mockFile, 'size', { value: 1024 * 1024 })

    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    const uploadButton = screen.getByText('文字起こし開始')
    fireEvent.click(uploadButton)

    // 話者数設定がAPIリクエストに含まれることを確認
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('3')
        })
      )
    })
  })
})