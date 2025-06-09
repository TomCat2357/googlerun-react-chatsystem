import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import WhisperJobList from '../WhisperJobList'

// Firebase認証のモック
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: { uid: 'test-uid' },
    loading: false
  })
}))

describe('WhisperJobList', () => {
  const mockJobs = [
    {
      jobId: 'job1',
      fileHash: 'hash1',
      filename: 'test1.wav',
      status: 'completed',
      createdAt: '2024-01-01T00:00:00Z',
      description: 'テスト音声1',
      tags: ['tag1', 'tag2'],
      language: 'ja'
    },
    {
      jobId: 'job2',
      fileHash: 'hash2',
      filename: 'test2.mp3',
      status: 'processing',
      createdAt: '2024-01-02T00:00:00Z',
      description: 'テスト音声2',
      tags: ['tag3'],
      language: 'en'
    },
    {
      jobId: 'job3',
      fileHash: 'hash3',
      filename: 'test3.wav',
      status: 'failed',
      createdAt: '2024-01-03T00:00:00Z',
      description: 'テスト音声3',
      errorMessage: 'Processing failed',
      tags: [],
      language: 'ja'
    }
  ]

  const mockProps = {
    jobs: mockJobs,
    onJobSelect: vi.fn(),
    onRefresh: vi.fn(),
    onCancel: vi.fn(),
    onRetry: vi.fn(),
    filterStatus: 'all',
    onFilterChange: vi.fn(),
    sortOrder: 'date-desc',
    onSortChange: vi.fn()
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('ジョブ一覧が正しく表示される', () => {
    render(<WhisperJobList {...mockProps} />)
    
    expect(screen.getByText('test1.wav')).toBeInTheDocument()
    expect(screen.getByText('test2.mp3')).toBeInTheDocument()
    expect(screen.getByText('test3.wav')).toBeInTheDocument()
  })

  it('ジョブステータスが正しく表示される', () => {
    render(<WhisperJobList {...mockProps} />)
    
    expect(screen.getByText('完了')).toBeInTheDocument()
    expect(screen.getByText('処理中')).toBeInTheDocument()
    expect(screen.getByText('失敗')).toBeInTheDocument()
  })

  it('ジョブクリック時にonJobSelectが呼ばれる', () => {
    render(<WhisperJobList {...mockProps} />)
    
    const jobRow = screen.getByText('test1.wav').closest('tr')
    fireEvent.click(jobRow!)
    
    expect(mockProps.onJobSelect).toHaveBeenCalledWith('job1', 'hash1')
  })

  it('ステータスフィルターが正しく動作する', () => {
    render(<WhisperJobList {...mockProps} />)
    
    const statusFilter = screen.getByDisplayValue('全て')
    fireEvent.change(statusFilter, { target: { value: 'completed' } })
    
    expect(mockProps.onFilterChange).toHaveBeenCalledWith('completed')
  })

  it('ソート機能が正しく動作する', () => {
    render(<WhisperJobList {...mockProps} />)
    
    const sortSelect = screen.getByDisplayValue('作成日時（新しい順）')
    fireEvent.change(sortSelect, { target: { value: 'date-asc' } })
    
    expect(mockProps.onSortChange).toHaveBeenCalledWith('date-asc')
  })

  it('キャンセルボタンが処理中ジョブに表示される', () => {
    render(<WhisperJobList {...mockProps} />)
    
    // 処理中のジョブにキャンセルボタンがあることを確認
    const processingJobRow = screen.getByText('test2.mp3').closest('tr')
    expect(processingJobRow).toBeInTheDocument()
    
    const cancelButtons = screen.getAllByText('キャンセル')
    expect(cancelButtons).toHaveLength(1)
  })

  it('再実行ボタンが失敗ジョブに表示される', () => {
    render(<WhisperJobList {...mockProps} />)
    
    // 失敗したジョブに再実行ボタンがあることを確認
    const retryButtons = screen.getAllByText('再実行')
    expect(retryButtons).toHaveLength(1)
  })

  it('キャンセルボタンクリック時にonCancelが呼ばれる', () => {
    render(<WhisperJobList {...mockProps} />)
    
    const cancelButton = screen.getByText('キャンセル')
    fireEvent.click(cancelButton)
    
    expect(mockProps.onCancel).toHaveBeenCalledWith('job2', 'hash2')
  })

  it('再実行ボタンクリック時にonRetryが呼ばれる', () => {
    render(<WhisperJobList {...mockProps} />)
    
    const retryButton = screen.getByText('再実行')
    fireEvent.click(retryButton)
    
    expect(mockProps.onRetry).toHaveBeenCalledWith('job3', 'hash3')
  })

  it('リフレッシュボタンが正しく動作する', () => {
    render(<WhisperJobList {...mockProps} />)
    
    const refreshButton = screen.getByText('更新')
    fireEvent.click(refreshButton)
    
    expect(mockProps.onRefresh).toHaveBeenCalled()
  })

  it('ジョブが空の場合に適切なメッセージが表示される', () => {
    const emptyProps = { ...mockProps, jobs: [] }
    render(<WhisperJobList {...emptyProps} />)
    
    expect(screen.getByText(/ジョブがありません/)).toBeInTheDocument()
  })

  it('エラーメッセージが表示される', () => {
    render(<WhisperJobList {...mockProps} />)
    
    expect(screen.getByText('Processing failed')).toBeInTheDocument()
  })

  it('タグが正しく表示される', () => {
    render(<WhisperJobList {...mockProps} />)
    
    expect(screen.getByText('tag1')).toBeInTheDocument()
    expect(screen.getByText('tag2')).toBeInTheDocument()
    expect(screen.getByText('tag3')).toBeInTheDocument()
  })

  it('言語情報が正しく表示される', () => {
    render(<WhisperJobList {...mockProps} />)
    
    // 日本語のジョブが表示されることを確認
    const japaneseJobs = screen.getAllByText('ja')
    expect(japaneseJobs).toHaveLength(2)
    
    // 英語のジョブが表示されることを確認
    expect(screen.getByText('en')).toBeInTheDocument()
  })
})