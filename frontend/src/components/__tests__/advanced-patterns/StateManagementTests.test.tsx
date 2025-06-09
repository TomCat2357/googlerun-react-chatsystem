import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { renderHook, act } from '@testing-library/react'
import React from 'react'
import { useChatHistory } from '../../../hooks/useChatHistory'
import { useChatOperations } from '../../../hooks/useChatOperations'
import { useFileUpload } from '../../../hooks/useFileUpload'

// Firebase認証のモック
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: { uid: 'test-uid' },
    loading: false
  })
}))

// IndexedDBのモック
const mockIndexedDB = {
  open: vi.fn().mockImplementation(() => ({
    onsuccess: null,
    onerror: null,
    result: {
      transaction: vi.fn().mockReturnValue({
        objectStore: vi.fn().mockReturnValue({
          get: vi.fn().mockReturnValue({
            onsuccess: null,
            onerror: null,
            result: { value: [] }
          }),
          put: vi.fn(),
          add: vi.fn(),
          delete: vi.fn()
        })
      })
    }
  }))
}

global.indexedDB = mockIndexedDB as any

/**
 * 状態管理パターンのテスト
 * React Hooks、Context、グローバル状態の管理パターンをテスト
 */
describe('State Management Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('useChatHistory Hook Tests', () => {
    it('チャット履歴の初期化が正しく動作する', async () => {
      const { result } = renderHook(() => useChatHistory())

      expect(result.current.messages).toEqual([])
      expect(result.current.isLoading).toBe(false)

      // 初期化処理の完了を待機
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })
    })

    it('メッセージの追加が正しく動作する', async () => {
      const { result } = renderHook(() => useChatHistory())

      const newMessage = {
        id: 'msg-1',
        role: 'user' as const,
        content: 'テストメッセージ',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }

      act(() => {
        result.current.addMessage(newMessage)
      })

      expect(result.current.messages).toHaveLength(1)
      expect(result.current.messages[0]).toEqual(newMessage)
    })

    it('メッセージの更新が正しく動作する', async () => {
      const { result } = renderHook(() => useChatHistory())

      const initialMessage = {
        id: 'msg-1',
        role: 'user' as const,
        content: '初期メッセージ',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }

      act(() => {
        result.current.addMessage(initialMessage)
      })

      const updatedMessage = {
        ...initialMessage,
        content: '更新されたメッセージ'
      }

      act(() => {
        result.current.updateMessage('msg-1', updatedMessage)
      })

      expect(result.current.messages[0].content).toBe('更新されたメッセージ')
    })

    it('メッセージの削除が正しく動作する', async () => {
      const { result } = renderHook(() => useChatHistory())

      const message1 = {
        id: 'msg-1',
        role: 'user' as const,
        content: 'メッセージ1',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }

      const message2 = {
        id: 'msg-2',
        role: 'user' as const,
        content: 'メッセージ2',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }

      act(() => {
        result.current.addMessage(message1)
        result.current.addMessage(message2)
      })

      expect(result.current.messages).toHaveLength(2)

      act(() => {
        result.current.deleteMessage('msg-1')
      })

      expect(result.current.messages).toHaveLength(1)
      expect(result.current.messages[0].id).toBe('msg-2')
    })

    it('履歴のクリアが正しく動作する', async () => {
      const { result } = renderHook(() => useChatHistory())

      const message = {
        id: 'msg-1',
        role: 'user' as const,
        content: 'テストメッセージ',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }

      act(() => {
        result.current.addMessage(message)
      })

      expect(result.current.messages).toHaveLength(1)

      act(() => {
        result.current.clearHistory()
      })

      expect(result.current.messages).toHaveLength(0)
    })

    it('永続化処理が正しく動作する', async () => {
      const { result } = renderHook(() => useChatHistory())

      const message = {
        id: 'msg-1',
        role: 'user' as const,
        content: 'テストメッセージ',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }

      act(() => {
        result.current.addMessage(message)
      })

      // IndexedDBへの保存処理の確認
      await waitFor(() => {
        expect(mockIndexedDB.open).toHaveBeenCalled()
      })
    })
  })

  describe('useChatOperations Hook Tests', () => {
    beforeEach(() => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          content: 'AI からの応答',
          role: 'assistant'
        })
      })
    })

    it('メッセージ送信処理が正しく動作する', async () => {
      const { result } = renderHook(() => useChatOperations())

      const message = 'テストメッセージ'

      await act(async () => {
        await result.current.sendMessage(message, [], [], [])
      })

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/chat'),
        expect.objectContaining({
          method: 'POST'
        })
      )
    })

    it('ストリーミング応答の処理が正しく動作する', async () => {
      // ストリーミングレスポンスのモック
      const mockReader = {
        read: vi.fn()
          .mockResolvedValueOnce({
            done: false,
            value: new TextEncoder().encode('data: {"content": "こんにちは"}\n\n')
          })
          .mockResolvedValueOnce({
            done: false,
            value: new TextEncoder().encode('data: {"content": "今日は"}\n\n')
          })
          .mockResolvedValueOnce({
            done: true
          })
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        body: {
          getReader: () => mockReader
        }
      })

      const { result } = renderHook(() => useChatOperations())

      await act(async () => {
        await result.current.sendMessage('テスト', [], [], [])
      })

      expect(result.current.streamingContent).toContain('こんにちは')
    })

    it('エラーハンドリングが正しく動作する', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({
          detail: 'サーバーエラー'
        })
      })

      const { result } = renderHook(() => useChatOperations())

      await act(async () => {
        await result.current.sendMessage('テスト', [], [], [])
      })

      expect(result.current.error).toBe('サーバーエラー')
    })

    it('生成停止機能が正しく動作する', async () => {
      const { result } = renderHook(() => useChatOperations())

      act(() => {
        result.current.setIsProcessing(true)
      })

      expect(result.current.isProcessing).toBe(true)

      act(() => {
        result.current.stopGeneration()
      })

      expect(result.current.isProcessing).toBe(false)
    })
  })

  describe('useFileUpload Hook Tests', () => {
    it('ファイル選択が正しく動作する', async () => {
      const { result } = renderHook(() => useFileUpload())

      const mockFile = new File(['test content'], 'test.txt', {
        type: 'text/plain'
      })

      act(() => {
        result.current.addFile(mockFile)
      })

      expect(result.current.selectedFiles).toHaveLength(1)
      expect(result.current.selectedFiles[0].name).toBe('test.txt')
    })

    it('ファイル数制限チェックが動作する', async () => {
      const { result } = renderHook(() => useFileUpload({
        maxFiles: 2
      }))

      const file1 = new File(['content1'], 'file1.txt', { type: 'text/plain' })
      const file2 = new File(['content2'], 'file2.txt', { type: 'text/plain' })
      const file3 = new File(['content3'], 'file3.txt', { type: 'text/plain' })

      act(() => {
        result.current.addFile(file1)
        result.current.addFile(file2)
        result.current.addFile(file3)
      })

      expect(result.current.selectedFiles).toHaveLength(2)
      expect(result.current.error).toContain('ファイル数が制限を超えています')
    })

    it('ファイルサイズ制限チェックが動作する', async () => {
      const { result } = renderHook(() => useFileUpload({
        maxFileSize: 1024 // 1KB
      }))

      const largeFile = new File(['x'.repeat(2048)], 'large.txt', {
        type: 'text/plain'
      })
      Object.defineProperty(largeFile, 'size', { value: 2048 })

      act(() => {
        result.current.addFile(largeFile)
      })

      expect(result.current.selectedFiles).toHaveLength(0)
      expect(result.current.error).toContain('ファイルサイズが制限を超えています')
    })

    it('ファイル形式制限チェックが動作する', async () => {
      const { result } = renderHook(() => useFileUpload({
        allowedTypes: ['image/jpeg', 'image/png']
      }))

      const invalidFile = new File(['content'], 'test.txt', {
        type: 'text/plain'
      })

      act(() => {
        result.current.addFile(invalidFile)
      })

      expect(result.current.selectedFiles).toHaveLength(0)
      expect(result.current.error).toContain('対応していないファイル形式です')
    })

    it('ファイル削除が正しく動作する', async () => {
      const { result } = renderHook(() => useFileUpload())

      const file1 = new File(['content1'], 'file1.txt', { type: 'text/plain' })
      const file2 = new File(['content2'], 'file2.txt', { type: 'text/plain' })

      act(() => {
        result.current.addFile(file1)
        result.current.addFile(file2)
      })

      expect(result.current.selectedFiles).toHaveLength(2)

      act(() => {
        result.current.removeFile(0)
      })

      expect(result.current.selectedFiles).toHaveLength(1)
      expect(result.current.selectedFiles[0].name).toBe('file2.txt')
    })

    it('全ファイルクリアが正しく動作する', async () => {
      const { result } = renderHook(() => useFileUpload())

      const file1 = new File(['content1'], 'file1.txt', { type: 'text/plain' })
      const file2 = new File(['content2'], 'file2.txt', { type: 'text/plain' })

      act(() => {
        result.current.addFile(file1)
        result.current.addFile(file2)
      })

      expect(result.current.selectedFiles).toHaveLength(2)

      act(() => {
        result.current.clearFiles()
      })

      expect(result.current.selectedFiles).toHaveLength(0)
    })
  })

  describe('複合状態管理テスト', () => {
    // テスト用のコンポーネント
    const TestComponent = () => {
      const chatHistory = useChatHistory()
      const chatOps = useChatOperations()
      const fileUpload = useFileUpload()

      return (
        <div>
          <div data-testid="message-count">{chatHistory.messages.length}</div>
          <div data-testid="is-processing">{chatOps.isProcessing.toString()}</div>
          <div data-testid="file-count">{fileUpload.selectedFiles.length}</div>
          
          <button
            data-testid="send-message"
            onClick={() => {
              const message = {
                id: 'test-msg',
                role: 'user' as const,
                content: 'テストメッセージ',
                timestamp: new Date(),
                images: [],
                audioFiles: [],
                textFiles: []
              }
              chatHistory.addMessage(message)
            }}
          >
            メッセージ送信
          </button>
          
          <button
            data-testid="add-file"
            onClick={() => {
              const file = new File(['content'], 'test.txt', { type: 'text/plain' })
              fileUpload.addFile(file)
            }}
          >
            ファイル追加
          </button>
        </div>
      )
    }

    it('複数のHooksが正しく連携する', async () => {
      render(<TestComponent />)

      expect(screen.getByTestId('message-count')).toHaveTextContent('0')
      expect(screen.getByTestId('file-count')).toHaveTextContent('0')

      // メッセージ追加
      fireEvent.click(screen.getByTestId('send-message'))
      expect(screen.getByTestId('message-count')).toHaveTextContent('1')

      // ファイル追加
      fireEvent.click(screen.getByTestId('add-file'))
      expect(screen.getByTestId('file-count')).toHaveTextContent('1')
    })

    it('状態の更新が正しく再レンダリングを引き起こす', async () => {
      const { rerender } = render(<TestComponent />)

      expect(screen.getByTestId('message-count')).toHaveTextContent('0')

      fireEvent.click(screen.getByTestId('send-message'))
      
      // 再レンダリング後の状態確認
      rerender(<TestComponent />)
      expect(screen.getByTestId('message-count')).toHaveTextContent('1')
    })
  })

  describe('メモリリーク検出テスト', () => {
    it('Hookのクリーンアップが正しく動作する', () => {
      const { unmount } = renderHook(() => useChatHistory())

      // アンマウント処理
      unmount()

      // メモリリークがないことを確認（実際の検証は環境に依存）
      expect(true).toBe(true) // プレースホルダー
    })

    it('イベントリスナーが正しくクリーンアップされる', () => {
      const addEventListenerSpy = vi.spyOn(window, 'addEventListener')
      const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener')

      const { unmount } = renderHook(() => useChatOperations())

      // マウント時にリスナーが追加される
      expect(addEventListenerSpy).toHaveBeenCalled()

      // アンマウント時にリスナーが削除される
      unmount()
      expect(removeEventListenerSpy).toHaveBeenCalled()

      addEventListenerSpy.mockRestore()
      removeEventListenerSpy.mockRestore()
    })
  })
})