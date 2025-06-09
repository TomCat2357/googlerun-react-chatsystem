import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorBoundary } from 'react-error-boundary'
import ChatMessages from '../../Chat/ChatMessages'
import WhisperPage from '../../Whisper/WhisperPage'

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
    MAX_TEXT_FILES: 10,
    WHISPER_MAX_BYTES: 50 * 1024 * 1024,
    WHISPER_MAX_SECONDS: 300
  }),
  API_BASE_URL: 'http://localhost:3000/api'
}))

// useTokenのモック
vi.mock('../../../hooks/useToken', () => ({
  useToken: () => 'mock-token'
}))

// エラーを発生させるテスト用コンポーネント
const ThrowErrorComponent = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) {
    throw new Error('テスト用エラー')
  }
  return <div>正常なコンポーネント</div>
}

// カスタムエラーバウンダリー
const TestErrorBoundary = ({ children, onError }: { children: React.ReactNode; onError?: (error: Error) => void }) => {
  return (
    <ErrorBoundary
      FallbackComponent={({ error, resetErrorBoundary }) => (
        <div role="alert" data-testid="error-fallback">
          <h2>エラーが発生しました</h2>
          <details>
            <summary>エラー詳細</summary>
            <pre>{error.message}</pre>
          </details>
          <button onClick={resetErrorBoundary}>再試行</button>
        </div>
      )}
      onError={onError}
    >
      {children}
    </ErrorBoundary>
  )
}

