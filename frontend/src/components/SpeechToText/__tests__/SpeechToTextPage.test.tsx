import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SpeechToTextPage from '../SpeechToTextPage'

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
    SPEECH_MAX_SECONDS: 120,
    MAX_AUDIO_FILES: 3,
    MAX_IMAGE_SIZE: 5242880
  }),
  API_BASE_URL: 'http://localhost:3000/api'
}))

// requestIdUtilsのモック
vi.mock('../../../utils/requestIdUtils', () => ({
  generateRequestId: () => 'F123456789ABC'
}))

describe('SpeechToTextPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    
    // 基本的なAPIレスポンスのモック
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        transcript: 'これはテスト音声の文字起こし結果です。',
        confidence: 0.95,
        segments: [
          {
            start: 0.0,
            end: 2.5,
            text: 'これはテスト音声の',
            confidence: 0.98
          },
          {
            start: 2.5,
            end: 5.0,
            text: '文字起こし結果です。',
            confidence: 0.92
          }
        ]
      })
    })
  })

  it('ページが正しくレンダリングされる', () => {
    render(<SpeechToTextPage />)
    
    expect(screen.getByText(/リアルタイム音声文字起こし/)).toBeInTheDocument()
    expect(screen.getByText(/音声録音/)).toBeInTheDocument()
    expect(screen.getByText(/ファイルアップロード/)).toBeInTheDocument()
  })

  it('録音開始ボタンが正しく動作する', async () => {
    // MediaRecorder APIのモック
    const mockMediaRecorder = {
      start: vi.fn(),
      stop: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      state: 'inactive'
    }

    global.MediaRecorder = vi.fn().mockImplementation(() => mockMediaRecorder)
    global.navigator.mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue(new MediaStream())
    } as any

    render(<SpeechToTextPage />)
    
    const recordButton = screen.getByText('録音開始')
    fireEvent.click(recordButton)

    await waitFor(() => {
      expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
        audio: true
      })
    })
  })

  it('音声ファイルアップロードが正しく動作する', async () => {
    render(<SpeechToTextPage />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['mock audio content'], 'test.wav', {
      type: 'audio/wav'
    })
    Object.defineProperty(mockFile, 'size', { value: 1024 * 1024 })

    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    await waitFor(() => {
      expect(screen.getByText('test.wav')).toBeInTheDocument()
    })

    const uploadButton = screen.getByText('文字起こし実行')
    fireEvent.click(uploadButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/speech'),
        expect.objectContaining({
          method: 'POST'
        })
      )
    })
  })

  it('文字起こし結果が正しく表示される', async () => {
    render(<SpeechToTextPage />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['mock audio content'], 'test.wav', {
      type: 'audio/wav'
    })
    Object.defineProperty(mockFile, 'size', { value: 1024 * 1024 })

    fireEvent.change(fileInput, { target: { files: [mockFile] } })
    
    const uploadButton = screen.getByText('文字起こし実行')
    fireEvent.click(uploadButton)

    await waitFor(() => {
      expect(screen.getByText('これはテスト音声の文字起こし結果です。')).toBeInTheDocument()
    })

    // 信頼度が表示されることを確認
    expect(screen.getByText(/信頼度: 95%/)).toBeInTheDocument()
  })

  it('エラーハンドリングが正しく動作する', async () => {
    // エラーレスポンスのモック
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({
        detail: '音声ファイルの処理に失敗しました'
      })
    })

    render(<SpeechToTextPage />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['mock audio content'], 'test.wav', {
      type: 'audio/wav'
    })

    fireEvent.change(fileInput, { target: { files: [mockFile] } })
    
    const uploadButton = screen.getByText('文字起こし実行')
    fireEvent.click(uploadButton)

    await waitFor(() => {
      expect(screen.getByText(/音声ファイルの処理に失敗しました/)).toBeInTheDocument()
    })
  })

  it('ファイルサイズ制限チェックが動作する', async () => {
    render(<SpeechToTextPage />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const largeFile = new File(['large audio content'], 'large.wav', {
      type: 'audio/wav'
    })
    Object.defineProperty(largeFile, 'size', { value: 60 * 1024 * 1024 }) // 60MB

    fireEvent.change(fileInput, { target: { files: [largeFile] } })

    await waitFor(() => {
      expect(screen.getByText(/ファイルサイズが制限を超えています/)).toBeInTheDocument()
    })
  })

  it('対応していないファイル形式でエラーが表示される', async () => {
    render(<SpeechToTextPage />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const invalidFile = new File(['text content'], 'test.txt', {
      type: 'text/plain'
    })

    fireEvent.change(fileInput, { target: { files: [invalidFile] } })

    await waitFor(() => {
      expect(screen.getByText(/対応していないファイル形式です/)).toBeInTheDocument()
    })
  })

  it('音声の長さ制限チェックが動作する', async () => {
    // HTMLAudioElementのモック
    const mockAudio = {
      duration: 180, // 3分（制限の120秒を超過）
      addEventListener: vi.fn((event, callback) => {
        if (event === 'loadedmetadata') {
          setTimeout(callback, 0)
        }
      }),
      removeEventListener: vi.fn(),
      load: vi.fn()
    }

    global.HTMLAudioElement = vi.fn().mockImplementation(() => mockAudio)

    render(<SpeechToTextPage />)
    
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const longAudio = new File(['long audio content'], 'long.wav', {
      type: 'audio/wav'
    })
    Object.defineProperty(longAudio, 'size', { value: 5 * 1024 * 1024 })

    fireEvent.change(fileInput, { target: { files: [longAudio] } })

    await waitFor(() => {
      expect(screen.getByText(/音声の長さが制限を超えています/)).toBeInTheDocument()
    })
  })

  it('結果のエクスポート機能が動作する', async () => {
    render(<SpeechToTextPage />)
    
    // まず文字起こしを実行
    const fileInput = screen.getByLabelText(/音声ファイルを選択/)
    const mockFile = new File(['mock audio content'], 'test.wav', {
      type: 'audio/wav'
    })
    fireEvent.change(fileInput, { target: { files: [mockFile] } })
    
    const uploadButton = screen.getByText('文字起こし実行')
    fireEvent.click(uploadButton)

    await waitFor(() => {
      expect(screen.getByText('これはテスト音声の文字起こし結果です。')).toBeInTheDocument()
    })

    // エクスポートボタンが表示されることを確認
    expect(screen.getByText(/エクスポート/)).toBeInTheDocument()
    
    const exportButton = screen.getByText(/TXTでエクスポート/)
    fireEvent.click(exportButton)

    // ダウンロードが開始されることを確認（実際のファイルダウンロードはモック）
    await waitFor(() => {
      expect(screen.queryByText(/エクスポート中/)).toBeInTheDocument()
    })
  })

  it('リアルタイム音声認識が動作する', async () => {
    // Web Speech APIのモック
    const mockRecognition = {
      start: vi.fn(),
      stop: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      continuous: false,
      interimResults: false,
      lang: 'ja-JP'
    }

    global.webkitSpeechRecognition = vi.fn().mockImplementation(() => mockRecognition)
    global.SpeechRecognition = vi.fn().mockImplementation(() => mockRecognition)

    render(<SpeechToTextPage />)
    
    const realtimeButton = screen.getByText('リアルタイム開始')
    fireEvent.click(realtimeButton)

    expect(mockRecognition.start).toHaveBeenCalled()
    expect(screen.getByText('認識中...')).toBeInTheDocument()
  })

  it('マイクのアクセス許可エラーが適切に処理される', async () => {
    // マイクアクセス拒否をシミュレート
    global.navigator.mediaDevices = {
      getUserMedia: vi.fn().mockRejectedValue(new Error('Permission denied'))
    } as any

    render(<SpeechToTextPage />)
    
    const recordButton = screen.getByText('録音開始')
    fireEvent.click(recordButton)

    await waitFor(() => {
      expect(screen.getByText(/マイクへのアクセスが拒否されました/)).toBeInTheDocument()
    })
  })

  it('言語設定が正しく動作する', () => {
    render(<SpeechToTextPage />)
    
    const languageSelect = screen.getByLabelText(/言語/)
    expect(languageSelect).toBeInTheDocument()
    
    fireEvent.change(languageSelect, { target: { value: 'en-US' } })
    expect(languageSelect).toHaveValue('en-US')
  })

  it('認識精度設定が反映される', () => {
    render(<SpeechToTextPage />)
    
    const accuracySelect = screen.getByLabelText(/認識精度/)
    expect(accuracySelect).toBeInTheDocument()
    
    fireEvent.change(accuracySelect, { target: { value: 'high' } })
    expect(accuracySelect).toHaveValue('high')
  })
})