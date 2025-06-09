/**
 * 振る舞い駆動Reactコンポーネントテスト
 * Behavior-Driven React Component Tests
 * 
 * この実装は以下の高度なテスト戦略を実装します：
 * 1. 振る舞い駆動設計（BDD）による UI テスト
 * 2. Given-When-Then パターンの採用
 * 3. ユーザーストーリーに基づくテストシナリオ
 * 4. 複数のテストダブル戦略の組み合わせ
 * 5. アクセシビリティと国際化の考慮
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// テストヘルパーとファクトリ
import { 
  renderWithProviders,
  AsyncTestHelper,
  UserInteractionSimulator,
  AccessibilityTestHelper,
  PerformanceTestHelper,
  MockHelper
} from '@helpers/TestHelpers'
import { 
  testDataFactory,
  TEST_SCENARIOS,
  type TestUser,
  type TestWhisperJob
} from '@factories/TestDataFactory'

// テスト対象コンポーネント
import WhisperPage from '../../Whisper/WhisperPage'
import ChatInput from '../../Chat/ChatInput'

/**
 * ユーザーストーリー：音声ファイルのアップロードと文字起こし
 * 
 * As a ユーザー
 * I want to 音声ファイルをアップロードして文字起こしを依頼できる
 * So that 会議やインタビューの内容を効率的にテキスト化できる
 */
