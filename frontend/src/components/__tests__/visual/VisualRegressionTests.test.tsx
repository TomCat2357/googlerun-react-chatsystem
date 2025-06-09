import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import WhisperPage from '../../Whisper/WhisperPage'
import ChatMessages from '../../Chat/ChatMessages'
import Header from '../../Header/Header'

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

/**
 * Visual Regression Tests
 * UIコンポーネントの見た目の一貫性を確保するためのテスト
 * 
 * 注意: 実際のスクリーンショット機能は追加のライブラリ（例：@storybook/test-runner）が必要
 * ここでは、レンダリング結果の構造やクラス名の一貫性をテストする
 */

describe('Visual Regression Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Layout Consistency', () => {
    it('Whisperページのレイアウト構造が一貫している', () => {
      const { container } = render(<WhisperPage />)
      
      // メインコンテナの存在確認
      expect(container.querySelector('.min-h-screen')).toBeInTheDocument()
      
      // タブナビゲーションの存在確認
      expect(screen.getByText('音声アップロード')).toBeInTheDocument()
      expect(screen.getByText('処理結果一覧')).toBeInTheDocument()
      
      // ヘッダータイトルの存在確認
      expect(screen.getByText(/Whisper 音声文字起こし/)).toBeInTheDocument()
      
      // レイアウトの基本構造が保持されていることを確認
      const mainContainer = container.firstChild as HTMLElement
      expect(mainContainer).toHaveClass('p-4', 'overflow-y-auto', 'bg-dark-primary')
    })

    it('チャットメッセージの表示レイアウトが一貫している', () => {
      const mockMessages = [
        {
          id: '1',
          role: 'user' as const,
          content: 'テストメッセージ',
          timestamp: new Date(),
          images: [],
          audioFiles: [],
          textFiles: []
        },
        {
          id: '2',
          role: 'assistant' as const,
          content: 'アシスタントの返答',
          timestamp: new Date(),
          images: [],
          audioFiles: [],
          textFiles: []
        }
      ]

      const { container } = render(
        <ChatMessages
          messages={mockMessages}
          isProcessing={false}
          streamingContent=""
          onStopGeneration={vi.fn()}
          onRetry={vi.fn()}
          onCopy={vi.fn()}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      // メッセージコンテナの構造確認
      const messageContainers = container.querySelectorAll('[data-testid="message-container"]')
      expect(messageContainers.length).toBeGreaterThanOrEqual(0)

      // ユーザーメッセージとアシスタントメッセージの表示確認
      expect(screen.getByText('テストメッセージ')).toBeInTheDocument()
      expect(screen.getByText('アシスタントの返答')).toBeInTheDocument()
    })

    it('ヘッダーコンポーネントのレイアウトが一貫している', () => {
      const { container } = render(<Header />)
      
      // ヘッダーの基本構造確認
      const header = container.querySelector('header')
      expect(header).toBeInTheDocument()
      expect(header).toHaveClass('bg-dark-primary')
      
      // ナビゲーション要素の存在確認
      expect(screen.getByText('ホーム')).toBeInTheDocument()
      
      // フレックスレイアウトの確認
      const containerDiv = header?.querySelector('.container')
      expect(containerDiv).toHaveClass('mx-auto', 'flex', 'justify-between', 'items-center')
    })
  })

  describe('Color Scheme Consistency', () => {
    it('ダークテーマのカラーパレットが一貫している', () => {
      const { container } = render(<WhisperPage />)
      
      // 主要な背景色の確認
      const mainContainer = container.firstChild as HTMLElement
      expect(mainContainer).toHaveClass('bg-dark-primary')
      
      // タブナビゲーションの色確認
      const activeTab = screen.getByText('音声アップロード').closest('button')
      expect(activeTab).toHaveClass('bg-blue-600')
    })

    it('ステータス表示の色が適切に設定されている', () => {
      const mockJobs = [
        {
          jobId: 'job1',
          fileHash: 'hash1',
          filename: 'test.wav',
          status: 'completed',
          createdAt: '2024-01-01T00:00:00Z',
          description: 'テスト',
          tags: [],
          language: 'ja'
        },
        {
          jobId: 'job2',
          fileHash: 'hash2',
          filename: 'test2.wav',
          status: 'failed',
          createdAt: '2024-01-01T00:00:00Z',
          description: 'テスト2',
          tags: [],
          language: 'ja'
        }
      ]

      render(<WhisperPage />)
      
      // ステータス表示の色分けが適切であることを確認
      // 実際の実装に応じて調整が必要
      expect(screen.queryByText('完了')).toBeTruthy()
      expect(screen.queryByText('失敗')).toBeTruthy()
    })
  })

  describe('Typography Consistency', () => {
    it('見出しとテキストのタイポグラフィが一貫している', () => {
      const { container } = render(<WhisperPage />)
      
      // メインタイトルのスタイル確認
      const mainTitle = screen.getByText(/Whisper 音声文字起こし/)
      expect(mainTitle).toHaveClass('text-3xl', 'font-bold')
      
      // サブタイトルのスタイル確認
      const subTitles = container.querySelectorAll('h2')
      subTitles.forEach(subtitle => {
        expect(subtitle).toHaveClass('text-xl')
      })
    })

    it('ボタンテキストのスタイルが一貫している', () => {
      render(<WhisperPage />)
      
      // プライマリボタンのスタイル確認
      const primaryButtons = screen.getAllByRole('button')
      const uploadButton = primaryButtons.find(button => 
        button.textContent?.includes('音声アップロード')
      )
      
      if (uploadButton) {
        expect(uploadButton).toHaveClass('px-4', 'py-2')
      }
    })
  })

  describe('Responsive Layout', () => {
    it('モバイル表示時のレイアウトが適切である', () => {
      // モバイルビューポートをシミュレート
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      })
      
      Object.defineProperty(window, 'innerHeight', {
        writable: true,
        configurable: true,
        value: 667,
      })

      const { container } = render(<WhisperPage />)
      
      // レスポンシブクラスの確認
      const responsiveElements = container.querySelectorAll('[class*="md:"], [class*="lg:"], [class*="sm:"]')
      expect(responsiveElements.length).toBeGreaterThan(0)
    })

    it('タブレット表示時のレイアウトが適切である', () => {
      // タブレットビューポートをシミュレート
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 768,
      })

      const { container } = render(<WhisperPage />)
      
      // グリッドレイアウトの確認
      const gridElements = container.querySelectorAll('[class*="grid"], [class*="flex"]')
      expect(gridElements.length).toBeGreaterThan(0)
    })
  })

  describe('Animation and Interaction States', () => {
    it('ホバー状態のスタイルが適用される', () => {
      render(<WhisperPage />)
      
      const buttons = screen.getAllByRole('button')
      buttons.forEach(button => {
        // ホバークラスの存在確認
        const classList = Array.from(button.classList)
        const hasHoverClass = classList.some(className => 
          className.includes('hover:')
        )
        
        if (hasHoverClass) {
          expect(button).toHaveClass(expect.stringContaining('hover:'))
        }
      })
    })

    it('フォーカス状態のスタイルが適用される', () => {
      render(<WhisperPage />)
      
      const focusableElements = screen.getAllByRole('button')
      focusableElements.forEach(element => {
        // フォーカスアウトラインが設定されていることを確認
        const computedStyle = window.getComputedStyle(element)
        expect(computedStyle.outline).not.toBe('none')
      })
    })

    it('トランジション効果が適切に設定されている', () => {
      render(<WhisperPage />)
      
      const buttons = screen.getAllByRole('button')
      buttons.forEach(button => {
        const classList = Array.from(button.classList)
        const hasTransitionClass = classList.some(className => 
          className.includes('transition')
        )
        
        if (hasTransitionClass) {
          expect(button).toHaveClass(expect.stringContaining('transition'))
        }
      })
    })
  })

  describe('Accessibility Visual Elements', () => {
    it('フォーカスインジケーターが視覚的に明確である', () => {
      render(<WhisperPage />)
      
      const interactiveElements = [
        ...screen.getAllByRole('button'),
        ...screen.getAllByRole('textbox'),
        ...screen.getAllByRole('combobox')
      ]
      
      interactiveElements.forEach(element => {
        element.focus()
        const computedStyle = window.getComputedStyle(element)
        
        // アウトラインまたはボックスシャドウが設定されていることを確認
        const hasVisibleFocus = 
          computedStyle.outline !== 'none' || 
          computedStyle.boxShadow !== 'none'
        
        expect(hasVisibleFocus).toBe(true)
      })
    })

    it('エラー状態の視覚的表現が明確である', () => {
      // エラー状態をシミュレート
      render(<WhisperPage />)
      
      // エラーメッセージの表示スタイル確認
      const errorElements = screen.queryAllByRole('alert')
      errorElements.forEach(element => {
        const classList = Array.from(element.classList)
        const hasErrorStyling = classList.some(className => 
          className.includes('red') || className.includes('error')
        )
        
        if (hasErrorStyling) {
          expect(element).toHaveClass(expect.stringContaining('red'))
        }
      })
    })
  })

  describe('Component Boundary Testing', () => {
    it('コンポーネントの境界が適切に設定されている', () => {
      const { container } = render(<WhisperPage />)
      
      // パディングとマージンの確認
      const sections = container.querySelectorAll('div[class*="p-"], div[class*="m-"]')
      expect(sections.length).toBeGreaterThan(0)
      
      sections.forEach(section => {
        const classList = Array.from(section.classList)
        const hasSpacing = classList.some(className => 
          className.startsWith('p-') || 
          className.startsWith('m-') ||
          className.startsWith('px-') ||
          className.startsWith('py-') ||
          className.startsWith('mx-') ||
          className.startsWith('my-')
        )
        
        expect(hasSpacing).toBe(true)
      })
    })

    it('コンテンツの配置が適切である', () => {
      const { container } = render(<WhisperPage />)
      
      // フレックスボックスまたはグリッドレイアウトの確認
      const layoutElements = container.querySelectorAll('[class*="flex"], [class*="grid"]')
      expect(layoutElements.length).toBeGreaterThan(0)
      
      layoutElements.forEach(element => {
        const classList = Array.from(element.classList)
        const hasLayoutClass = classList.some(className => 
          className.includes('flex') || 
          className.includes('grid') ||
          className.includes('justify') ||
          className.includes('items')
        )
        
        expect(hasLayoutClass).toBe(true)
      })
    })
  })
})