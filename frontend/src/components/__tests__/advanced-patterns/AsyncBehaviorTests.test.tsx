import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { act } from '@testing-library/react'

// Firebase認証のモック
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: { uid: 'test-uid' },
    loading: false
  })
}))

/**
 * 非同期動作パターンのテスト
 * Promise、async/await、タイマー、ストリーミングなどの非同期処理パターンをテスト
 */
describe('Async Behavior Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  describe('Promise-based API Tests', () => {
    it('複数の並列API呼び出しが正しく処理される', async () => {
      const mockApi1 = vi.fn().mockResolvedValue({ data: 'api1-result' })
      const mockApi2 = vi.fn().mockResolvedValue({ data: 'api2-result' })
      const mockApi3 = vi.fn().mockResolvedValue({ data: 'api3-result' })

      // 並列実行のテスト
      const results = await Promise.all([
        mockApi1(),
        mockApi2(),
        mockApi3()
      ])

      expect(results).toHaveLength(3)
      expect(results[0].data).toBe('api1-result')
      expect(results[1].data).toBe('api2-result')
      expect(results[2].data).toBe('api3-result')

      expect(mockApi1).toHaveBeenCalledTimes(1)
      expect(mockApi2).toHaveBeenCalledTimes(1)
      expect(mockApi3).toHaveBeenCalledTimes(1)
    })

    it('API呼び出しの順次実行が正しく動作する', async () => {
      const mockApi1 = vi.fn().mockResolvedValue({ data: 'step1' })
      const mockApi2 = vi.fn().mockResolvedValue({ data: 'step2' })
      const mockApi3 = vi.fn().mockResolvedValue({ data: 'step3' })

      // 順次実行のテスト
      const result1 = await mockApi1()
      const result2 = await mockApi2(result1.data)
      const result3 = await mockApi3(result2.data)

      expect(result3.data).toBe('step3')
      
      // 呼び出し順序の確認
      expect(mockApi1).toHaveBeenCalledBefore(mockApi2 as any)
      expect(mockApi2).toHaveBeenCalledBefore(mockApi3 as any)
    })

    it('API呼び出しのレース条件が適切に処理される', async () => {
      let resolveApi1: (value: any) => void
      let resolveApi2: (value: any) => void

      const api1Promise = new Promise(resolve => {
        resolveApi1 = resolve
      })
      const api2Promise = new Promise(resolve => {
        resolveApi2 = resolve
      })

      const mockApi1 = vi.fn().mockReturnValue(api1Promise)
      const mockApi2 = vi.fn().mockReturnValue(api2Promise)

      const racePromise = Promise.race([mockApi1(), mockApi2()])

      // API2を先に解決
      resolveApi2!({ winner: 'api2' })
      
      const result = await racePromise
      expect(result.winner).toBe('api2')

      // API1を後で解決
      resolveApi1!({ winner: 'api1' })
    })

    it('失敗したAPI呼び出しのリトライ機能が動作する', async () => {
      let callCount = 0
      const mockApi = vi.fn().mockImplementation(() => {
        callCount++
        if (callCount < 3) {
          return Promise.reject(new Error(`失敗 ${callCount}`))
        }
        return Promise.resolve({ data: '成功' })
      })

      const retryApi = async (maxRetries: number = 3) => {
        for (let i = 0; i < maxRetries; i++) {
          try {
            return await mockApi()
          } catch (error) {
            if (i === maxRetries - 1) {
              throw error
            }
            await new Promise(resolve => setTimeout(resolve, 100))
          }
        }
      }

      const result = await retryApi()
      expect(result.data).toBe('成功')
      expect(mockApi).toHaveBeenCalledTimes(3)
    })
  })

  describe('Streaming Data Tests', () => {
    it('ストリーミングデータの受信が正しく処理される', async () => {
      const chunks = ['chunk1', 'chunk2', 'chunk3']
      let chunkIndex = 0

      const mockReader = {
        read: vi.fn().mockImplementation(() => {
          if (chunkIndex < chunks.length) {
            const chunk = chunks[chunkIndex++]
            return Promise.resolve({
              done: false,
              value: new TextEncoder().encode(chunk)
            })
          } else {
            return Promise.resolve({ done: true })
          }
        })
      }

      const mockResponse = {
        ok: true,
        body: {
          getReader: () => mockReader
        }
      }

      global.fetch = vi.fn().mockResolvedValue(mockResponse)

      const StreamingComponent = () => {
        const [content, setContent] = React.useState('')
        const [isStreaming, setIsStreaming] = React.useState(false)

        const startStream = async () => {
          setIsStreaming(true)
          const response = await fetch('/api/stream')
          const reader = response.body!.getReader()

          let fullContent = ''
          while (true) {
            const { done, value } = await reader.read()
            if (done) break

            const chunk = new TextDecoder().decode(value)
            fullContent += chunk
            setContent(fullContent)
          }
          setIsStreaming(false)
        }

        return (
          <div>
            <button onClick={startStream}>開始</button>
            <div data-testid="content">{content}</div>
            <div data-testid="streaming">{isStreaming.toString()}</div>
          </div>
        )
      }

      render(<StreamingComponent />)

      const button = screen.getByText('開始')
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('content')).toHaveTextContent('chunk1chunk2chunk3')
      })

      expect(screen.getByTestId('streaming')).toHaveTextContent('false')
    })

    it('ストリーミングの中断処理が正しく動作する', async () => {
      const abortController = new AbortController()
      
      const mockReader = {
        read: vi.fn()
          .mockResolvedValueOnce({
            done: false,
            value: new TextEncoder().encode('chunk1')
          })
          .mockRejectedValue(new DOMException('The operation was aborted.', 'AbortError'))
      }

      const mockResponse = {
        ok: true,
        body: {
          getReader: () => mockReader
        }
      }

      global.fetch = vi.fn().mockResolvedValue(mockResponse)

      const StreamingComponent = () => {
        const [content, setContent] = React.useState('')
        const [abortController, setAbortController] = React.useState<AbortController | null>(null)

        const startStream = async () => {
          const controller = new AbortController()
          setAbortController(controller)

          try {
            const response = await fetch('/api/stream', {
              signal: controller.signal
            })
            const reader = response.body!.getReader()

            while (true) {
              const { done, value } = await reader.read()
              if (done) break

              const chunk = new TextDecoder().decode(value)
              setContent(prev => prev + chunk)
            }
          } catch (error) {
            if (error instanceof DOMException && error.name === 'AbortError') {
              setContent(prev => prev + '[中断]')
            }
          }
        }

        const stopStream = () => {
          if (abortController) {
            abortController.abort()
          }
        }

        return (
          <div>
            <button onClick={startStream}>開始</button>
            <button onClick={stopStream}>停止</button>
            <div data-testid="content">{content}</div>
          </div>
        )
      }

      render(<StreamingComponent />)

      const startButton = screen.getByText('開始')
      const stopButton = screen.getByText('停止')

      fireEvent.click(startButton)

      // 少し待ってから停止
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 10))
      })

      fireEvent.click(stopButton)

      await waitFor(() => {
        expect(screen.getByTestId('content')).toHaveTextContent('chunk1[中断]')
      })
    })
  })

  describe('Timer-based Operations Tests', () => {
    it('setTimeoutを使った遅延処理が正しく動作する', async () => {
      const DelayedComponent = () => {
        const [message, setMessage] = React.useState('初期メッセージ')

        const startDelay = () => {
          setTimeout(() => {
            setMessage('遅延後のメッセージ')
          }, 1000)
        }

        return (
          <div>
            <button onClick={startDelay}>遅延開始</button>
            <div data-testid="message">{message}</div>
          </div>
        )
      }

      render(<DelayedComponent />)

      const button = screen.getByText('遅延開始')
      fireEvent.click(button)

      expect(screen.getByTestId('message')).toHaveTextContent('初期メッセージ')

      // 時間を進める
      act(() => {
        vi.advanceTimersByTime(1000)
      })

      expect(screen.getByTestId('message')).toHaveTextContent('遅延後のメッセージ')
    })

    it('setIntervalを使った定期処理が正しく動作する', async () => {
      const IntervalComponent = () => {
        const [count, setCount] = React.useState(0)
        const [intervalId, setIntervalId] = React.useState<NodeJS.Timeout | null>(null)

        const startInterval = () => {
          const id = setInterval(() => {
            setCount(prev => prev + 1)
          }, 500)
          setIntervalId(id)
        }

        const stopInterval = () => {
          if (intervalId) {
            clearInterval(intervalId)
            setIntervalId(null)
          }
        }

        return (
          <div>
            <button onClick={startInterval}>開始</button>
            <button onClick={stopInterval}>停止</button>
            <div data-testid="count">{count}</div>
          </div>
        )
      }

      render(<IntervalComponent />)

      const startButton = screen.getByText('開始')
      fireEvent.click(startButton)

      expect(screen.getByTestId('count')).toHaveTextContent('0')

      // 500ms進める
      act(() => {
        vi.advanceTimersByTime(500)
      })
      expect(screen.getByTestId('count')).toHaveTextContent('1')

      // さらに500ms進める
      act(() => {
        vi.advanceTimersByTime(500)
      })
      expect(screen.getByTestId('count')).toHaveTextContent('2')

      // 停止
      const stopButton = screen.getByText('停止')
      fireEvent.click(stopButton)

      // さらに時間を進めても増加しない
      act(() => {
        vi.advanceTimersByTime(1000)
      })
      expect(screen.getByTestId('count')).toHaveTextContent('2')
    })

    it('デバウンス処理が正しく動作する', async () => {
      const DebounceComponent = () => {
        const [value, setValue] = React.useState('')
        const [debouncedValue, setDebouncedValue] = React.useState('')

        React.useEffect(() => {
          const timer = setTimeout(() => {
            setDebouncedValue(value)
          }, 300)

          return () => clearTimeout(timer)
        }, [value])

        return (
          <div>
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              data-testid="input"
            />
            <div data-testid="debounced">{debouncedValue}</div>
          </div>
        )
      }

      render(<DebounceComponent />)

      const input = screen.getByTestId('input')

      // 高速で入力
      fireEvent.change(input, { target: { value: 'a' } })
      fireEvent.change(input, { target: { value: 'ab' } })
      fireEvent.change(input, { target: { value: 'abc' } })

      // まだデバウンスされていない
      expect(screen.getByTestId('debounced')).toHaveTextContent('')

      // 300ms進める
      act(() => {
        vi.advanceTimersByTime(300)
      })

      // デバウンス処理が実行される
      expect(screen.getByTestId('debounced')).toHaveTextContent('abc')
    })

    it('スロットル処理が正しく動作する', async () => {
      const ThrottleComponent = () => {
        const [count, setCount] = React.useState(0)
        const [throttledCount, setThrottledCount] = React.useState(0)
        const lastUpdateRef = React.useRef(0)

        const handleClick = () => {
          setCount(prev => prev + 1)

          const now = Date.now()
          if (now - lastUpdateRef.current >= 200) {
            setThrottledCount(prev => prev + 1)
            lastUpdateRef.current = now
          }
        }

        return (
          <div>
            <button onClick={handleClick}>クリック</button>
            <div data-testid="count">{count}</div>
            <div data-testid="throttled">{throttledCount}</div>
          </div>
        )
      }

      render(<ThrottleComponent />)

      const button = screen.getByText('クリック')

      // 高速でクリック
      fireEvent.click(button)
      fireEvent.click(button)
      fireEvent.click(button)

      expect(screen.getByTestId('count')).toHaveTextContent('3')
      expect(screen.getByTestId('throttled')).toHaveTextContent('1')

      // 時間を進める
      act(() => {
        vi.advanceTimersByTime(200)
      })

      // 再度クリック
      fireEvent.click(button)

      expect(screen.getByTestId('count')).toHaveTextContent('4')
      expect(screen.getByTestId('throttled')).toHaveTextContent('2')
    })
  })

  describe('Error Handling in Async Operations', () => {
    it('非同期エラーが適切にキャッチされる', async () => {
      const AsyncErrorComponent = () => {
        const [error, setError] = React.useState<string | null>(null)
        const [loading, setLoading] = React.useState(false)

        const fetchData = async () => {
          setLoading(true)
          setError(null)

          try {
            const response = await fetch('/api/data')
            if (!response.ok) {
              throw new Error('API エラー')
            }
            const data = await response.json()
          } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error')
          } finally {
            setLoading(false)
          }
        }

        return (
          <div>
            <button onClick={fetchData}>データ取得</button>
            {loading && <div data-testid="loading">読み込み中</div>}
            {error && <div data-testid="error">{error}</div>}
          </div>
        )
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500
      })

      render(<AsyncErrorComponent />)

      const button = screen.getByText('データ取得')
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('API エラー')
      })

      expect(screen.queryByTestId('loading')).not.toBeInTheDocument()
    })

    it('タイムアウトエラーが正しく処理される', async () => {
      const TimeoutComponent = () => {
        const [status, setStatus] = React.useState('未開始')

        const fetchWithTimeout = async () => {
          setStatus('実行中')

          const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => reject(new Error('タイムアウト')), 1000)
          })

          const fetchPromise = new Promise(resolve => {
            setTimeout(() => resolve({ data: '成功' }), 2000)
          })

          try {
            await Promise.race([fetchPromise, timeoutPromise])
            setStatus('成功')
          } catch (error) {
            setStatus(error instanceof Error ? error.message : 'エラー')
          }
        }

        return (
          <div>
            <button onClick={fetchWithTimeout}>開始</button>
            <div data-testid="status">{status}</div>
          </div>
        )
      }

      render(<TimeoutComponent />)

      const button = screen.getByText('開始')
      fireEvent.click(button)

      expect(screen.getByTestId('status')).toHaveTextContent('実行中')

      // 1秒進める（タイムアウト発生）
      await act(async () => {
        vi.advanceTimersByTime(1000)
      })

      await waitFor(() => {
        expect(screen.getByTestId('status')).toHaveTextContent('タイムアウト')
      })
    })
  })

  describe('Concurrent Operations Tests', () => {
    it('複数の非同期操作が競合しても適切に処理される', async () => {
      const ConcurrentComponent = () => {
        const [results, setResults] = React.useState<string[]>([])

        const startConcurrentOperations = async () => {
          const operations = [
            fetch('/api/data1').then(() => 'result1'),
            fetch('/api/data2').then(() => 'result2'),
            fetch('/api/data3').then(() => 'result3')
          ]

          try {
            const allResults = await Promise.allSettled(operations)
            const successResults = allResults
              .filter(result => result.status === 'fulfilled')
              .map(result => (result as PromiseFulfilledResult<string>).value)
            
            setResults(successResults)
          } catch (error) {
            console.error('エラー:', error)
          }
        }

        return (
          <div>
            <button onClick={startConcurrentOperations}>開始</button>
            <div data-testid="results">{results.join(', ')}</div>
          </div>
        )
      }

      global.fetch = vi.fn()
        .mockResolvedValueOnce({ ok: true })
        .mockResolvedValueOnce({ ok: true })
        .mockRejectedValueOnce(new Error('Failed'))

      render(<ConcurrentComponent />)

      const button = screen.getByText('開始')
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('results')).toHaveTextContent('result1, result2')
      })
    })
  })
})