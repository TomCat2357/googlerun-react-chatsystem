import { describe, it, expect } from 'vitest'
import { 
  validateImageFile,
  validateAudioFile,
  validateTextFile,
  getFileExtension,
  validateFileSize,
  validateFileType,
  validateEmail,
  validatePassword,
  validateRequired
} from '../validation'

// File モックを作成
const createMockFile = (name: string, type: string, size: number = 1024): File => {
  const file = new File(['test content'], name, { type })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

describe('validation', () => {
  describe('validateImageFile', () => {
    it('有効な画像ファイルが正しく検証される', () => {
      const file = createMockFile('test.jpg', 'image/jpeg', 1024)
      const result = validateImageFile(file)
      
      expect(result).toBeNull()
    })

    it('サイズが大きすぎるファイルが正しくエラーとなる', () => {
      const file = createMockFile('test.jpg', 'image/jpeg', 10 * 1024 * 1024) // 10MB
      const result = validateImageFile(file, 5 * 1024 * 1024) // 5MB制限
      
      expect(result).toContain('ファイルサイズが上限')
    })

    it('無効なファイルタイプが正しくエラーとなる', () => {
      const file = createMockFile('test.txt', 'text/plain', 1024)
      const result = validateImageFile(file)
      
      expect(result).toContain('許可されていないファイルタイプ')
    })
  })

  describe('validateAudioFile', () => {
    it('有効な音声ファイルが正しく検証される', () => {
      const file = createMockFile('test.mp3', 'audio/mp3', 1024)
      const result = validateAudioFile(file)
      
      expect(result).toBeNull()
    })

    it('無効なファイルタイプが正しくエラーとなる', () => {
      const file = createMockFile('test.txt', 'text/plain', 1024)
      const result = validateAudioFile(file)
      
      expect(result).toContain('許可されていないファイルタイプ')
    })
  })

  describe('validateTextFile', () => {
    it('有効なテキストファイルが正しく検証される', () => {
      const file = createMockFile('test.txt', 'text/plain', 1024)
      const result = validateTextFile(file)
      
      expect(result).toBeNull()
    })

    it('無効なファイルタイプが正しくエラーとなる', () => {
      const file = createMockFile('test.jpg', 'image/jpeg', 1024)
      const result = validateTextFile(file)
      
      expect(result).toContain('許可されていないファイルタイプ')
    })
  })

  describe('getFileExtension', () => {
    it('ファイル名から正しく拡張子を取得する', () => {
      expect(getFileExtension('test.txt')).toBe('txt')
      expect(getFileExtension('image.jpg')).toBe('jpg')
      expect(getFileExtension('archive.tar.gz')).toBe('gz')
    })

    it('拡張子がないファイル名で空文字列を返す', () => {
      expect(getFileExtension('filename')).toBe('')
      expect(getFileExtension('folder.')).toBe('')
      expect(getFileExtension('')).toBe('')
    })
  })

  describe('validateFileSize', () => {
    it('制限内のファイルサイズで成功する', () => {
      const file = createMockFile('test.txt', 'text/plain', 1024)
      const result = validateFileSize(file, 2048)
      
      expect(result).toBeNull()
    })

    it('制限を超えるファイルサイズでエラーとなる', () => {
      const file = createMockFile('test.txt', 'text/plain', 3072)
      const result = validateFileSize(file, 2048)
      
      expect(result).toContain('ファイルサイズが上限')
    })
  })

  describe('validateFileType', () => {
    it('許可されたタイプで成功する', () => {
      const file = createMockFile('test.jpg', 'image/jpeg', 1024)
      const result = validateFileType(file, ['image/jpeg', 'image/png'])
      
      expect(result).toBeNull()
    })

    it('許可されていないタイプでエラーとなる', () => {
      const file = createMockFile('test.txt', 'text/plain', 1024)
      const result = validateFileType(file, ['image/jpeg', 'image/png'])
      
      expect(result).toContain('許可されていないファイルタイプ')
    })

    it('ワイルドカードタイプで成功する', () => {
      const file = createMockFile('test.jpg', 'image/jpeg', 1024)
      const result = validateFileType(file, ['image/*'])
      
      expect(result).toBeNull()
    })

    it('拡張子ベースの検証で成功する', () => {
      const file = createMockFile('test.txt', 'text/plain', 1024)
      const result = validateFileType(file, ['.txt', '.csv'])
      
      expect(result).toBeNull()
    })
  })

  describe('validateEmail', () => {
    it('有効なメールアドレスで成功する', () => {
      expect(validateEmail('test@example.com')).toBeNull()
      expect(validateEmail('user.name@domain.co.jp')).toBeNull()
    })

    it('無効なメールアドレスでエラーとなる', () => {
      expect(validateEmail('')).toContain('必須')
      expect(validateEmail('invalid-email')).toContain('有効なメールアドレス')
      expect(validateEmail('@domain.com')).toContain('有効なメールアドレス')
    })
  })

  describe('validatePassword', () => {
    it('有効なパスワードで成功する', () => {
      expect(validatePassword('StrongPass123!')).toBeNull()
      expect(validatePassword('MySecure2024@')).toBeNull()
    })

    it('短すぎるパスワードでエラーとなる', () => {
      expect(validatePassword('1234567')).toContain('8文字以上')
    })

    it('弱いパスワードでエラーとなる', () => {
      expect(validatePassword('password')).toContain('3種類以上')
      expect(validatePassword('12345678')).toContain('3種類以上')
    })
  })

  describe('validateRequired', () => {
    it('値が存在する場合は成功する', () => {
      expect(validateRequired('test', 'フィールド')).toBeNull()
      expect(validateRequired(123, 'フィールド')).toBeNull()
      expect(validateRequired(['item'], 'フィールド')).toBeNull()
    })

    it('値が空の場合はエラーとなる', () => {
      expect(validateRequired('', 'フィールド')).toContain('必須')
      expect(validateRequired(null, 'フィールド')).toContain('必須')
      expect(validateRequired(undefined, 'フィールド')).toContain('必須')
      expect(validateRequired([], 'フィールド')).toContain('必須')
    })
  })
})