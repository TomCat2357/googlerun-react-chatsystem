import { describe, it, expect } from 'vitest'
import { 
  validateImageFile, 
  validateAudioFile, 
  validateTextFile,
  getFileExtension 
} from '../validation'

describe('validation', () => {
  describe('validateImageFile', () => {
    it('有効な画像ファイルが正しく検証される', () => {
      const validFile = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
      const maxSize = 5 * 1024 * 1024 // 5MB
      
      const result = validateImageFile(validFile, maxSize)
      
      expect(result.isValid).toBe(true)
      expect(result.error).toBeUndefined()
    })

    it('サイズが大きすぎるファイルが正しくエラーとなる', () => {
      const largeFileContent = new Array(6 * 1024 * 1024).fill('a').join('') // 6MB
      const largeFile = new File([largeFileContent], 'large.jpg', { type: 'image/jpeg' })
      const maxSize = 5 * 1024 * 1024 // 5MB
      
      const result = validateImageFile(largeFile, maxSize)
      
      expect(result.isValid).toBe(false)
      expect(result.error).toContain('ファイルサイズ')
    })

    it('無効なファイルタイプが正しくエラーとなる', () => {
      const invalidFile = new File(['test'], 'test.txt', { type: 'text/plain' })
      const maxSize = 5 * 1024 * 1024
      
      const result = validateImageFile(invalidFile, maxSize)
      
      expect(result.isValid).toBe(false)
      expect(result.error).toContain('サポートされていない')
    })
  })

  describe('validateAudioFile', () => {
    it('有効な音声ファイルが正しく検証される', () => {
      const validFile = new File(['test'], 'test.mp3', { type: 'audio/mpeg' })
      
      const result = validateAudioFile(validFile)
      
      expect(result.isValid).toBe(true)
      expect(result.error).toBeUndefined()
    })

    it('無効なファイルタイプが正しくエラーとなる', () => {
      const invalidFile = new File(['test'], 'test.txt', { type: 'text/plain' })
      
      const result = validateAudioFile(invalidFile)
      
      expect(result.isValid).toBe(false)
      expect(result.error).toContain('サポートされていない')
    })
  })

  describe('validateTextFile', () => {
    it('有効なテキストファイルが正しく検証される', () => {
      const validFile = new File(['test content'], 'test.txt', { type: 'text/plain' })
      
      const result = validateTextFile(validFile)
      
      expect(result.isValid).toBe(true)
      expect(result.error).toBeUndefined()
    })

    it('無効なファイルタイプが正しくエラーとなる', () => {
      const invalidFile = new File(['test'], 'test.exe', { type: 'application/exe' })
      
      const result = validateTextFile(invalidFile)
      
      expect(result.isValid).toBe(false)
      expect(result.error).toContain('サポートされていない')
    })
  })

  describe('getFileExtension', () => {
    it('ファイル名から正しく拡張子を取得する', () => {
      expect(getFileExtension('test.jpg')).toBe('jpg')
      expect(getFileExtension('document.pdf')).toBe('pdf')
      expect(getFileExtension('archive.tar.gz')).toBe('gz')
    })

    it('拡張子がないファイル名で空文字列を返す', () => {
      expect(getFileExtension('filename')).toBe('')
      expect(getFileExtension('')).toBe('')
    })
  })
})