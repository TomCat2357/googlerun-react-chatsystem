/**
 * フロントエンド用高度テストデータファクトリ
 * Advanced Test Data Factory for Frontend Components
 * 
 * この実装は以下の高度なテストデータ戦略を提供します：
 * 1. Fakeライブラリの代替としてカスタムデータ生成
 * 2. React固有のプロパティ生成（状態、イベント、API応答）
 * 3. ユーザーインタラクションシナリオの生成
 * 4. 国際化対応のテストデータ
 * 5. アクセシビリティテスト用データ
 */

import { WhisperFirestoreData } from '../../types/apiTypes'

export interface TestUser {
  id: string
  email: string
  name: string
  role: 'admin' | 'user' | 'guest'
  preferences: {
    language: 'ja' | 'en' | 'auto'
    theme: 'light' | 'dark'
    notifications: boolean
  }
  subscription: {
    tier: 'free' | 'standard' | 'premium' | 'enterprise'
    expiresAt: string
    features: string[]
  }
}

export interface TestChatMessage {
  id: string
  content: string
  timestamp: string
  sender: 'user' | 'assistant'
  type: 'text' | 'image' | 'audio' | 'file'
  metadata?: {
    fileSize?: number
    mimeType?: string
    duration?: number
  }
}

export interface TestWhisperJob extends WhisperFirestoreData {
  progress?: number
  estimatedCompletion?: string
  segments?: Array<{
    start: number
    end: number
    text: string
    speaker: string
    confidence?: number
  }>
}

export interface TestScenario {
  name: string
  description: string
  users: TestUser[]
  messages: TestChatMessage[]
  whisperJobs: TestWhisperJob[]
  apiResponses: Record<string, any>
  userInteractions: TestUserInteraction[]
}

export interface TestUserInteraction {
  type: 'click' | 'input' | 'drag' | 'scroll' | 'keyboard'
  target: string
  value?: string
  delay?: number
  modifiers?: string[]
}

/**
 * 高度なテストデータ生成クラス
 */
export class FrontendTestDataFactory {
  private seedValue: number = 12345
  private generatedIds: Set<string> = new Set()

  constructor(seed?: number) {
    if (seed !== undefined) {
      this.seedValue = seed
    }
  }

  /**
   * シード値を使った疑似ランダム数生成
   */
  private seededRandom(): number {
    this.seedValue = (this.seedValue * 9301 + 49297) % 233280
    return this.seedValue / 233280
  }

  /**
   * 一意IDの生成
   */
  private generateUniqueId(prefix: string = 'id'): string {
    let id: string
    do {
      const random = Math.floor(this.seededRandom() * 1000000)
      id = `${prefix}_${random}`
    } while (this.generatedIds.has(id))
    
    this.generatedIds.add(id)
    return id
  }

  /**
   * 配列からランダム要素を選択
   */
  private randomElement<T>(array: T[]): T {
    const index = Math.floor(this.seededRandom() * array.length)
    return array[index]
  }

  /**
   * 指定範囲のランダム整数
   */
  private randomInt(min: number, max: number): number {
    return Math.floor(this.seededRandom() * (max - min + 1)) + min
  }

  /**
   * リアルなユーザープロファイル生成
   */
  createTestUser(overrides: Partial<TestUser> = {}): TestUser {
    const userTypes = [
      { role: 'admin' as const, tier: 'enterprise' as const },
      { role: 'user' as const, tier: 'premium' as const },
      { role: 'user' as const, tier: 'standard' as const },
      { role: 'guest' as const, tier: 'free' as const }
    ]

    const names = {
      ja: ['田中太郎', '佐藤花子', '鈴木一郎', '高橋美咲', '渡辺健太'],
      en: ['John Smith', 'Jane Doe', 'Mike Johnson', 'Sarah Wilson', 'Alex Brown']
    }

    const domains = ['example.com', 'test.org', 'demo.jp', 'sample.net']
    
    const userType = this.randomElement(userTypes)
    const isJapanese = this.seededRandom() > 0.5
    const namesList = isJapanese ? names.ja : names.en
    const name = this.randomElement(namesList)
    const emailPrefix = name.toLowerCase().replace(/\s+/g, '.')
    const domain = this.randomElement(domains)

    const baseUser: TestUser = {
      id: this.generateUniqueId('user'),
      email: `${emailPrefix}@${domain}`,
      name,
      role: userType.role,
      preferences: {
        language: isJapanese ? 'ja' : this.randomElement(['en', 'auto']),
        theme: this.randomElement(['light', 'dark']),
        notifications: this.seededRandom() > 0.3
      },
      subscription: {
        tier: userType.tier,
        expiresAt: new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString(),
        features: this.getFeaturesForTier(userType.tier)
      }
    }

    return { ...baseUser, ...overrides }
  }

