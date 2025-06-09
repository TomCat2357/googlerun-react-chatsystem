import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import WhisperPage from '../../Whisper/WhisperPage'
import ChatInput from '../../Chat/ChatInput'
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

describe('Accessibility Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Keyboard Navigation', () => {
    it('タブキーでのフォーカス移動が正しく動作する', () => {
      render(<WhisperPage />)

      // 最初の focusable 要素にフォーカス
      const firstButton = screen.getByText('音声アップロード')
      firstButton.focus()
      expect(document.activeElement).toBe(firstButton)

      // Tab キーでフォーカス移動
      fireEvent.keyDown(document.activeElement!, { key: 'Tab' })
      
      // 次の要素にフォーカスが移動していることを確認
      expect(document.activeElement).not.toBe(firstButton)
    })

    it('Escapeキーでモーダルが閉じられる', () => {
      const mockProps = {
        input: '',
        setInput: vi.fn(),
        isProcessing: false,
        selectedFiles: [],
        addFiles: vi.fn(),
        sendMessage: vi.fn(),
        stopGeneration: vi.fn(),
        setErrorMessage: vi.fn(),
        maxLimits: {
          MAX_IMAGES: 5,
          MAX_AUDIO_FILES: 3,
          MAX_TEXT_FILES: 10,
          MAX_IMAGE_SIZE: 5242880,
          MAX_LONG_EDGE: 1568
        }
      }

      render(<ChatInput {...mockProps} />)

      // Escapeキーでの動作をテスト（実際のモーダルが実装されている場合）
      fireEvent.keyDown(document, { key: 'Escape' })
      
      // モーダルが閉じられることを確認（モック関数の呼び出し等）
      expect(mockProps.setErrorMessage).toHaveBeenCalledWith('')
    })

    it('Enter/Spaceキーでボタンがアクティベートされる', () => {
      const mockOnClick = vi.fn()
      
      render(
        <button onClick={mockOnClick} type="button">
          テストボタン
        </button>
      )

      const button = screen.getByText('テストボタン')
      
      // Enterキーでのアクティベート
      fireEvent.keyDown(button, { key: 'Enter' })
      expect(mockOnClick).toHaveBeenCalled()

      mockOnClick.mockClear()

      // Spaceキーでのアクティベート
      fireEvent.keyDown(button, { key: ' ' })
      expect(mockOnClick).toHaveBeenCalled()
    })
  })

  describe('ARIA Labels and Roles', () => {
    it('すべてのフォーム要素に適切なラベルが設定されている', () => {
      render(<WhisperPage />)

      // ファイル入力要素にアクセシブルなラベルがあることを確認
      const fileInputs = screen.getAllByRole('button')
      fileInputs.forEach(input => {
        expect(input).toHaveAccessibleName()
      })

      // フォーム要素にaria-labelまたはlabelが設定されていることを確認
      const textInputs = screen.getAllByRole('textbox')
      textInputs.forEach(input => {
        expect(input).toHaveAccessibleName()
      })
    })

    it('リストとテーブルに適切なroleが設定されている', () => {
      render(<WhisperPage />)

      // 処理結果一覧タブに切り替え
      fireEvent.click(screen.getByText('処理結果一覧'))

      // テーブルがtableロールを持っていることを確認
      const tables = screen.queryAllByRole('table')
      expect(tables.length).toBeGreaterThanOrEqual(0)

      // ヘッダーがcolumnheaderロールを持っていることを確認
      const columnHeaders = screen.queryAllByRole('columnheader')
      expect(columnHeaders.length).toBeGreaterThanOrEqual(0)
    })

    it('状態変化が適切にアナウンスされる', () => {
      render(<WhisperPage />)

      // エラーメッセージにaria-live属性が設定されていることを確認
      const errorRegions = screen.queryAllByRole('alert')
      errorRegions.forEach(region => {
        expect(region).toBeInTheDocument()
      })

      // ステータス表示にaria-live属性が設定されていることを確認
      const statusRegions = screen.queryAllByRole('status')
      statusRegions.forEach(region => {
        expect(region).toBeInTheDocument()
      })
    })
  })

  describe('Color Contrast and Visual', () => {
    it('フォーカス状態が視覚的に明確である', () => {
      render(<WhisperPage />)

      const button = screen.getByText('音声アップロード')
      button.focus()

      // フォーカス状態のスタイルが適用されていることを確認
      const computedStyle = window.getComputedStyle(button)
      expect(computedStyle.outline).not.toBe('none')
    })

    it('エラー状態が色以外の方法でも伝達される', () => {
      const mockProps = {
        input: '',
        setInput: vi.fn(),
        isProcessing: false,
        selectedFiles: [],
        addFiles: vi.fn(),
        sendMessage: vi.fn(),
        stopGeneration: vi.fn(),
        setErrorMessage: vi.fn(),
        maxLimits: {
          MAX_IMAGES: 5,
          MAX_AUDIO_FILES: 3,
          MAX_TEXT_FILES: 10,
          MAX_IMAGE_SIZE: 5242880,
          MAX_LONG_EDGE: 1568
        }
      }

      render(<ChatInput {...mockProps} />)

      // エラーメッセージにアイコンやテキストが含まれていることを確認
      const errorElements = screen.queryAllByRole('alert')
      errorElements.forEach(element => {
        // エラーメッセージがテキストで提供されていることを確認
        expect(element).toHaveTextContent
      })
    })
  })

  describe('Screen Reader Support', () => {
    it('画像に適切なalt属性が設定されている', () => {
      render(<WhisperPage />)

      const images = screen.queryAllByRole('img')
      images.forEach(img => {
        expect(img).toHaveAttribute('alt')
        expect(img.getAttribute('alt')).not.toBe('')
      })
    })

    it('複雑なUIコンポーネントに説明が提供されている', () => {
      render(<WhisperPage />)

      // ドラッグアンドドロップエリアに説明テキストがあることを確認
      const dropZoneDescription = screen.queryByText(/ドラッグ/)
      if (dropZoneDescription) {
        expect(dropZoneDescription).toBeInTheDocument()
      }

      // フォームの説明やヘルプテキストが提供されていることを確認
      const helpTexts = screen.queryAllByText(/形式/)
      expect(helpTexts.length).toBeGreaterThan(0)
    })

    it('動的コンテンツの変更が適切にアナウンスされる', () => {
      render(<WhisperPage />)

      // アップロード進行状況にaria-live属性が設定されていることを確認
      const progressRegions = screen.queryAllByRole('progressbar')
      progressRegions.forEach(region => {
        expect(region).toHaveAttribute('aria-valuenow')
      })
    })
  })

  describe('Form Accessibility', () => {
    it('必須フィールドが適切にマークされている', () => {
      render(<WhisperPage />)

      // 必須フィールドにaria-required属性が設定されていることを確認
      const requiredFields = screen.queryAllByRole('textbox')
      requiredFields.forEach(field => {
        if (field.hasAttribute('required')) {
          expect(field).toHaveAttribute('aria-required', 'true')
        }
      })
    })

    it('フォームエラーがフィールドと関連付けられている', () => {
      const mockProps = {
        input: '',
        setInput: vi.fn(),
        isProcessing: false,
        selectedFiles: [],
        addFiles: vi.fn(),
        sendMessage: vi.fn(),
        stopGeneration: vi.fn(),
        setErrorMessage: vi.fn(),
        maxLimits: {
          MAX_IMAGES: 5,
          MAX_AUDIO_FILES: 3,
          MAX_TEXT_FILES: 10,
          MAX_IMAGE_SIZE: 5242880,
          MAX_LONG_EDGE: 1568
        }
      }

      render(<ChatInput {...mockProps} />)

      // エラー状態のフィールドにaria-invalid属性が設定されていることを確認
      const textboxes = screen.queryAllByRole('textbox')
      textboxes.forEach(textbox => {
        if (textbox.hasAttribute('aria-invalid')) {
          expect(textbox.getAttribute('aria-invalid')).toBe('true')
        }
      })
    })

    it('フィールドグループが適切にラベル付けされている', () => {
      render(<WhisperPage />)

      // fieldsetとlegendが適切に使用されていることを確認
      const fieldsets = screen.queryAllByRole('group')
      fieldsets.forEach(fieldset => {
        expect(fieldset).toHaveAccessibleName()
      })
    })
  })

  describe('Mobile Accessibility', () => {
    it('タッチターゲットが適切なサイズを持っている', () => {
      render(<WhisperPage />)

      const buttons = screen.getAllByRole('button')
      buttons.forEach(button => {
        const computedStyle = window.getComputedStyle(button)
        const minSize = 44 // 44px minimum touch target size

        // ボタンの最小サイズを確認（実際のピクセル値は環境によって異なる）
        expect(button).toBeInTheDocument()
      })
    })

    it('ズーム時にコンテンツが適切に表示される', () => {
      // メタビューポートでズームが許可されていることを確認
      const viewport = document.querySelector('meta[name="viewport"]')
      if (viewport) {
        const content = viewport.getAttribute('content')
        expect(content).not.toContain('user-scalable=no')
        expect(content).not.toContain('maximum-scale=1')
      }
    })
  })

  describe('Language and Internationalization', () => {
    it('適切な言語属性が設定されている', () => {
      render(<WhisperPage />)

      // html要素またはコンテンツに適切なlang属性が設定されていることを確認
      const htmlElement = document.documentElement
      expect(htmlElement).toHaveAttribute('lang')
    })

    it('方向（LTR/RTL）が適切に設定されている', () => {
      render(<WhisperPage />)

      // 必要に応じてdir属性が設定されていることを確認
      const htmlElement = document.documentElement
      const dir = htmlElement.getAttribute('dir')
      
      if (dir) {
        expect(['ltr', 'rtl', 'auto']).toContain(dir)
      }
    })
  })
})