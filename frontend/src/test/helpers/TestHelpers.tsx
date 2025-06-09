/**
 * 高度なテストヘルパーユーティリティ
 * Advanced Test Helper Utilities for React Components
 * 
 * この実装は以下の高度なテスト支援機能を提供します：
 * 1. コンテキストプロバイダーの自動設定
 * 2. 非同期操作の待機ヘルパー
 * 3. ユーザーインタラクションシミュレーション
 * 4. アクセシビリティテストヘルパー
 * 5. パフォーマンス測定ユーティリティ
 */

import React, { ReactElement, ReactNode } from 'react'
import { render, RenderOptions, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, expect } from 'vitest'
import { AuthContext } from '../../contexts/AuthContext'
import type { TestUser } from '../factories/TestDataFactory'

// テスト用のAuthContextプロバイダー
interface MockAuthProviderProps {
  children: ReactNode
  user?: TestUser | null
  loading?: boolean
}

export const MockAuthProvider: React.FC<MockAuthProviderProps> = ({ 
  children, 
  user = null, 
  loading = false 
}) => {
  const mockAuthValue = {
    currentUser: user ? {
      uid: user.id,
      email: user.email,
      displayName: user.name
    } : null,
    loading,
    signIn: vi.fn(),
    signOut: vi.fn(),
    signUp: vi.fn()
  }

  return (
    <AuthContext.Provider value={mockAuthValue}>
      {children}
    </AuthContext.Provider>
  )
}

// カスタムレンダー関数
interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  authUser?: TestUser | null
  authLoading?: boolean
  initialPath?: string
}

export function renderWithProviders(
  ui: ReactElement,
  options: CustomRenderOptions = {}
) {
  const {
    authUser,
    authLoading = false,
    initialPath = '/',
    ...renderOptions
  } = options

  // パスを設定（React Routerを使用している場合）
  if (initialPath !== '/') {
    window.history.pushState({}, 'Test Page', initialPath)
  }

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MockAuthProvider user={authUser} loading={authLoading}>
        {children}
      </MockAuthProvider>
    )
  }

  return {
    user: userEvent.setup(),
    ...render(ui, { wrapper: Wrapper, ...renderOptions })
  }
}

/**
 * 非同期操作の待機ヘルパー
 */
export class AsyncTestHelper {
  /**
   * 特定のテキストが表示されるまで待機
   */
  static async waitForText(text: string, timeout: number = 5000) {
    return await waitFor(
      () => {
        expect(screen.getByText(text)).toBeInTheDocument()
      },
      { timeout }
    )
  }

  /**
   * 特定の要素が消えるまで待機
   */
  static async waitForElementToDisappear(testId: string, timeout: number = 5000) {
    return await waitFor(
      () => {
        expect(screen.queryByTestId(testId)).not.toBeInTheDocument()
      },
      { timeout }
    )
  }

  /**
   * ローディング状態の完了を待機
   */
  static async waitForLoadingToComplete(loadingTestId: string = 'loading') {
    await waitFor(() => {
      expect(screen.queryByTestId(loadingTestId)).not.toBeInTheDocument()
    })
  }

  /**
   * API応答のシミュレーション
   */
  static async simulateApiDelay(delay: number = 100) {
    return new Promise(resolve => setTimeout(resolve, delay))
  }

  /**
   * ストリーミングレスポンスのシミュレーション
   */
  static async simulateStreamingResponse(
    chunks: string[],
    onChunk: (chunk: string, accumulated: string) => void,
    chunkDelay: number = 50
  ) {
    let accumulated = ''
    for (const chunk of chunks) {
      await this.simulateApiDelay(chunkDelay)
      accumulated += chunk
      onChunk(chunk, accumulated)
    }
  }
}

/**
 * ユーザーインタラクションシミュレーター
 */
export class UserInteractionSimulator {
  private user: ReturnType<typeof userEvent.setup>

  constructor(user: ReturnType<typeof userEvent.setup>) {
    this.user = user
  }

  /**
   * ファイルアップロードのシミュレーション
   */
  async uploadFile(inputElement: HTMLElement, file: File) {
    await this.user.upload(inputElement, file)
  }

  /**
   * ドラッグ&ドロップのシミュレーション
   */
  async dragAndDrop(sourceElement: HTMLElement, targetElement: HTMLElement) {
    // ドラッグ開始
    await this.user.pointer([
      { target: sourceElement },
      { keys: '[MouseLeft>]' },
    ])

    // ドロップ
    await this.user.pointer([
      { target: targetElement },
      { keys: '[/MouseLeft]' },
    ])
  }

