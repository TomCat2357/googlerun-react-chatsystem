import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

/**
 * 高度なテストユーティリティ関数群
 * テストの効率化と品質向上のためのヘルパー関数をテスト
 */

// テスト用のユーティリティ関数
export const createMockFile = (
  name: string, 
  type: string, 
  size: number = 1024,
  content: string = 'mock content'
): File => {
  const file = new File([content], name, { type })
  Object.defineProperty(file, 'size', { value: size, writable: false })
  return file
}

export const createMockAudioFile = (
  name: string = 'test.wav',
  duration: number = 30,
  size: number = 1024 * 1024
): File & { duration?: number } => {
  const file = createMockFile(name, 'audio/wav', size) as File & { duration?: number }
  file.duration = duration
  return file
}

export const createMockImageFile = (
  name: string = 'test.jpg',
  width: number = 800,
  height: number = 600,
  size: number = 500 * 1024
): File & { width?: number; height?: number } => {
  const file = createMockFile(name, 'image/jpeg', size) as File & { width?: number; height?: number }
  file.width = width
  file.height = height
  return file
}

export const waitForAsyncOperations = async (timeout: number = 100): Promise<void> => {
  return new Promise(resolve => setTimeout(resolve, timeout))
}

export const simulateNetworkDelay = (delay: number = 500): Promise<void> => {
  return new Promise(resolve => setTimeout(resolve, delay))
}

export const createMockResponse = (data: any, ok: boolean = true, status: number = 200) => {
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(data),
    text: vi.fn().mockResolvedValue(JSON.stringify(data)),
    blob: vi.fn().mockResolvedValue(new Blob([JSON.stringify(data)])),
    headers: new Map([['content-type', 'application/json']])
  }
}

export const createMockStreamResponse = (chunks: string[]) => {
  let chunkIndex = 0
  
  const mockReader = {
    read: vi.fn().mockImplementation(() => {
      if (chunkIndex < chunks.length) {
        const chunk = chunks[chunkIndex++]
        return Promise.resolve({
          done: false,
          value: new TextEncoder().encode(chunk)
        })
      } else {
        return Promise.resolve({ done: true })
      }
    })
  }

  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => mockReader
    }
  }
}

export const measureRenderTime = async (renderFn: () => void): Promise<number> => {
  const startTime = performance.now()
  await renderFn()
  const endTime = performance.now()
  return endTime - startTime
}

export const measureMemoryUsage = (): NodeJS.MemoryUsage => {
  if (global.gc) {
    global.gc()
  }
  return process.memoryUsage()
}

export const generateLargeDataSet = <T>(
  count: number,
  generator: (index: number) => T
): T[] => {
  return Array.from({ length: count }, (_, index) => generator(index))
}

export const createMockLocalStorage = () => {
  const store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key]
    }),
    clear: vi.fn(() => {
      Object.keys(store).forEach(key => delete store[key])
    }),
    length: Object.keys(store).length,
    key: vi.fn((index: number) => Object.keys(store)[index] || null)
  }
}

export const createMockIndexedDB = () => {
  const databases: Record<string, any> = {}
  
  return {
    open: vi.fn((name: string, version?: number) => {
      const request = {
        onsuccess: null as any,
        onerror: null as any,
        onupgradeneeded: null as any,
        result: {
          transaction: vi.fn((storeNames: string | string[], mode?: string) => ({
            objectStore: vi.fn((storeName: string) => ({
              get: vi.fn((key: any) => ({
                onsuccess: null as any,
                onerror: null as any,
                result: { value: databases[storeName]?.[key] }
              })),
              put: vi.fn((value: any, key?: any) => {
                if (!databases[storeName]) databases[storeName] = {}
                databases[storeName][key || value.id] = value
              }),
              add: vi.fn((value: any, key?: any) => {
                if (!databases[storeName]) databases[storeName] = {}
                databases[storeName][key || value.id] = value
              }),
              delete: vi.fn((key: any) => {
                if (databases[storeName]) {
                  delete databases[storeName][key]
                }
              }),
              clear: vi.fn(() => {
                databases[storeName] = {}
              })
            }))
          }))
        }
      }
      
      // 非同期でsuccess事象を発火
      setTimeout(() => {
        if (request.onsuccess) {
          request.onsuccess({ target: request })
        }
      }, 0)
      
      return request
    }),
    deleteDatabase: vi.fn(),
    databases: vi.fn().mockResolvedValue([])
  }
}