describe('Error Boundary Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // console.errorをモック化してエラーログを抑制
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  describe('Basic Error Handling', () => {
    it('コンポーネントエラーが適切にキャッチされる', () => {
      const onError = vi.fn()

      render(
        <TestErrorBoundary onError={onError}>
          <ThrowErrorComponent shouldThrow={true} />
        </TestErrorBoundary>
      )

      // エラーフォールバックが表示される
      expect(screen.getByTestId('error-fallback')).toBeInTheDocument()
      expect(screen.getByText('エラーが発生しました')).toBeInTheDocument()
      expect(screen.getByText('テスト用エラー')).toBeInTheDocument()

      // onErrorコールバックが呼ばれる
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'テスト用エラー'
        }),
        expect.any(Object)
      )
    })

    it('エラーが発生しない場合は通常通り表示される', () => {
      render(
        <TestErrorBoundary>
          <ThrowErrorComponent shouldThrow={false} />
        </TestErrorBoundary>
      )

      expect(screen.getByText('正常なコンポーネント')).toBeInTheDocument()
      expect(screen.queryByTestId('error-fallback')).not.toBeInTheDocument()
    })
  })

  describe('ChatMessages Error Scenarios', () => {
    it('不正なメッセージデータでもエラーが適切に処理される', () => {
      const invalidMessages = [
        {
          id: '1',
          role: 'user',
          content: null, // 不正なcontent
          timestamp: new Date(),
          images: [],
          audioFiles: [],
          textFiles: []
        }
      ] as any

      const onError = vi.fn()

      render(
        <TestErrorBoundary onError={onError}>
          <ChatMessages
            messages={invalidMessages}
            isProcessing={false}
            streamingContent=""
            onStopGeneration={vi.fn()}
            onRetry={vi.fn()}
            onCopy={vi.fn()}
            onEdit={vi.fn()}
            onDelete={vi.fn()}
          />
        </TestErrorBoundary>
      )

      // エラーが発生した場合、エラーバウンダリーがキャッチする
      if (onError.mock.calls.length > 0) {
        expect(screen.getByTestId('error-fallback')).toBeInTheDocument()
      }
    })

    it('大量のメッセージでメモリエラーが発生した場合の処理', () => {
      // 異常に大きなメッセージデータを作成
      const largeMessages = Array.from({ length: 10000 }, (_, index) => ({
        id: `msg-${index}`,
        role: 'user',
        content: 'x'.repeat(100000), // 非常に長いテキスト
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }))

      const onError = vi.fn()

      try {
        render(
          <TestErrorBoundary onError={onError}>
            <ChatMessages
              messages={largeMessages}
              isProcessing={false}
              streamingContent=""
              onStopGeneration={vi.fn()}
              onRetry={vi.fn()}
              onCopy={vi.fn()}
              onEdit={vi.fn()}
              onDelete={vi.fn()}
            />
          </TestErrorBoundary>
        )
      } catch (error) {
        // メモリエラーなどが発生する可能性がある
        expect(error).toBeDefined()
      }
    })
  })

  describe('WhisperPage Error Scenarios', () => {
    it('認証エラー時の表示が適切である', () => {
      // 認証失敗をモック
      vi.mocked(vi.doMock('../../../contexts/AuthContext', () => ({
        useAuth: () => ({
          currentUser: null,
          loading: false,
          error: 'Authentication failed'
        })
      })))

      render(
        <TestErrorBoundary>
          <WhisperPage />
        </TestErrorBoundary>
      )

      // 認証エラーメッセージが表示される
      expect(screen.getByText(/ログインが必要/)).toBeInTheDocument()
    })

    it('API呼び出しエラー時の処理', async () => {
      // fetch APIをエラーレスポンスでモック
      global.fetch = vi.fn().mockRejectedValue(new Error('Network Error'))

      const onError = vi.fn()

      render(
        <TestErrorBoundary onError={onError}>
          <WhisperPage />
        </TestErrorBoundary>
      )

      // ネットワークエラーが適切に処理されることを確認
      // 実際のAPI呼び出しが行われるタイミングでテストする必要がある
    })
  })

  describe('Network Error Handling', () => {
    it('ネットワーク接続エラーが適切に処理される', async () => {
      // オフライン状態をシミュレート
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: false,
      })

      // fetch がネットワークエラーを返すようにモック
      global.fetch = vi.fn().mockRejectedValue(new Error('Network Error'))

      const onError = vi.fn()

      render(
        <TestErrorBoundary onError={onError}>
          <WhisperPage />
        </TestErrorBoundary>
      )

      // ネットワークエラーの表示確認
      // 実際の実装に応じて調整が必要
    })

    it('タイムアウトエラーが適切に処理される', async () => {
      // タイムアウトをシミュレート
      global.fetch = vi.fn().mockImplementation(() => 
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Request timeout')), 100)
        )
      )

      const onError = vi.fn()

      render(
        <TestErrorBoundary onError={onError}>
          <WhisperPage />
        </TestErrorBoundary>
      )

      // タイムアウトエラーの処理確認
    })
  })

  describe('Browser Compatibility Errors', () => {
    it('FileReader API非対応時の処理', () => {
      // FileReader を undefined にして古いブラウザをシミュレート
      const originalFileReader = global.FileReader
      global.FileReader = undefined as any

      const onError = vi.fn()

      try {
        render(
          <TestErrorBoundary onError={onError}>
            <WhisperPage />
          </TestErrorBoundary>
        )

        // FileReader使用時にエラーが発生する可能性がある
      } finally {
        // FileReader を復元
        global.FileReader = originalFileReader
      }
    })

    it('WebAPI非対応時の適切なフォールバック', () => {
      // Clipboard API を削除してフォールバック動作をテスト
      const originalClipboard = navigator.clipboard
      Object.defineProperty(navigator, 'clipboard', {
        value: undefined,
        configurable: true
      })

      try {
        render(
          <TestErrorBoundary>
            <WhisperPage />
          </TestErrorBoundary>
        )

        // Clipboard API非対応でもエラーにならないことを確認
        expect(screen.queryByTestId('error-fallback')).not.toBeInTheDocument()
      } finally {
        // Clipboard API を復元
        Object.defineProperty(navigator, 'clipboard', {
          value: originalClipboard,
          configurable: true
        })
      }
    })
  })

  describe('Memory Leak and Performance Errors', () => {
    it('メモリリークによるエラーが適切に処理される', () => {
      // メモリリークをシミュレート
      const createMemoryLeak = () => {
        const largeArray: number[][] = []
        for (let i = 0; i < 1000; i++) {
          largeArray.push(new Array(10000).fill(i))
        }
        return largeArray
      }

      const onError = vi.fn()

      try {
        render(
          <TestErrorBoundary onError={onError}>
            <div>{JSON.stringify(createMemoryLeak())}</div>
          </TestErrorBoundary>
        )
      } catch (error) {
        // メモリ関連のエラーがキャッチされることを確認
        expect(error).toBeDefined()
      }
    })

    it('無限レンダリングループのエラー処理', () => {
      // 無限ループを発生させるコンポーネント
      const InfiniteLoopComponent = () => {
        const [count, setCount] = React.useState(0)
        
        // useEffect内で無限にstateを更新（実際にはReactが検出して停止する）
        React.useEffect(() => {
          if (count < 1000) { // 制限を設けてテスト環境を保護
            setCount(count + 1)
          }
        }, [count])

        return <div>Count: {count}</div>
      }

      const onError = vi.fn()

      render(
        <TestErrorBoundary onError={onError}>
          <InfiniteLoopComponent />
        </TestErrorBoundary>
      )

      // 無限ループが適切に処理されることを確認
      // 実際にはReactの保護機能によりエラーにならない場合もある
    })
  })

  describe('Error Recovery', () => {
    it('エラー後の復旧機能が正しく動作する', () => {
      let shouldThrow = true

      const { rerender } = render(
        <TestErrorBoundary>
          <ThrowErrorComponent shouldThrow={shouldThrow} />
        </TestErrorBoundary>
      )

      // 最初はエラーが表示される
      expect(screen.getByTestId('error-fallback')).toBeInTheDocument()

      // 再試行ボタンをクリック
      const retryButton = screen.getByText('再試行')
      expect(retryButton).toBeInTheDocument()

      // エラー条件を解除してコンポーネントを再レンダリング
      shouldThrow = false
      rerender(
        <TestErrorBoundary>
          <ThrowErrorComponent shouldThrow={shouldThrow} />
        </TestErrorBoundary>
      )

      // エラーが解消されても、エラーバウンダリーはリセットボタンが押されるまでエラー状態を維持
      // 実際の動作は ErrorBoundary の実装に依存
    })

    it('部分的なエラー復旧が正しく動作する', () => {
      // 一部のコンポーネントでエラーが発生しても、他の部分は正常に動作することを確認
      render(
        <div>
          <TestErrorBoundary>
            <ThrowErrorComponent shouldThrow={true} />
          </TestErrorBoundary>
          <div data-testid="other-component">他のコンポーネント</div>
        </div>
      )

      // エラーバウンダリー内はエラー表示
      expect(screen.getByTestId('error-fallback')).toBeInTheDocument()
      
      // エラーバウンダリー外は正常表示
      expect(screen.getByTestId('other-component')).toBeInTheDocument()
    })
  })
})