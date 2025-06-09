import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

// テスト用のシンプルなボタンコンポーネント（例）
const SimpleButton = ({ onClick, children, disabled = false }) => (
  <button onClick={onClick} disabled={disabled}>
    {children}
  </button>
)

describe('SimpleButton（例として）', () => {
  it('🔵 ボタンが画面に表示される', () => {
    // Arrange: ボタンを画面に表示
    render(<SimpleButton>クリックして</SimpleButton>)
    
    // Assert: ボタンが存在することを確認
    expect(screen.getByRole('button')).toBeInTheDocument()
    expect(screen.getByText('クリックして')).toBeInTheDocument()
  })

  it('🟢 ボタンをクリックしたら関数が呼ばれる', () => {
    // Arrange: モック関数を準備
    const mockClick = vi.fn()
    render(<SimpleButton onClick={mockClick}>クリックして</SimpleButton>)
    
    // Act: ボタンをクリック
    fireEvent.click(screen.getByRole('button'))
    
    // Assert: 関数が1回呼ばれたことを確認
    expect(mockClick).toHaveBeenCalledTimes(1)
  })

  it('🔴 無効状態のボタンはクリックできない', () => {
    // Arrange: 無効なボタンを表示
    const mockClick = vi.fn()
    render(
      <SimpleButton onClick={mockClick} disabled={true}>
        無効ボタン
      </SimpleButton>
    )
    
    // Act: ボタンをクリックしようとする
    fireEvent.click(screen.getByRole('button'))
    
    // Assert: 関数が呼ばれていないことを確認
    expect(mockClick).not.toHaveBeenCalled()
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