  /**
   * キーボードショートカットのシミュレーション
   */
  async pressShortcut(shortcut: string) {
    await this.user.keyboard(shortcut)
  }

  /**
   * 複雑なフォーム入力のシミュレーション
   */
  async fillForm(formData: Record<string, string>) {
    for (const [fieldName, value] of Object.entries(formData)) {
      const field = screen.getByLabelText(new RegExp(fieldName, 'i'))
      await this.user.clear(field)
      await this.user.type(field, value)
    }
  }

  /**
   * タブナビゲーションのテスト
   */
  async testTabNavigation(expectedFocusOrder: string[]) {
    for (const selector of expectedFocusOrder) {
      await this.user.tab()
      const focusedElement = document.activeElement
      const expectedElement = document.querySelector(selector)
      expect(focusedElement).toBe(expectedElement)
    }
  }
}

/**
 * アクセシビリティテストヘルパー
 */
export class AccessibilityTestHelper {
  /**
   * ARIA属性のテスト
   */
  static testAriaAttributes(element: HTMLElement, expectedAttributes: Record<string, string>) {
    for (const [attribute, expectedValue] of Object.entries(expectedAttributes)) {
      expect(element).toHaveAttribute(`aria-${attribute}`, expectedValue)
    }
  }

  /**
   * キーボードナビゲーションのテスト
   */
  static async testKeyboardNavigation(
    user: ReturnType<typeof userEvent.setup>,
    startElement: HTMLElement,
    expectedOrder: string[]
  ) {
    // 開始要素にフォーカス
    startElement.focus()
    
    for (const selector of expectedOrder) {
      await user.tab()
      const expectedElement = screen.getByTestId(selector) || screen.getByRole(selector)
      expect(document.activeElement).toBe(expectedElement)
    }
  }

  /**
   * スクリーンリーダー用のラベルテスト
   */
  static testScreenReaderLabels(elements: { element: HTMLElement; expectedLabel: string }[]) {
    elements.forEach(({ element, expectedLabel }) => {
      const accessibleName = element.getAttribute('aria-label') || 
                           element.getAttribute('aria-labelledby') ||
                           (element as HTMLInputElement).labels?.[0]?.textContent

      expect(accessibleName).toContain(expectedLabel)
    })
  }

  /**
   * フォーカス管理のテスト
   */
  static async testFocusManagement(
    user: ReturnType<typeof userEvent.setup>,
    trigger: HTMLElement,
    expectedFocusTarget: HTMLElement
  ) {
    await user.click(trigger)
    expect(document.activeElement).toBe(expectedFocusTarget)
  }
}

/**
 * パフォーマンステストヘルパー
 */
export class PerformanceTestHelper {
  private startTime: number = 0
  private endTime: number = 0
  private measurements: Record<string, number> = {}

  /**
   * 測定開始
   */
  startMeasurement(label: string = 'default') {
    this.startTime = performance.now()
    return label
  }

  /**
   * 測定終了
   */
  endMeasurement(label: string = 'default'): number {
    this.endTime = performance.now()
    const duration = this.endTime - this.startTime
    this.measurements[label] = duration
    return duration
  }

  /**
   * レンダリング時間の測定
   */
  async measureRenderTime<T>(renderFn: () => T): Promise<{ result: T; duration: number }> {
    const start = performance.now()
    const result = renderFn()
    const end = performance.now()
    return { result, duration: end - start }
  }

  /**
   * メモリ使用量の測定（Performance APIが利用可能な場合）
   */
  measureMemoryUsage(): number | null {
    if ('memory' in performance) {
      return (performance as any).memory.usedJSHeapSize
    }
    return null
  }

  /**
   * パフォーマンスレポートの生成
   */
  generateReport(): {
    measurements: Record<string, number>
    summary: {
      total: number
      average: number
      max: number
      min: number
    }
  } {
    const values = Object.values(this.measurements)
    const total = values.reduce((sum, val) => sum + val, 0)
    const average = total / values.length
    const max = Math.max(...values)
    const min = Math.min(...values)

    return {
      measurements: { ...this.measurements },
      summary: { total, average, max, min }
    }
  }

  /**
   * パフォーマンス要件のアサーション
   */
  assertPerformanceThresholds(thresholds: {
    maxRenderTime?: number
    maxMemoryIncrease?: number
    maxApiResponseTime?: number
  }) {
    if (thresholds.maxRenderTime && this.measurements.render) {
      expect(this.measurements.render).toBeLessThan(thresholds.maxRenderTime)
    }
    // 他の閾値チェックも同様に実装
  }
}

