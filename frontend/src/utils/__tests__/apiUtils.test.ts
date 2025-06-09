import { describe, it, expect, vi } from 'vitest'
import { 
  buildApiUrl,
  handleApiError,
  createFormData
} from '../apiUtils'

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
    it('Axiosエラーが正しく処理される', () => {
      const axiosError = {
        isAxiosError: true,
        response: {
          status: 400,
          data: { message: 'Bad Request' }
        }
      }
      
      const result = handleApiError(axiosError)
      
      expect(result).toContain('400')
      expect(result).toContain('Bad Request')
    })

    it('ネットワークエラーが正しく処理される', () => {
      const networkError = {
        isAxiosError: true,
        request: {},
        message: 'Network Error'
      }
      
      const result = handleApiError(networkError)
      
      expect(result).toContain('ネットワークエラー')
    })

    it('一般的なエラーが正しく処理される', () => {
      const generalError = new Error('Something went wrong')
      
      const result = handleApiError(generalError)
      
      expect(result).toContain('Something went wrong')
    })
  })

  describe('createFormData', () => {
    it('オブジェクトからFormDataが正しく作成される', () => {
      const data = {
        name: 'John',
        age: '30',
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
  })
})