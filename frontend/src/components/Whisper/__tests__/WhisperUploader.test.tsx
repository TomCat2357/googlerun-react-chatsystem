import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import WhisperUploader from '../WhisperUploader'

// Firebase認証のモック
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: { uid: 'test-uid' },
    loading: false
  })
}))

// Configのモック
vi.mock('../../../config', () => ({
  getServerConfig: () => ({
    WHISPER_MAX_BYTES: 50 * 1024 * 1024, // 50MB
    WHISPER_MAX_SECONDS: 300 // 5分
  }),
  API_BASE_URL: 'http://localhost:3000/api'
}))

// fetch APIのモック
global.fetch = vi.fn()

describe('WhisperUploader', () => {
  const mockProps = {
    onAudioDataChange: vi.fn(),
    onAudioInfoChange: vi.fn(),
    onDescriptionChange: vi.fn(),
    onRecordingDateChange: vi.fn(),
    onTagsChange: vi.fn(),
    onLanguageChange: vi.fn(),
    onInitialPromptChange: vi.fn()
  }

  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('gs://bucket/file.wav')
    })
  })

  it('ファイル選択UIが正しくレンダリングされる', () => {
    render(<WhisperUploader {...mockProps} />)
    
    expect(screen.getByText(/音声ファイル選択/)).toBeInTheDocument()
    expect(screen.getByText(/対応形式: WAV, MP3, M4A/)).toBeInTheDocument()
  })

  it('ファイル選択時に適切な処理が実行される', async () => {
    render(<WhisperUploader {...mockProps} />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['test audio content'], 'test.wav', {
      type: 'audio/wav'
    })

    // ファイルサイズをモック
    Object.defineProperty(mockFile, 'size', { value: 1024 * 1024 }) // 1MB

    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    await waitFor(() => {
      expect(mockProps.onAudioInfoChange).toHaveBeenCalledWith(
        expect.objectContaining({
          fileName: 'test.wav',
          fileSize: 1024 * 1024
        })
      )
    })
  })

  it('大きすぎるファイルが選択された場合にエラーが表示される', async () => {
    render(<WhisperUploader {...mockProps} />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['large audio content'], 'large.wav', {
      type: 'audio/wav'
    })

    // 制限を超えるファイルサイズをモック
    Object.defineProperty(mockFile, 'size', { value: 60 * 1024 * 1024 }) // 60MB

    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    await waitFor(() => {
      expect(screen.getByText(/ファイルサイズが大きすぎます/)).toBeInTheDocument()
    })
  })

  it('対応していない形式のファイルが選択された場合にエラーが表示される', async () => {
    render(<WhisperUploader {...mockProps} />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['text content'], 'test.txt', {
      type: 'text/plain'
    })

    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    await waitFor(() => {
      expect(screen.getByText(/対応していないファイル形式です/)).toBeInTheDocument()
    })
  })

  it('ドラッグアンドドロップが正しく動作する', async () => {
    render(<WhisperUploader {...mockProps} />)
    
    const dropZone = screen.getByTestId('drop-zone')
    const mockFile = new File(['test audio content'], 'test.mp3', {
      type: 'audio/mp3'
    })

    Object.defineProperty(mockFile, 'size', { value: 1024 * 1024 })

    // ドラッグオーバーイベント
    fireEvent.dragOver(dropZone, {
      dataTransfer: {
        files: [mockFile]
      }
    })

    // ドロップイベント
    fireEvent.drop(dropZone, {
      dataTransfer: {
        files: [mockFile]
      }
    })

    await waitFor(() => {
      expect(mockProps.onAudioInfoChange).toHaveBeenCalledWith(
        expect.objectContaining({
          fileName: 'test.mp3',
          fileSize: 1024 * 1024
        })
      )
    })
  })

  it('アップロード中は適切な表示になる', async () => {
    // fetchを遅延レスポンスにモック
    global.fetch = vi.fn().mockImplementation(() => 
      new Promise(resolve => setTimeout(() => resolve({
        ok: true,
        text: () => Promise.resolve('gs://bucket/file.wav')
      }), 100))
    )

    render(<WhisperUploader {...mockProps} />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['test audio content'], 'test.wav', {
      type: 'audio/wav'
    })

    Object.defineProperty(mockFile, 'size', { value: 1024 * 1024 })
    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    // アップロード中の表示をチェック
    await waitFor(() => {
      expect(screen.getByText(/アップロード中/)).toBeInTheDocument()
    })
  })

  it('話者数設定が正しく動作する', () => {
    render(<WhisperUploader {...mockProps} />)
    
    // 話者数設定の要素が存在することを確認
    expect(screen.getByText(/話者数設定/)).toBeInTheDocument()
    
    // 自動判定がデフォルトで選択されていることを確認
    const autoDetectRadio = screen.getByLabelText(/自動判定/)
    expect(autoDetectRadio).toBeChecked()
  })

  it('言語設定が正しく動作する', () => {
    render(<WhisperUploader {...mockProps} />)
    
    const languageSelect = screen.getByLabelText(/言語/)
    expect(languageSelect).toBeInTheDocument()
    
    // デフォルトで日本語が選択されていることを確認
    expect(languageSelect).toHaveValue('ja')
    
    // 言語変更時にコールバックが呼ばれることを確認
    fireEvent.change(languageSelect, { target: { value: 'en' } })
    expect(mockProps.onLanguageChange).toHaveBeenCalledWith('en')
  })
})