  /**
   * チャットメッセージ生成
   */
  createTestChatMessage(overrides: Partial<TestChatMessage> = {}): TestChatMessage {
    const messageTemplates = {
      text: [
        'こんにちは、お疲れ様です。',
        'この件について相談があります。',
        'ありがとうございます。',
        'Hello, how are you today?',
        'Could you please help me with this?',
        'Thank you for your assistance.'
      ],
      file: [
        '会議資料.pdf',
        '音声録音.wav',
        'プレゼン資料.pptx',
        'meeting_notes.docx',
        'recording.mp3',
        'presentation.pdf'
      ]
    }

    const messageType = this.randomElement(['text', 'image', 'audio', 'file'] as const)
    const isFromUser = this.seededRandom() > 0.4

    let content: string
    let metadata: any = undefined

    switch (messageType) {
      case 'text':
        content = this.randomElement(messageTemplates.text)
        break
      case 'image':
        content = 'image_upload.jpg'
        metadata = {
          fileSize: this.randomInt(100000, 5000000),
          mimeType: 'image/jpeg'
        }
        break
      case 'audio':
        content = 'audio_message.wav'
        metadata = {
          fileSize: this.randomInt(50000, 10000000),
          mimeType: 'audio/wav',
          duration: this.randomInt(5, 300)
        }
        break
      case 'file':
        content = this.randomElement(messageTemplates.file)
        metadata = {
          fileSize: this.randomInt(10000, 50000000),
          mimeType: this.getMimeTypeForFile(content)
        }
        break
    }

    const baseMessage: TestChatMessage = {
      id: this.generateUniqueId('msg'),
      content,
      timestamp: new Date(Date.now() - this.randomInt(0, 86400000)).toISOString(),
      sender: isFromUser ? 'user' : 'assistant',
      type: messageType,
      metadata
    }

    return { ...baseMessage, ...overrides }
  }

  /**
   * Whisperジョブデータ生成
   */
  createTestWhisperJob(overrides: Partial<TestWhisperJob> = {}): TestWhisperJob {
    const statuses = ['queued', 'processing', 'completed', 'failed'] as const
    const languages = ['ja', 'en', 'auto'] as const
    const status = this.randomElement(statuses)
    
    const filename = `recording_${this.randomInt(1, 999)}.wav`
    const duration = this.randomInt(30000, 3600000) // 30秒 - 1時間
    const fileSize = Math.floor(duration / 1000 * 128000 / 8) // 128kbps相当

    const baseJob: TestWhisperJob = {
      job_id: this.generateUniqueId('job'),
      user_id: this.generateUniqueId('user'),
      user_email: 'test@example.com',
      filename,
      gcs_bucket_name: 'test-whisper-bucket',
      audio_size: fileSize,
      audio_duration_ms: duration,
      file_hash: this.generateHash(),
      status,
      num_speakers: this.randomInt(1, 4),
      min_speakers: 1,
      max_speakers: 4,
      language: this.randomElement(languages),
      initial_prompt: this.seededRandom() > 0.7 ? 'これは会議の録音です。' : '',
      tags: this.generateTags(),
      description: this.seededRandom() > 0.5 ? '重要な会議の録音データ' : '',
      created_at: new Date(Date.now() - this.randomInt(0, 2592000000)).toISOString(),
      updated_at: new Date().toISOString(),
      progress: status === 'processing' ? this.randomInt(10, 90) : undefined,
      estimatedCompletion: status === 'processing' 
        ? new Date(Date.now() + this.randomInt(300000, 3600000)).toISOString()
        : undefined,
      segments: status === 'completed' ? this.generateSegments(duration) : undefined
    }

    return { ...baseJob, ...overrides }
  }

