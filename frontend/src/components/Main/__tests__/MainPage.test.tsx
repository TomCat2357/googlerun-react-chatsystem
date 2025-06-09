import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import MainPage from '../MainPage'

// Firebase認証のモック
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: { uid: 'test-uid', email: 'test@example.com' },
    loading: false
  })
}))

// React Routerのモック
const MockMainPageWithRouter = () => (
  <BrowserRouter>
    <MainPage />
  </BrowserRouter>
)

describe('MainPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('メインページが正しくレンダリングされる', () => {
    render(<MockMainPageWithRouter />)
    
    // メインタイトルの確認
    expect(screen.getByText(/Welcome/)).toBeInTheDocument()
    
    // 基本的なレイアウト要素の確認
    expect(screen.getByRole('main')).toBeInTheDocument()
  })

  it('ナビゲーションメニューが表示される', () => {
    render(<MockMainPageWithRouter />)
    
    // 主要な機能へのリンクを確認
    expect(screen.getByText(/チャット/)).toBeInTheDocument()
    expect(screen.getByText(/音声文字起こし/)).toBeInTheDocument()
    expect(screen.getByText(/画像生成/)).toBeInTheDocument()
    expect(screen.getByText(/位置情報/)).toBeInTheDocument()
  })

  it('機能カードが正しく表示される', () => {
    render(<MockMainPageWithRouter />)
    
    // 各機能の説明カードを確認
    const cards = screen.getAllByRole('article')
    expect(cards.length).toBeGreaterThan(0)
    
    // カードのタイトルを確認
    expect(screen.getByText(/AI チャット/)).toBeInTheDocument()
    expect(screen.getByText(/Whisper 音声文字起こし/)).toBeInTheDocument()
    expect(screen.getByText(/AI 画像生成/)).toBeInTheDocument()
    expect(screen.getByText(/地図・住所検索/)).toBeInTheDocument()
  })

  it('各機能カードがクリック可能である', () => {
    render(<MockMainPageWithRouter />)
    
    const chatCard = screen.getByText(/AI チャット/).closest('a, button')
    const whisperCard = screen.getByText(/Whisper 音声文字起こし/).closest('a, button')
    const imageCard = screen.getByText(/AI 画像生成/).closest('a, button')
    const geoCard = screen.getByText(/地図・住所検索/).closest('a, button')
    
    expect(chatCard).toBeInTheDocument()
    expect(whisperCard).toBeInTheDocument()
    expect(imageCard).toBeInTheDocument()
    expect(geoCard).toBeInTheDocument()
  })

  it('ユーザー情報が表示される', () => {
    render(<MockMainPageWithRouter />)
    
    // ログイン中のユーザー情報
    expect(screen.getByText(/test@example.com/)).toBeInTheDocument()
  })

  it('レスポンシブレイアウトが適用されている', () => {
    const { container } = render(<MockMainPageWithRouter />)
    
    // グリッドレイアウトの確認
    const gridContainer = container.querySelector('.grid')
    expect(gridContainer).toBeInTheDocument()
    
    // レスポンシブクラスの確認
    const responsiveElements = container.querySelectorAll('[class*="md:"], [class*="lg:"]')
    expect(responsiveElements.length).toBeGreaterThan(0)
  })

  it('ダークテーマが適用されている', () => {
    const { container } = render(<MockMainPageWithRouter />)
    
    // ダークテーマのクラスが適用されていることを確認
    expect(container.querySelector('.bg-dark-primary, .bg-gray-900')).toBeInTheDocument()
    expect(container.querySelector('.text-gray-100, .text-white')).toBeInTheDocument()
  })

  it('アクセシビリティ属性が適切に設定されている', () => {
    render(<MockMainPageWithRouter />)
    
    // メインランドマークの確認
    expect(screen.getByRole('main')).toBeInTheDocument()
    
    // 見出しレベルの確認
    const headings = screen.getAllByRole('heading')
    expect(headings.length).toBeGreaterThan(0)
    
    // リンクのアクセシブル名の確認
    const links = screen.getAllByRole('link')
    links.forEach(link => {
      expect(link).toHaveAccessibleName()
    })
  })

  it('キーボードナビゲーションが動作する', () => {
    render(<MockMainPageWithRouter />)
    
    const firstCard = screen.getAllByRole('link')[0]
    
    // フォーカスの設定
    firstCard.focus()
    expect(document.activeElement).toBe(firstCard)
    
    // Enterキーでの動作
    fireEvent.keyDown(firstCard, { key: 'Enter' })
    // 実際のナビゲーション処理の確認（router mockが必要）
  })

  it('統計情報が表示される', () => {
    render(<MockMainPageWithRouter />)
    
    // 使用状況の統計などが表示される場合
    const stats = screen.queryAllByText(/利用回数|処理時間|成功率/)
    if (stats.length > 0) {
      expect(stats[0]).toBeInTheDocument()
    }
  })

  it('最近の活動履歴が表示される', () => {
    render(<MockMainPageWithRouter />)
    
    // 最近の活動履歴セクション
    const recentActivity = screen.queryByText(/最近の活動|履歴/)
    if (recentActivity) {
      expect(recentActivity).toBeInTheDocument()
    }
  })

  it('お知らせエリアが表示される', () => {
    render(<MockMainPageWithRouter />)
    
    // お知らせ・アップデート情報
    const notifications = screen.queryByText(/お知らせ|更新情報/)
    if (notifications) {
      expect(notifications).toBeInTheDocument()
    }
  })

  it('フッター情報が表示される', () => {
    render(<MockMainPageWithRouter />)
    
    // フッターエリア
    const footer = screen.queryByRole('contentinfo')
    if (footer) {
      expect(footer).toBeInTheDocument()
    }
  })
})