describe('音声ファイルアップロードの振る舞い', () => {
  let user: ReturnType<typeof userEvent.setup>
  let testUser: TestUser
  let performanceHelper: PerformanceTestHelper

  beforeEach(() => {
    user = userEvent.setup()
    testUser = testDataFactory.createTestUser({
      subscription: { tier: 'premium', expiresAt: '', features: ['whisper_advanced'] }
    })
    performanceHelper = new PerformanceTestHelper()
    MockHelper.mockLocalStorage()
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  describe('正常なワークフロー', () => {
    it('プレミアムユーザーが音声ファイルをアップロードできること', async () => {
      // Given: プレミアムユーザーがログインしている
      const scenario = testDataFactory.createTestScenario('basic')
      MockHelper.mockApiResponse('/api/whisper/jobs', scenario.apiResponses['/api/whisper/jobs'])

      // Given: 有効な音声ファイルが用意されている
      const audioFile = new File(['mock audio content'], 'meeting_recording.wav', {
        type: 'audio/wav'
      })

      // When: ユーザーがWhisperページにアクセスする
      const { container } = renderWithProviders(<WhisperPage />, {
        authUser: testUser
      })

      // Then: ページが正常に読み込まれること
      await AsyncTestHelper.waitForText('Whisper 音声文字起こし')
      expect(screen.getByText('音声アップロード')).toBeInTheDocument()

      // When: ユーザーが音声ファイルをアップロードする
      const fileInput = screen.getByLabelText(/音声ファイル/i)
      await user.upload(fileInput, audioFile)

      // Then: ファイルが正常に選択されること
      expect(fileInput).toHaveProperty('files', [audioFile])
      
      // When: ユーザーがアップロードボタンをクリックする
      const uploadButton = screen.getByRole('button', { name: /アップロード|送信/i })
      expect(uploadButton).toBeEnabled()
      
      performanceHelper.startMeasurement('upload_flow')
      await user.click(uploadButton)
      
      // Then: アップロード処理が開始されること
      await AsyncTestHelper.waitForText('アップロード中')
      
      // Then: 処理完了後にジョブ一覧画面に遷移すること
      await AsyncTestHelper.waitForText('処理結果一覧')
      performanceHelper.endMeasurement('upload_flow')

      // パフォーマンス要件の確認
      const uploadTime = performanceHelper.generateReport().measurements.upload_flow
      expect(uploadTime).toBeLessThan(3000) // 3秒以内
    })

    it('複数の音声形式に対応していること', async () => {
      // Given: 異なる形式の音声ファイルが用意されている
      const testFiles = [
        new File(['wav content'], 'test.wav', { type: 'audio/wav' }),
        new File(['mp3 content'], 'test.mp3', { type: 'audio/mpeg' }),
        new File(['m4a content'], 'test.m4a', { type: 'audio/mp4' })
      ]

      renderWithProviders(<WhisperPage />, { authUser: testUser })

      const fileInput = screen.getByLabelText(/音声ファイル/i)

      // When: 各形式のファイルをアップロードする
      for (const file of testFiles) {
        await user.upload(fileInput, file)
        
        // Then: ファイルが受け入れられること
        expect(fileInput).toHaveProperty('files', [file])
        expect(screen.queryByText(/形式が未対応/)).not.toBeInTheDocument()
      }
    })
  })

  describe('エラーハンドリング', () => {
    it('ファイルサイズ制限を超えた場合に適切なエラーメッセージを表示すること', async () => {
      // Given: サイズ制限を超えた音声ファイルが用意されている
      const oversizedFile = new File(
        [new ArrayBuffer(101 * 1024 * 1024)], // 101MB
        'large_meeting.wav',
        { type: 'audio/wav' }
      )

      renderWithProviders(<WhisperPage />, { authUser: testUser })

      // When: 大きなファイルをアップロードしようとする
      const fileInput = screen.getByLabelText(/音声ファイル/i)
      await user.upload(fileInput, oversizedFile)

      const uploadButton = screen.getByRole('button', { name: /アップロード|送信/i })
      await user.click(uploadButton)

      // Then: 適切なエラーメッセージが表示されること
      await AsyncTestHelper.waitForText(/ファイルが大きすぎます/)
      expect(screen.getByText(/最大100MB/)).toBeInTheDocument()
    })

    it('ネットワークエラー時に再試行オプションを提供すること', async () => {
      // Given: ネットワークエラーが発生する環境
      MockHelper.mockApiError('/api/whisper', { status: 500, message: 'Network Error' })

      const audioFile = new File(['audio content'], 'test.wav', { type: 'audio/wav' })

      renderWithProviders(<WhisperPage />, { authUser: testUser })

      // When: ファイルをアップロードしようとする
      const fileInput = screen.getByLabelText(/音声ファイル/i)
      await user.upload(fileInput, audioFile)

      const uploadButton = screen.getByRole('button', { name: /アップロード|送信/i })
      await user.click(uploadButton)

      // Then: エラーメッセージと再試行ボタンが表示されること
      await AsyncTestHelper.waitForText(/エラーが発生しました/)
      expect(screen.getByRole('button', { name: /再試行|もう一度/i })).toBeInTheDocument()
    })
  })

  describe('アクセシビリティ', () => {
    it('キーボードナビゲーションが正常に動作すること', async () => {
      renderWithProviders(<WhisperPage />, { authUser: testUser })

      // アップロードボタンにフォーカス
      const uploadTab = screen.getByRole('button', { name: /音声アップロード/i })
      uploadTab.focus()

      // キーボードナビゲーションの順序をテスト
      const expectedFocusOrder = [
        'upload-tab',
        'jobs-tab',
        'file-input',
        'upload-button'
      ]

      await AccessibilityTestHelper.testKeyboardNavigation(user, uploadTab, expectedFocusOrder)
    })

    it('スクリーンリーダー用の適切なラベルが設定されていること', async () => {
      renderWithProviders(<WhisperPage />, { authUser: testUser })

      const elements = [
        { element: screen.getByLabelText(/音声ファイル/i), expectedLabel: '音声ファイル' },
        { element: screen.getByRole('button', { name: /アップロード/i }), expectedLabel: 'アップロード' }
      ]

      AccessibilityTestHelper.testScreenReaderLabels(elements)
    })
  })

  describe('国際化対応', () => {
    it('英語ロケールで正しく表示されること', async () => {
      // Given: 英語ユーザーの設定
      const englishUser = testDataFactory.createTestUser({
        preferences: { language: 'en', theme: 'light', notifications: true }
      })

      renderWithProviders(<WhisperPage />, { authUser: englishUser })

      // Then: 英語のテキストが表示されること
      expect(screen.getByText(/Whisper Audio Transcription|Audio Upload/i)).toBeInTheDocument()
    })
  })
})

/**
 * ユーザーストーリー：チャット機能での音声メッセージ送信
 * 
 * As a ユーザー
 * I want to チャットで音声メッセージを送信できる
 * So that 文字入力が困難な状況でも迅速にコミュニケーションできる
 */
describe('チャット音声メッセージの振る舞い', () => {
  let user: ReturnType<typeof userEvent.setup>
  let testUser: TestUser
  let interactionSimulator: UserInteractionSimulator

  beforeEach(() => {
    user = userEvent.setup()
    testUser = testDataFactory.createTestUser()
    interactionSimulator = new UserInteractionSimulator(user)
    
    // メディアデバイスAPIのモック
    MockHelper.mockMediaDevices()
  })

  describe('音声録音機能', () => {
    it('マイクボタンを長押しして音声を録音できること', async () => {
      // Given: チャット画面が表示されている
      const scenario = testDataFactory.createTestScenario('basic')
      MockHelper.mockApiResponse('/api/chat/messages', scenario.apiResponses['/api/chat/messages'])

      renderWithProviders(<ChatInput onSendMessage={vi.fn()} />, {
        authUser: testUser
      })

      // When: マイクボタンを長押しする
      const micButton = screen.getByRole('button', { name: /マイク|音声/i })
      expect(micButton).toBeInTheDocument()

      // 長押しのシミュレーション（mousedown -> 待機 -> mouseup）
      await user.pointer({ target: micButton, keys: '[MouseLeft>]' })
      
      // Then: 録音中の状態が表示されること
      await AsyncTestHelper.waitForText(/録音中/)
      expect(screen.getByLabelText(/録音中/)).toBeInTheDocument()

      // When: ボタンを離す
      await user.pointer({ keys: '[/MouseLeft]' })

      // Then: 録音が停止し、送信オプションが表示されること
      await AsyncTestHelper.waitForText(/送信|キャンセル/)
      expect(screen.getByRole('button', { name: /送信/i })).toBeEnabled()
      expect(screen.getByRole('button', { name: /キャンセル/i })).toBeEnabled()
    })

    it('録音権限が拒否された場合に適切なメッセージを表示すること', async () => {
      // Given: マイクアクセスが拒否される環境
      const mockGetUserMedia = vi.fn().mockRejectedValue(
        new DOMException('Permission denied', 'NotAllowedError')
      )
      Object.defineProperty(navigator, 'mediaDevices', {
        value: { getUserMedia: mockGetUserMedia },
        writable: true
      })

      renderWithProviders(<ChatInput onSendMessage={vi.fn()} />, {
        authUser: testUser
      })

      // When: マイクボタンをクリックする
      const micButton = screen.getByRole('button', { name: /マイク|音声/i })
      await user.click(micButton)

      // Then: 権限エラーメッセージが表示されること
      await AsyncTestHelper.waitForText(/マイクの使用許可/)
      expect(screen.getByText(/設定からマイクへのアクセスを許可/)).toBeInTheDocument()
    })
  })

  describe('音声メッセージの送信', () => {
    it('録音した音声メッセージを送信できること', async () => {
      const mockSendMessage = vi.fn()
      
      renderWithProviders(<ChatInput onSendMessage={mockSendMessage} />, {
        authUser: testUser
      })

      const micButton = screen.getByRole('button', { name: /マイク|音声/i })

      // 録音フローの実行
      await user.pointer({ target: micButton, keys: '[MouseLeft>]' })
      await AsyncTestHelper.simulateApiDelay(1000) // 1秒間録音
      await user.pointer({ keys: '[/MouseLeft]' })

      // 送信ボタンクリック
      const sendButton = screen.getByRole('button', { name: /送信/i })
      await user.click(sendButton)

      // Then: onSendMessage が適切な引数で呼ばれること
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'audio',
            content: expect.any(String),
            metadata: expect.objectContaining({
              duration: expect.any(Number),
              mimeType: 'audio/wav'
            })
          })
        )
      })
    })
  })
})

