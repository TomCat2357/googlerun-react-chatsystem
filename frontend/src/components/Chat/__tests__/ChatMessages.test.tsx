import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChatMessages from '../ChatMessages'

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
    MAX_IMAGES: 5,
    MAX_AUDIO_FILES: 3,
    MAX_TEXT_FILES: 10
  }),
  API_BASE_URL: 'http://localhost:3000/api'
}))

describe('ChatMessages', () => {
  const mockMessages = [
    {
      id: '1',
      role: 'user',
      content: 'こんにちは',
      timestamp: new Date('2024-01-01T10:00:00Z'),
      images: [],
      audioFiles: [],
      textFiles: []
    },
    {
      id: '2',
      role: 'assistant',
      content: 'こんにちは！何かお手伝いできることはありますか？',
      timestamp: new Date('2024-01-01T10:00:30Z'),
      images: [],
      audioFiles: [],
      textFiles: []
    },
    {
      id: '3',
      role: 'user',
      content: '画像を解析してください',
      timestamp: new Date('2024-01-01T10:01:00Z'),
      images: ['data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ...'],
      audioFiles: [],
      textFiles: []
    }
  ]

  const mockProps = {
    messages: mockMessages,
    isProcessing: false,
    streamingContent: '',
    onStopGeneration: vi.fn(),
    onRetry: vi.fn(),
    onCopy: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn()
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('メッセージ一覧が正しく表示される', () => {
    render(<ChatMessages {...mockProps} />)
    
    expect(screen.getByText('こんにちは')).toBeInTheDocument()
    expect(screen.getByText('こんにちは！何かお手伝いできることはありますか？')).toBeInTheDocument()
    expect(screen.getByText('画像を解析してください')).toBeInTheDocument()
  })

  it('ユーザーメッセージとアシスタントメッセージが区別される', () => {
    render(<ChatMessages {...mockProps} />)
    
    // ユーザーメッセージのアイコンまたはスタイルを確認
    const userMessages = screen.getAllByText('👤')
    expect(userMessages).toHaveLength(2) // ユーザーメッセージが2つ
    
    const assistantMessages = screen.getAllByText('🤖')
    expect(assistantMessages).toHaveLength(1) // アシスタントメッセージが1つ
  })

  it('画像添付メッセージが正しく表示される', () => {
    render(<ChatMessages {...mockProps} />)
    
    // 画像が添付されたメッセージに画像プレビューが表示される
    const images = screen.getAllByRole('img')
    expect(images).toHaveLength(1)
  })

  it('タイムスタンプが正しく表示される', () => {
    render(<ChatMessages {...mockProps} />)
    
    // タイムスタンプの表示を確認（例：10:00の形式）
    expect(screen.getByText('10:00')).toBeInTheDocument()
    expect(screen.getByText('10:00')).toBeInTheDocument() // アシスタントメッセージ
    expect(screen.getByText('10:01')).toBeInTheDocument()
  })

  it('処理中の表示が正しく動作する', () => {
    const processingProps = {
      ...mockProps,
      isProcessing: true,
      streamingContent: '回答を考えています...'
    }
    
    render(<ChatMessages {...processingProps} />)
    
    expect(screen.getByText('回答を考えています...')).toBeInTheDocument()
  })

  it('ストリーミング中のコンテンツが表示される', () => {
    const streamingProps = {
      ...mockProps,
      isProcessing: true,
      streamingContent: 'これは部分的な回答です'
    }
    
    render(<ChatMessages {...streamingProps} />)
    
    expect(screen.getByText('これは部分的な回答です')).toBeInTheDocument()
  })

  it('停止ボタンが処理中に表示される', () => {
    const processingProps = {
      ...mockProps,
      isProcessing: true
    }
    
    render(<ChatMessages {...processingProps} />)
    
    const stopButton = screen.getByText('停止')
    expect(stopButton).toBeInTheDocument()
    
    fireEvent.click(stopButton)
    expect(mockProps.onStopGeneration).toHaveBeenCalled()
  })

  it('コピーボタンが正しく動作する', () => {
    // クリップボードAPIのモック
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined)
      }
    })
    
    render(<ChatMessages {...mockProps} />)
    
    // メッセージにホバーしてコピーボタンを表示
    const messageElement = screen.getByText('こんにちは！何かお手伝いできることはありますか？')
    fireEvent.mouseEnter(messageElement)
    
    const copyButton = screen.getByTitle('コピー')
    fireEvent.click(copyButton)
    
    expect(mockProps.onCopy).toHaveBeenCalledWith('2')
  })

  it('再試行ボタンが正しく動作する', () => {
    render(<ChatMessages {...mockProps} />)
    
    // ユーザーメッセージにホバーして再試行ボタンを表示
    const userMessage = screen.getByText('こんにちは')
    fireEvent.mouseEnter(userMessage)
    
    const retryButton = screen.getByTitle('再試行')
    fireEvent.click(retryButton)
    
    expect(mockProps.onRetry).toHaveBeenCalledWith('1')
  })

  it('編集ボタンが正しく動作する', () => {
    render(<ChatMessages {...mockProps} />)
    
    // ユーザーメッセージにホバーして編集ボタンを表示
    const userMessage = screen.getByText('こんにちは')
    fireEvent.mouseEnter(userMessage)
    
    const editButton = screen.getByTitle('編集')
    fireEvent.click(editButton)
    
    expect(mockProps.onEdit).toHaveBeenCalledWith('1')
  })

  it('削除ボタンが正しく動作する', () => {
    render(<ChatMessages {...mockProps} />)
    
    // メッセージにホバーして削除ボタンを表示
    const messageElement = screen.getByText('こんにちは')
    fireEvent.mouseEnter(messageElement)
    
    const deleteButton = screen.getByTitle('削除')
    fireEvent.click(deleteButton)
    
    expect(mockProps.onDelete).toHaveBeenCalledWith('1')
  })

  it('メッセージが空の場合に適切な表示がされる', () => {
    const emptyProps = { ...mockProps, messages: [] }
    render(<ChatMessages {...emptyProps} />)
    
    expect(screen.getByText(/メッセージはありません/)).toBeInTheDocument()
  })

  it('長いメッセージが適切に表示される', () => {
    const longMessage = 'あ'.repeat(1000)
    const longMessageProps = {
      ...mockProps,
      messages: [{
        id: '1',
        role: 'assistant',
        content: longMessage,
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }]
    }
    
    render(<ChatMessages {...longMessageProps} />)
    
    expect(screen.getByText(longMessage)).toBeInTheDocument()
  })

  it('マークダウン形式のメッセージが正しく表示される', () => {
    const markdownMessage = '# タイトル\n\n**太字**のテキストです。\n\n- リスト項目1\n- リスト項目2'
    const markdownProps = {
      ...mockProps,
      messages: [{
        id: '1',
        role: 'assistant',
        content: markdownMessage,
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }]
    }
    
    render(<ChatMessages {...markdownProps} />)
    
    // マークダウンが適切にレンダリングされることを確認
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    expect(screen.getByText('太字')).toBeInTheDocument()
  })
})