  /**
   * テストシナリオ生成
   */
  createTestScenario(scenarioType: 'basic' | 'complex' | 'error' | 'performance' = 'basic'): TestScenario {
    const scenarios = {
      basic: {
        name: '基本的なユーザーワークフロー',
        description: '一般的な使用パターンのテスト',
        userCount: 2,
        messageCount: 5,
        jobCount: 2
      },
      complex: {
        name: '複雑なマルチユーザーシナリオ',
        description: '多数のユーザーと操作が含まれる複雑なテスト',
        userCount: 5,
        messageCount: 20,
        jobCount: 8
      },
      error: {
        name: 'エラーハンドリングシナリオ',
        description: 'エラー状況の処理をテスト',
        userCount: 1,
        messageCount: 3,
        jobCount: 2
      },
      performance: {
        name: 'パフォーマンステストシナリオ',
        description: '大量データでのパフォーマンステスト',
        userCount: 10,
        messageCount: 100,
        jobCount: 50
      }
    }

    const config = scenarios[scenarioType]
    const users = Array.from({ length: config.userCount }, () => this.createTestUser())
    const messages = Array.from({ length: config.messageCount }, () => this.createTestChatMessage())
    const whisperJobs = Array.from({ length: config.jobCount }, () => this.createTestWhisperJob())

    return {
      name: config.name,
      description: config.description,
      users,
      messages,
      whisperJobs,
      apiResponses: this.createApiResponses(scenarioType),
      userInteractions: this.createUserInteractions(scenarioType)
    }
  }

  /**
   * API応答データ生成
   */
  createApiResponses(scenarioType: string): Record<string, any> {
    const baseResponses = {
      '/api/auth/user': {
        user: this.createTestUser(),
        token: this.generateToken()
      },
      '/api/chat/messages': {
        messages: Array.from({ length: 10 }, () => this.createTestChatMessage()),
        hasMore: this.seededRandom() > 0.5
      },
      '/api/whisper/jobs': {
        jobs: Array.from({ length: 5 }, () => this.createTestWhisperJob()),
        total: this.randomInt(5, 50)
      }
    }

    if (scenarioType === 'error') {
      return {
        ...baseResponses,
        '/api/whisper/upload': {
          error: 'File size too large',
          code: 'FILE_TOO_LARGE'
        },
        '/api/chat/send': {
          error: 'Rate limit exceeded',
          code: 'RATE_LIMIT'
        }
      }
    }

    return baseResponses
  }

  /**
   * ユーザーインタラクション生成
   */
  createUserInteractions(scenarioType: string): TestUserInteraction[] {
    const basicInteractions: TestUserInteraction[] = [
      { type: 'click', target: 'button[data-testid="upload-button"]' },
      { type: 'input', target: 'input[data-testid="message-input"]', value: 'Hello, world!' },
      { type: 'click', target: 'button[data-testid="send-button"]' }
    ]

    const complexInteractions: TestUserInteraction[] = [
      ...basicInteractions,
      { type: 'drag', target: 'div[data-testid="file-drop-zone"]' },
      { type: 'scroll', target: 'div[data-testid="message-list"]' },
      { type: 'keyboard', target: 'input[data-testid="search"]', value: 'test', modifiers: ['ctrl'] }
    ]

    switch (scenarioType) {
      case 'complex':
      case 'performance':
        return complexInteractions
      default:
        return basicInteractions
    }
  }