/**
 * ユーザーストーリー：リアルタイム文字起こし結果の表示
 * 
 * As a ユーザー
 * I want to 文字起こし結果をリアルタイムで確認できる
 * So that 処理の進捗状況を把握し、必要に応じて修正できる
 */
describe('リアルタイム文字起こし表示の振る舞い', () => {
  let testUser: TestUser
  let testJob: TestWhisperJob

  beforeEach(() => {
    testUser = testDataFactory.createTestUser()
    testJob = testDataFactory.createTestWhisperJob({
      status: 'processing',
      progress: 45
    })
  })

  describe('ストリーミング更新', () => {
    it('処理進捗がリアルタイムで更新されること', async () => {
      // Given: 処理中のジョブが存在する
      MockHelper.mockApiResponse('/api/whisper/jobs', {
        jobs: [testJob],
        total: 1
      })

      renderWithProviders(<WhisperPage />, { authUser: testUser })

      // ジョブ一覧に移動
      const jobsTab = screen.getByRole('button', { name: /処理結果一覧/i })
      await userEvent.setup().click(jobsTab)

      // Then: 進捗が表示されること
      await AsyncTestHelper.waitForText('45%')
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45')

      // When: 進捗が更新される（WebSocketや定期更新のシミュレーション）
      const updatedJob = { ...testJob, progress: 75 }
      MockHelper.mockApiResponse('/api/whisper/jobs', {
        jobs: [updatedJob],
        total: 1
      })

      // WebSocket更新のシミュレーション
      await AsyncTestHelper.simulateApiDelay(500)

      // Then: 進捗表示が更新されること
      await AsyncTestHelper.waitForText('75%')
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '75')
    })

    it('エラー発生時に適切な状態表示がされること', async () => {
      // Given: エラーが発生したジョブ
      const errorJob = testDataFactory.createTestWhisperJob({
        status: 'failed',
        error_message: '音声ファイルの形式が未対応です'
      })

      MockHelper.mockApiResponse('/api/whisper/jobs', {
        jobs: [errorJob],
        total: 1
      })

      renderWithProviders(<WhisperPage />, { authUser: testUser })

      const jobsTab = screen.getByRole('button', { name: /処理結果一覧/i })
      await userEvent.setup().click(jobsTab)

      // Then: エラー状態が表示されること
      await AsyncTestHelper.waitForText('失敗')
      expect(screen.getByText(/音声ファイルの形式が未対応/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /再試行|リトライ/i })).toBeInTheDocument()
    })
  })
})