/**
 * モックヘルパー
 */
export class MockHelper {
  /**
   * API応答のモック
   */
  static mockApiResponse(url: string, response: any, delay: number = 0) {
    global.fetch = vi.fn().mockImplementation(() =>
      new Promise(resolve => {
        setTimeout(() => {
          resolve({
            ok: true,
            json: () => Promise.resolve(response),
            text: () => Promise.resolve(JSON.stringify(response))
          })
        }, delay)
      })
    )
  }

  /**
   * API エラーのモック
   */
  static mockApiError(url: string, error: { status: number; message: string }) {
    global.fetch = vi.fn().mockRejectedValue(
      Object.assign(new Error(error.message), { status: error.status })
    )
  }

  /**
   * ローカルストレージのモック
   */
  static mockLocalStorage() {
    const storage: Record<string, string> = {}
    
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn((key: string) => storage[key] || null),
        setItem: vi.fn((key: string, value: string) => {
          storage[key] = value
        }),
        removeItem: vi.fn((key: string) => {
          delete storage[key]
        }),
        clear: vi.fn(() => {
          Object.keys(storage).forEach(key => delete storage[key])
        })
      },
      writable: true
    })
  }

  /**
   * 位置情報APIのモック
   */
  static mockGeolocation(position: { latitude: number; longitude: number }) {
    const mockGeolocation = {
      getCurrentPosition: vi.fn().mockImplementation((success) => {
        success({
          coords: {
            latitude: position.latitude,
            longitude: position.longitude,
            accuracy: 100
          }
        })
      })
    }

    Object.defineProperty(navigator, 'geolocation', {
      value: mockGeolocation,
      writable: true
    })
  }

  /**
   * メディアデバイスAPIのモック
   */
  static mockMediaDevices(stream?: MediaStream) {
    const mockGetUserMedia = vi.fn().mockResolvedValue(
      stream || {
        getTracks: () => [{ stop: vi.fn() }],
        getVideoTracks: () => [],
        getAudioTracks: () => [{ stop: vi.fn() }]
      }
    )

    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: mockGetUserMedia },
      writable: true
    })
  }
}

/**
 * カスタムマッチャーの拡張
 */
declare global {
  namespace Vi {
    interface JestAssertion<T = any> {
      toBeAccessible(): T
      toHaveLoadingState(): T
      toHaveErrorState(message?: string): T
      toRenderWithinTime(maxTime: number): T
    }
  }
}

// カスタムマッチャーの実装
expect.extend({
  toBeAccessible(received: HTMLElement) {
    const hasAriaLabel = received.hasAttribute('aria-label') || 
                        received.hasAttribute('aria-labelledby')
    const hasRole = received.hasAttribute('role')
    const isAccessible = hasAriaLabel || hasRole || received.tagName === 'BUTTON'

    return {
      message: () => `Expected element to be accessible`,
      pass: isAccessible
    }
  },

  toHaveLoadingState(received: HTMLElement) {
    const hasLoadingAttribute = received.hasAttribute('aria-busy') || 
                               received.hasAttribute('data-loading')
    const hasLoadingText = received.textContent?.includes('loading') || 
                          received.textContent?.includes('読み込み')

    return {
      message: () => `Expected element to have loading state`,
      pass: hasLoadingAttribute || hasLoadingText || false
    }
  },

  toHaveErrorState(received: HTMLElement, expectedMessage?: string) {
    const hasErrorRole = received.getAttribute('role') === 'alert'
    const hasErrorClass = received.className.includes('error')
    const hasErrorMessage = expectedMessage 
      ? received.textContent?.includes(expectedMessage)
      : received.textContent?.includes('error') || received.textContent?.includes('エラー')

    return {
      message: () => `Expected element to have error state${expectedMessage ? ` with message "${expectedMessage}"` : ''}`,
      pass: hasErrorRole || hasErrorClass || hasErrorMessage || false
    }
  },

  async toRenderWithinTime(received: () => any, maxTime: number) {
    const start = performance.now()
    await received()
    const end = performance.now()
    const duration = end - start

    return {
      message: () => `Expected render to complete within ${maxTime}ms, but took ${duration}ms`,
      pass: duration <= maxTime
    }
  }
})

// エクスポート用のファクトリ関数
export function createTestHelpers() {
  return {
    AsyncTestHelper,
    UserInteractionSimulator,
    AccessibilityTestHelper,
    PerformanceTestHelper,
    MockHelper
  }
}

export { renderWithProviders as render }