  /**
   * アクセシビリティテスト用データ生成
   */
  createAccessibilityTestData() {
    return {
      screenReaderLabels: [
        'メインナビゲーション',
        'チャットメッセージ一覧',
        'メッセージ入力フィールド',
        '送信ボタン',
        'ファイルアップロードエリア'
      ],
      keyboardNavigation: [
        { key: 'Tab', expectedFocus: 'button[data-testid="upload-button"]' },
        { key: 'Tab', expectedFocus: 'input[data-testid="message-input"]' },
        { key: 'Tab', expectedFocus: 'button[data-testid="send-button"]' }
      ],
      colorContrastTests: [
        { background: '#ffffff', foreground: '#333333', ratio: 12.6 },
        { background: '#000000', foreground: '#ffffff', ratio: 21.0 }
      ]
    }
  }

  // プライベートヘルパーメソッド
  private getFeaturesForTier(tier: string): string[] {
    const features = {
      free: ['basic_chat', 'file_upload_small'],
      standard: ['basic_chat', 'file_upload_medium', 'whisper_basic'],
      premium: ['basic_chat', 'file_upload_large', 'whisper_advanced', 'priority_support'],
      enterprise: ['all_features', 'custom_integrations', 'dedicated_support']
    }
    return features[tier as keyof typeof features] || features.free
  }

  private getMimeTypeForFile(filename: string): string {
    const extension = filename.split('.').pop()?.toLowerCase()
    const mimeTypes: Record<string, string> = {
      pdf: 'application/pdf',
      doc: 'application/msword',
      docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      ppt: 'application/vnd.ms-powerpoint',
      pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      wav: 'audio/wav',
      mp3: 'audio/mpeg',
      jpg: 'image/jpeg',
      png: 'image/png'
    }
    return mimeTypes[extension || ''] || 'application/octet-stream'
  }

  private generateHash(): string {
    const chars = 'abcdef0123456789'
    let result = ''
    for (let i = 0; i < 16; i++) {
      result += chars.charAt(Math.floor(this.seededRandom() * chars.length))
    }
    return result
  }

  private generateToken(): string {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    let result = ''
    for (let i = 0; i < 64; i++) {
      result += chars.charAt(Math.floor(this.seededRandom() * chars.length))
    }
    return result
  }

  private generateTags(): string[] {
    const allTags = ['会議', 'インタビュー', '講演', 'プレゼン', '音声メモ', '電話会議', 'セミナー']
    const count = this.randomInt(1, 3)
    const tags: string[] = []
    for (let i = 0; i < count; i++) {
      const tag = this.randomElement(allTags)
      if (!tags.includes(tag)) {
        tags.push(tag)
      }
    }
    return tags
  }

  private generateSegments(durationMs: number): Array<{
    start: number
    end: number
    text: string
    speaker: string
    confidence?: number
  }> {
    const segments = []
    const segmentCount = Math.floor(durationMs / 10000) // 10秒ごとのセグメント
    const speakers = ['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_02']
    const texts = [
      'おはようございます。今日はお忙しい中お時間をいただき、ありがとうございます。',
      'はい、こちらこそよろしくお願いします。',
      'それでは早速、本日の議題について説明させていただきます。',
      'Good morning everyone. Thank you for joining today\'s meeting.',
      'Let\'s start with the first agenda item.',
      'Does anyone have any questions about this topic?'
    ]

    let currentTime = 0
    for (let i = 0; i < segmentCount; i++) {
      const segmentDuration = this.randomInt(3000, 15000) // 3-15秒
      const endTime = Math.min(currentTime + segmentDuration, durationMs)
      
      segments.push({
        start: currentTime / 1000,
        end: endTime / 1000,
        text: this.randomElement(texts),
        speaker: this.randomElement(speakers),
        confidence: 0.8 + this.seededRandom() * 0.2
      })

      currentTime = endTime
      if (currentTime >= durationMs) break
    }

    return segments
  }
}

/**
 * グローバルファクトリインスタンス
 */
export const testDataFactory = new FrontendTestDataFactory()

/**
 * テストシナリオの定数
 */
export const TEST_SCENARIOS = {
  BASIC_USER_WORKFLOW: 'basic',
  COMPLEX_MULTI_USER: 'complex',
  ERROR_HANDLING: 'error',
  PERFORMANCE_TESTING: 'performance'
} as const