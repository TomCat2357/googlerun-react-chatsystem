import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChatOperations } from '../useChatOperations'

// Firebase認証のモック
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: { uid: 'test-uid' },
    loading: false
  })
}))

// useTokenのモック
vi.mock('../useToken', () => ({
  useToken: () => 'mock-token'
}))

// Configのモック
vi.mock('../../config', () => ({
  API_BASE_URL: 'http://localhost:3000/api'
}))

// fetch APIのモック
global.fetch = vi.fn()

describe('useChatOperations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = vi.fn()
  })

  it('初期状態が正しく設定される', () => {
    const { result } = renderHook(() => useChatOperations())
    
    expect(result.current.messages).toEqual([])
    expect(result.current.isProcessing).toBe(false)
    expect(result.current.streamingContent).toBe('')
    expect(result.current.error).toBe('')
  })

  it('メッセージ送信が正しく動作する', async () => {
    // 成功レスポンスのモック
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({
              done: false,
              value: new TextEncoder().encode('data: {"content": "こんにちは"}\n\n')
            })
            .mockResolvedValueOnce({
              done: false,
              value: new TextEncoder().encode('data: [DONE]\n\n')
            })
            .mockResolvedValue({ done: true })
        })
      }
    })

    const { result } = renderHook(() => useChatOperations())

    await act(async () => {
      await result.current.sendMessage('こんにちは', [], [], [])
    })

    expect(result.current.messages).toHaveLength(2) // ユーザーメッセージ + アシスタントメッセージ
    expect(result.current.messages[0].content).toBe('こんにちは')
    expect(result.current.messages[0].role).toBe('user')
  })

  it('ストリーミングレスポンスが正しく処理される', async () => {
    const mockReader = {
      read: vi.fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: {"content": "こん"}\n\n')
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: {"content": "にちは"}\n\n')
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: [DONE]\n\n')
        })
        .mockResolvedValue({ done: true })
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader }
    })

    const { result } = renderHook(() => useChatOperations())

    await act(async () => {
      await result.current.sendMessage('テスト', [], [], [])
    })

    // ストリーミングが完了していることを確認
    expect(result.current.isProcessing).toBe(false)
    expect(result.current.streamingContent).toBe('')
  })

  it('エラーハンドリングが正しく動作する', async () => {
    // エラーレスポンスのモック
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve('Internal Server Error')
    })

    const { result } = renderHook(() => useChatOperations())

    await act(async () => {
      await result.current.sendMessage('エラーテスト', [], [], [])
    })

    expect(result.current.error).toContain('API エラー')
    expect(result.current.isProcessing).toBe(false)
  })

  it('メッセージ削除が正しく動作する', () => {
    const { result } = renderHook(() => useChatOperations())

    // 初期メッセージを設定
    act(() => {
      result.current.addMessage({
        id: '1',
        role: 'user',
        content: 'テスト1',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      })
      result.current.addMessage({
        id: '2',
        role: 'assistant',
        content: 'テスト2',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      })
    })

    expect(result.current.messages).toHaveLength(2)

    // メッセージ削除
    act(() => {
      result.current.deleteMessage('1')
    })

    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].id).toBe('2')
  })

  it('メッセージ編集が正しく動作する', () => {
    const { result } = renderHook(() => useChatOperations())

    // 初期メッセージを設定
    act(() => {
      result.current.addMessage({
        id: '1',
        role: 'user',
        content: '元のメッセージ',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      })
    })

    // メッセージ編集
    act(() => {
      result.current.editMessage('1', '編集されたメッセージ')
    })

    expect(result.current.messages[0].content).toBe('編集されたメッセージ')
  })

  it('チャット履歴のクリアが正しく動作する', () => {
    const { result } = renderHook(() => useChatOperations())

    // メッセージを追加
    act(() => {
      result.current.addMessage({
        id: '1',
        role: 'user',
        content: 'テスト',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      })
    })

    expect(result.current.messages).toHaveLength(1)

    // クリア
    act(() => {
      result.current.clearHistory()
    })

    expect(result.current.messages).toHaveLength(0)
  })

  it('処理停止が正しく動作する', () => {
    const { result } = renderHook(() => useChatOperations())

    // 処理中状態にする
    act(() => {
      result.current.setIsProcessing(true)
    })

    expect(result.current.isProcessing).toBe(true)

    // 停止
    act(() => {
      result.current.stopGeneration()
    })

    expect(result.current.isProcessing).toBe(false)
  })

  it('メッセージコピーが正しく動作する', async () => {
    // クリップボードAPIのモック
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined)
      }
    })

    const { result } = renderHook(() => useChatOperations())

    // メッセージを追加
    act(() => {
      result.current.addMessage({
        id: '1',
        role: 'assistant',
        content: 'コピーするメッセージ',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      })
    })

    // コピー実行
    await act(async () => {
      await result.current.copyMessage('1')
    })

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('コピーするメッセージ')
  })

  it('ファイル添付が正しく処理される', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({
              done: false,
              value: new TextEncoder().encode('data: {"content": "画像を確認しました"}\n\n')
            })
            .mockResolvedValueOnce({
              done: false,
              value: new TextEncoder().encode('data: [DONE]\n\n')
            })
            .mockResolvedValue({ done: true })
        })
      }
    })

    const { result } = renderHook(() => useChatOperations())

    const mockImage = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ...'

    await act(async () => {
      await result.current.sendMessage('この画像を見てください', [mockImage], [], [])
    })

    expect(result.current.messages[0].images).toContain(mockImage)
  })

  it('ネットワークエラーが適切に処理される', async () => {
    // ネットワークエラーのモック
    global.fetch = vi.fn().mockRejectedValue(new Error('Network Error'))

    const { result } = renderHook(() => useChatOperations())

    await act(async () => {
      await result.current.sendMessage('テスト', [], [], [])
    })

    expect(result.current.error).toContain('ネットワークエラー')
    expect(result.current.isProcessing).toBe(false)
  })
})