describe('TestUtils', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('createMockFile', () => {
    it('指定されたプロパティでモックファイルを作成する', () => {
      const file = createMockFile('test.txt', 'text/plain', 2048, 'test content')
      
      expect(file.name).toBe('test.txt')
      expect(file.type).toBe('text/plain')
      expect(file.size).toBe(2048)
    })

    it('音声ファイルのモックが正しく作成される', () => {
      const audioFile = createMockAudioFile('audio.mp3', 60, 2 * 1024 * 1024)
      
      expect(audioFile.name).toBe('audio.mp3')
      expect(audioFile.type).toBe('audio/wav')
      expect(audioFile.duration).toBe(60)
      expect(audioFile.size).toBe(2 * 1024 * 1024)
    })

    it('画像ファイルのモックが正しく作成される', () => {
      const imageFile = createMockImageFile('image.png', 1920, 1080, 800 * 1024)
      
      expect(imageFile.name).toBe('image.png')
      expect(imageFile.type).toBe('image/jpeg')
      expect(imageFile.width).toBe(1920)
      expect(imageFile.height).toBe(1080)
      expect(imageFile.size).toBe(800 * 1024)
    })
  })

  describe('createMockResponse', () => {
    it('成功レスポンスのモックを作成する', async () => {
      const data = { message: 'success' }
      const response = createMockResponse(data)
      
      expect(response.ok).toBe(true)
      expect(response.status).toBe(200)
      expect(await response.json()).toEqual(data)
    })

    it('エラーレスポンスのモックを作成する', async () => {
      const errorData = { error: 'Not Found' }
      const response = createMockResponse(errorData, false, 404)
      
      expect(response.ok).toBe(false)
      expect(response.status).toBe(404)
      expect(await response.json()).toEqual(errorData)
    })
  })

  describe('createMockStreamResponse', () => {
    it('ストリーミングレスポンスのモックを作成する', async () => {
      const chunks = ['chunk1', 'chunk2', 'chunk3']
      const response = createMockStreamResponse(chunks)
      
      const reader = response.body.getReader()
      
      // 最初のチャンクを読み取り
      const result1 = await reader.read()
      expect(result1.done).toBe(false)
      expect(new TextDecoder().decode(result1.value)).toBe('chunk1')
      
      // 2番目のチャンクを読み取り
      const result2 = await reader.read()
      expect(result2.done).toBe(false)
      expect(new TextDecoder().decode(result2.value)).toBe('chunk2')
      
      // 3番目のチャンクを読み取り
      const result3 = await reader.read()
      expect(result3.done).toBe(false)
      expect(new TextDecoder().decode(result3.value)).toBe('chunk3')
      
      // ストリーム終了
      const result4 = await reader.read()
      expect(result4.done).toBe(true)
    })
  })

  describe('measureRenderTime', () => {
    it('レンダリング時間を測定する', async () => {
      const mockRenderFn = vi.fn(() => {
        // 10ms の遅延をシミュレート
        const start = Date.now()
        while (Date.now() - start < 10) {
          // 処理時間をシミュレート
        }
      })
      
      const renderTime = await measureRenderTime(mockRenderFn)
      
      expect(renderTime).toBeGreaterThanOrEqual(10)
      expect(mockRenderFn).toHaveBeenCalled()
    })
  })

  describe('generateLargeDataSet', () => {
    it('大量のテストデータを生成する', () => {
      const generator = (index: number) => ({
        id: `item-${index}`,
        name: `Item ${index}`,
        value: index * 10
      })
      
      const dataset = generateLargeDataSet(1000, generator)
      
      expect(dataset).toHaveLength(1000)
      expect(dataset[0]).toEqual({
        id: 'item-0',
        name: 'Item 0',
        value: 0
      })
      expect(dataset[999]).toEqual({
        id: 'item-999',
        name: 'Item 999',
        value: 9990
      })
    })
  })

  describe('createMockLocalStorage', () => {
    it('LocalStorageのモックが正しく動作する', () => {
      const mockStorage = createMockLocalStorage()
      
      // アイテムの設定
      mockStorage.setItem('key1', 'value1')
      expect(mockStorage.setItem).toHaveBeenCalledWith('key1', 'value1')
      
      // アイテムの取得
      mockStorage.getItem('key1')
      expect(mockStorage.getItem).toHaveBeenCalledWith('key1')
      
      // アイテムの削除
      mockStorage.removeItem('key1')
      expect(mockStorage.removeItem).toHaveBeenCalledWith('key1')
      
      // 全クリア
      mockStorage.clear()
      expect(mockStorage.clear).toHaveBeenCalled()
    })
  })

  describe('createMockIndexedDB', () => {
    it('IndexedDBのモックが正しく動作する', async () => {
      const mockIDB = createMockIndexedDB()
      
      const request = mockIDB.open('testDB', 1)
      
      // 成功イベントの設定
      request.onsuccess = vi.fn()
      
      // 非同期処理の完了を待機
      await waitForAsyncOperations()
      
      expect(request.onsuccess).toHaveBeenCalled()
      expect(mockIDB.open).toHaveBeenCalledWith('testDB', 1)
    })
  })

  describe('simulateNetworkDelay', () => {
    it('ネットワーク遅延をシミュレートする', async () => {
      const startTime = Date.now()
      await simulateNetworkDelay(100)
      const endTime = Date.now()
      
      expect(endTime - startTime).toBeGreaterThanOrEqual(100)
    })
  })

  describe('waitForAsyncOperations', () => {
    it('非同期処理の完了を待機する', async () => {
      let completed = false
      
      setTimeout(() => {
        completed = true
      }, 50)
      
      await waitForAsyncOperations(100)
      
      expect(completed).toBe(true)
    })
  })
})