/**
 * パフォーマンステスト：大量データの処理
 */
describe('パフォーマンステスト', () => {
  it('大量のジョブデータを効率的に表示できること', async () => {
    // Given: 大量のテストデータ
    const performanceScenario = testDataFactory.createTestScenario('performance')
    const testUser = performanceScenario.users[0]

    const performanceHelper = new PerformanceTestHelper()

    // When: 大量データでページを表示
    performanceHelper.startMeasurement('large_dataset_render')
    
    MockHelper.mockApiResponse('/api/whisper/jobs', {
      jobs: performanceScenario.whisperJobs,
      total: performanceScenario.whisperJobs.length
    })

    const { container } = renderWithProviders(<WhisperPage />, { authUser: testUser })
    
    await AsyncTestHelper.waitForLoadingToComplete()
    performanceHelper.endMeasurement('large_dataset_render')

    // Then: パフォーマンス要件を満たすこと
    const report = performanceHelper.generateReport()
    expect(report.measurements.large_dataset_render).toBeLessThan(2000) // 2秒以内

    // メモリ使用量の確認
    const memoryUsage = performanceHelper.measureMemoryUsage()
    if (memoryUsage) {
      expect(memoryUsage).toBeLessThan(50 * 1024 * 1024) // 50MB以内
    }

    // DOMノード数の確認（仮想化が適切に動作していることを確認）
    const jobItems = container.querySelectorAll('[data-testid*="job-item"]')
    expect(jobItems.length).toBeLessThan(50) // 仮想化により表示項目数が制限されていること
  })
})