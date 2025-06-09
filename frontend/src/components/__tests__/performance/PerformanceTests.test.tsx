import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { performance } from 'perf_hooks'
import ChatMessages from '../../Chat/ChatMessages'
import WhisperJobList from '../../Whisper/WhisperJobList'

// Firebase認証のモック
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: { uid: 'test-uid' },
    loading: false
  })
}))

describe('Performance Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('ChatMessages Performance', () => {
    it('大量メッセージ（1000件）のレンダリングが3秒以内に完了する', async () => {
      // 1000件のテストメッセージを生成
      const generateLargeMessageSet = (count: number) => {
        return Array.from({ length: count }, (_, index) => ({
          id: `msg-${index}`,
          role: index % 2 === 0 ? 'user' : 'assistant',
          content: `これはテストメッセージ ${index + 1} です。パフォーマンステスト用の長いメッセージ内容を含んでいます。`,
          timestamp: new Date(Date.now() - (count - index) * 1000),
          images: [],
          audioFiles: [],
          textFiles: []
        }))
      }

      const largeMessageSet = generateLargeMessageSet(1000)
      const mockProps = {
        messages: largeMessageSet,
        isProcessing: false,
        streamingContent: '',
        onStopGeneration: vi.fn(),
        onRetry: vi.fn(),
        onCopy: vi.fn(),
        onEdit: vi.fn(),
        onDelete: vi.fn()
      }

      const startTime = performance.now()
      
      render(<ChatMessages {...mockProps} />)
      
      // 最初と最後のメッセージが表示されることを確認
      await waitFor(() => {
        expect(screen.getByText('これはテストメッセージ 1 です')).toBeInTheDocument()
      }, { timeout: 5000 })

      const endTime = performance.now()
      const renderTime = endTime - startTime

      expect(renderTime).toBeLessThan(3000) // 3秒以内
      console.log(`大量メッセージレンダリング時間: ${renderTime.toFixed(2)}ms`)
    })

    it('メッセージ追加時のレンダリング時間が100ms以内である', async () => {
      const initialMessages = Array.from({ length: 100 }, (_, index) => ({
        id: `msg-${index}`,
        role: 'user',
        content: `メッセージ ${index + 1}`,
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }))

      const { rerender } = render(<ChatMessages messages={initialMessages} isProcessing={false} streamingContent="" onStopGeneration={vi.fn()} onRetry={vi.fn()} onCopy={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

      const startTime = performance.now()

      // 新しいメッセージを追加
      const updatedMessages = [...initialMessages, {
        id: 'new-msg',
        role: 'assistant',
        content: '新しいメッセージです',
        timestamp: new Date(),
        images: [],
        audioFiles: [],
        textFiles: []
      }]

      rerender(<ChatMessages messages={updatedMessages} isProcessing={false} streamingContent="" onStopGeneration={vi.fn()} onRetry={vi.fn()} onCopy={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('新しいメッセージです')).toBeInTheDocument()
      })

      const endTime = performance.now()
      const updateTime = endTime - startTime

      expect(updateTime).toBeLessThan(100) // 100ms以内
      console.log(`メッセージ追加時間: ${updateTime.toFixed(2)}ms`)
    })
  })

  describe('WhisperJobList Performance', () => {
    it('大量ジョブ（500件）の表示が2秒以内に完了する', async () => {
      const generateLargeJobSet = (count: number) => {
        return Array.from({ length: count }, (_, index) => ({
          jobId: `job-${index}`,
          fileHash: `hash-${index}`,
          filename: `audio-${index}.wav`,
          status: ['completed', 'processing', 'failed', 'queued'][index % 4],
          createdAt: new Date(Date.now() - index * 60000).toISOString(),
          description: `テスト音声ファイル ${index + 1}`,
          tags: [`tag-${index % 10}`, `category-${index % 5}`],
          language: ['ja', 'en', 'ko'][index % 3]
        }))
      }

      const largeJobSet = generateLargeJobSet(500)
      const mockProps = {
        jobs: largeJobSet,
        onJobSelect: vi.fn(),
        onRefresh: vi.fn(),
        onCancel: vi.fn(),
        onRetry: vi.fn(),
        filterStatus: 'all',
        onFilterChange: vi.fn(),
        sortOrder: 'date-desc',
        onSortChange: vi.fn()
      }

      const startTime = performance.now()
      
      render(<WhisperJobList {...mockProps} />)
      
      // テーブルヘッダーとジョブ項目の表示を確認
      await waitFor(() => {
        expect(screen.getByText('ファイル名')).toBeInTheDocument()
        expect(screen.getByText('audio-0.wav')).toBeInTheDocument()
      }, { timeout: 5000 })

      const endTime = performance.now()
      const renderTime = endTime - startTime

      expect(renderTime).toBeLessThan(2000) // 2秒以内
      console.log(`大量ジョブレンダリング時間: ${renderTime.toFixed(2)}ms`)
    })

    it('フィルタリング処理が50ms以内に完了する', async () => {
      const jobs = Array.from({ length: 200 }, (_, index) => ({
        jobId: `job-${index}`,
        fileHash: `hash-${index}`,
        filename: `audio-${index}.wav`,
        status: ['completed', 'processing', 'failed', 'queued'][index % 4],
        createdAt: new Date(Date.now() - index * 60000).toISOString(),
        description: `テスト音声ファイル ${index + 1}`,
        tags: [`tag-${index % 10}`],
        language: 'ja'
      }))

      const { rerender } = render(
        <WhisperJobList 
          jobs={jobs}
          onJobSelect={vi.fn()}
          onRefresh={vi.fn()}
          onCancel={vi.fn()}
          onRetry={vi.fn()}
          filterStatus="all"
          onFilterChange={vi.fn()}
          sortOrder="date-desc"
          onSortChange={vi.fn()}
        />
      )

      const startTime = performance.now()

      // フィルタを'completed'に変更
      rerender(
        <WhisperJobList 
          jobs={jobs}
          onJobSelect={vi.fn()}
          onRefresh={vi.fn()}
          onCancel={vi.fn()}
          onRetry={vi.fn()}
          filterStatus="completed"
          onFilterChange={vi.fn()}
          sortOrder="date-desc"
          onSortChange={vi.fn()}
        />
      )

      await waitFor(() => {
        // フィルタリング結果の確認
        const visibleRows = screen.getAllByRole('row')
        expect(visibleRows.length).toBeGreaterThan(1) // ヘッダー + データ行
      })

      const endTime = performance.now()
      const filterTime = endTime - startTime

      expect(filterTime).toBeLessThan(50) // 50ms以内
      console.log(`フィルタリング時間: ${filterTime.toFixed(2)}ms`)
    })
  })

  describe('Memory Usage Tests', () => {
    it('メモリリークが発生しないことを確認する', async () => {
      // GCを強制実行
      if (global.gc) {
        global.gc()
      }

      const initialMemory = process.memoryUsage()

      // 大量レンダリングを複数回実行
      for (let i = 0; i < 10; i++) {
        const messages = Array.from({ length: 100 }, (_, index) => ({
          id: `msg-${i}-${index}`,
          role: 'user',
          content: `メッセージ ${i}-${index}`,
          timestamp: new Date(),
          images: [],
          audioFiles: [],
          textFiles: []
        }))

        const { unmount } = render(
          <ChatMessages 
            messages={messages}
            isProcessing={false}
            streamingContent=""
            onStopGeneration={vi.fn()}
            onRetry={vi.fn()}
            onCopy={vi.fn()}
            onEdit={vi.fn()}
            onDelete={vi.fn()}
          />
        )

        // コンポーネントをアンマウント
        unmount()
      }

      // GCを再実行
      if (global.gc) {
        global.gc()
      }

      const finalMemory = process.memoryUsage()
      const memoryIncrease = finalMemory.heapUsed - initialMemory.heapUsed

      // メモリ増加が10MB以内であることを確認（許容範囲）
      expect(memoryIncrease).toBeLessThan(10 * 1024 * 1024)
      console.log(`メモリ増加量: ${(memoryIncrease / 1024 / 1024).toFixed(2)}MB`)
    })
  })

  describe('Concurrent Rendering Tests', () => {
    it('同時実行される複数のコンポーネントが適切に処理される', async () => {
      const promises = []

      // 10個のコンポーネントを同時にレンダリング
      for (let i = 0; i < 10; i++) {
        const promise = new Promise((resolve) => {
          const messages = [{
            id: `msg-${i}`,
            role: 'user',
            content: `並行テストメッセージ ${i}`,
            timestamp: new Date(),
            images: [],
            audioFiles: [],
            textFiles: []
          }]

          const { container } = render(
            <ChatMessages 
              messages={messages}
              isProcessing={false}
              streamingContent=""
              onStopGeneration={vi.fn()}
              onRetry={vi.fn()}
              onCopy={vi.fn()}
              onEdit={vi.fn()}
              onDelete={vi.fn()}
            />
          )

          resolve(container)
        })

        promises.push(promise)
      }

      const startTime = performance.now()
      const results = await Promise.all(promises)
      const endTime = performance.now()

      expect(results).toHaveLength(10)
      expect(endTime - startTime).toBeLessThan(1000) // 1秒以内
      console.log(`並行レンダリング時間: ${(endTime - startTime).toFixed(2)}ms`)
    })
  })
})