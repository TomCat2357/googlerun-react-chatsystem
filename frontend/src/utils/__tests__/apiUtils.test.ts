import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { 
  buildApiUrl,
  handleApiError,
  createFormData,
  createApiHeaders,
  getStatusMessage
} from '../apiUtils'

// Mock the Response constructor for handleApiError tests
global.Response = vi.fn().mockImplementation((body, init) => ({
  ok: init?.status ? init.status >= 200 && init.status < 300 : true,
  status: init?.status || 200,
  json: vi.fn().mockResolvedValue(JSON.parse(body || '{}')),
  text: vi.fn().mockResolvedValue(body || ''),
  headers: new Map(Object.entries(init?.headers || {}))
}))

describe('apiUtils', () => {
  describe('buildApiUrl', () => {
    it('ベースURLとパスが正しく結合される', () => {
      const baseUrl = 'https://api.example.com'
      const path = '/users/123'
      
      const result = buildApiUrl(baseUrl, path)
      
      expect(result).toBe('https://api.example.com/users/123')
    })

    it('パスの最初にスラッシュがない場合でも正しく処理される', () => {
      const baseUrl = 'https://api.example.com'
      const path = 'users/123'
      
      const result = buildApiUrl(baseUrl, path)
      
      expect(result).toBe('https://api.example.com/users/123')
    })

    it('ベースURLの最後にスラッシュがある場合でも正しく処理される', () => {
      const baseUrl = 'https://api.example.com/'
      const path = '/users/123'
      
      const result = buildApiUrl(baseUrl, path)
      
      expect(result).toBe('https://api.example.com/users/123')
    })
  })

  describe('handleApiError', () => {
    it('レスポンスエラーが正しく処理される', async () => {
      const mockResponse = {
        ok: false,
        status: 400,
        json: vi.fn().mockResolvedValue({ message: 'Bad Request', code: 'VALIDATION_ERROR' })
      }
      
      await expect(handleApiError(mockResponse as any)).rejects.toMatchObject({
        status: 400,
        message: 'Bad Request',
        code: 'VALIDATION_ERROR'
      })
    })

    it('JSONパースエラー時のフォールバック処理', async () => {
      const mockResponse = {
        ok: false,
        status: 500,
        json: vi.fn().mockRejectedValue(new Error('JSON parse error'))
      }
      
      await expect(handleApiError(mockResponse as any)).rejects.toMatchObject({
        status: 500,
        message: 'HTTP error! status: 500'
      })
    })
  })

  describe('createFormData', () => {
    it('オブジェクトからFormDataが正しく作成される', () => {
      const data = {
        name: 'John',
        age: 30,
        file: new File(['test'], 'test.txt')
      }
      
      const formData = createFormData(data)
      
      expect(formData).toBeInstanceOf(FormData)
      expect(formData.get('name')).toBe('John')
      expect(formData.get('age')).toBe('30')
      expect(formData.get('file')).toBeInstanceOf(File)
    })

    it('空のオブジェクトでもFormDataが作成される', () => {
      const data = {}
      
      const formData = createFormData(data)
      
      expect(formData).toBeInstanceOf(FormData)
    })

    it('配列が正しく処理される', () => {
      const data = {
        tags: ['tag1', 'tag2', 'tag3']
      }
      
      const formData = createFormData(data)
      
      expect(formData.get('tags[0]')).toBe('tag1')
      expect(formData.get('tags[1]')).toBe('tag2')
      expect(formData.get('tags[2]')).toBe('tag3')
    })
  })

  describe('createApiHeaders', () => {
    it('標準ヘッダーが正しく作成される', () => {
      const token = 'test-token'
      const headers = createApiHeaders(token)
      
      expect(headers['Content-Type']).toBe('application/json')
      expect(headers['Authorization']).toBe('Bearer test-token')
      expect(headers['X-Request-Id']).toMatch(/^F[0-9a-f]{12}$/i)
    })

    it('カスタムヘッダーが追加される', () => {
      const token = 'test-token'
      const customHeaders = { 'Custom-Header': 'custom-value' }
      const headers = createApiHeaders(token, 'custom-id', customHeaders)
      
      expect(headers['X-Request-Id']).toBe('custom-id')
      expect(headers['Custom-Header']).toBe('custom-value')
    })
  })

  describe('getStatusMessage', () => {
    it('既知のステータスコードの説明を返す', () => {
      expect(getStatusMessage(200)).toBe('OK')
      expect(getStatusMessage(400)).toBe('不正なリクエスト')
      expect(getStatusMessage(500)).toBe('サーバーエラーが発生しました')
    })

    it('未知のステータスコードの場合はデフォルトメッセージを返す', () => {
      expect(getStatusMessage(999)).toBe('HTTPエラー: 999')
    })
  })
})