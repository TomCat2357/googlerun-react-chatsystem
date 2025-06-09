import '@testing-library/jest-dom'
import { vi } from 'vitest'

// グローバルなモック設定

// console.errorをモック化してテスト中のエラーログを抑制
const originalConsoleError = console.error
beforeEach(() => {
  console.error = vi.fn()
})

afterEach(() => {
  console.error = originalConsoleError
  vi.clearAllMocks()
})

// LocalStorage/SessionStorageのモック
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  },
  writable: true,
})

Object.defineProperty(window, 'sessionStorage', {
  value: {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  },
  writable: true,
})

// IndexedDBのモック
global.indexedDB = {
  open: vi.fn().mockImplementation(() => ({
    onsuccess: null,
    onerror: null,
    result: {
      transaction: vi.fn().mockReturnValue({
        objectStore: vi.fn().mockReturnValue({
          get: vi.fn().mockReturnValue({
            onsuccess: null,
            onerror: null,
            result: { value: {} }
          }),
          put: vi.fn(),
          add: vi.fn(),
          delete: vi.fn()
        })
      })
    }
  })),
  deleteDatabase: vi.fn(),
  databases: vi.fn()
}

// matchMediaのモック（レスポンシブテスト用）
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// URL.createObjectURLのモック（ファイルアップロードテスト用）
Object.defineProperty(URL, 'createObjectURL', {
  writable: true,
  value: vi.fn(() => 'mocked-object-url'),
})

Object.defineProperty(URL, 'revokeObjectURL', {
  writable: true,
  value: vi.fn(),
})

// ResizeObserverのモック
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

// IntersectionObserverのモック
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

// Clipboard APIのモック
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
    readText: vi.fn().mockResolvedValue(''),
  },
})

// HTMLCanvasElementのモック
global.HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
  fillRect: vi.fn(),
  clearRect: vi.fn(),
  getImageData: vi.fn().mockReturnValue({
    data: new Uint8ClampedArray(4)
  }),
  putImageData: vi.fn(),
  createImageData: vi.fn().mockReturnValue({}),
  setTransform: vi.fn(),
  drawImage: vi.fn(),
  save: vi.fn(),
  fillText: vi.fn(),
  restore: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  closePath: vi.fn(),
  stroke: vi.fn(),
  translate: vi.fn(),
  scale: vi.fn(),
  rotate: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  measureText: vi.fn().mockReturnValue({ width: 0 }),
  transform: vi.fn(),
  rect: vi.fn(),
  clip: vi.fn()
})

// HTMLMediaElementのモック（音声・動画要素用）
Object.defineProperty(HTMLMediaElement.prototype, 'play', {
  writable: true,
  value: vi.fn().mockResolvedValue(undefined),
})

Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
  writable: true,
  value: vi.fn(),
})

Object.defineProperty(HTMLMediaElement.prototype, 'load', {
  writable: true,
  value: vi.fn(),
})

// FileReaderのモック
global.FileReader = vi.fn().mockImplementation(() => ({
  readAsDataURL: vi.fn().mockImplementation(function() {
    setTimeout(() => {
      this.onload({ target: { result: 'data:image/jpeg;base64,mock-base64-data' } })
    }, 0)
  }),
  readAsText: vi.fn().mockImplementation(function() {
    setTimeout(() => {
      this.onload({ target: { result: 'mock text content' } })
    }, 0)
  }),
  readAsArrayBuffer: vi.fn(),
  onload: vi.fn(),
  onerror: vi.fn(),
  result: null
}))

// TextDecoderのモック
global.TextDecoder = vi.fn().mockImplementation(() => ({
  decode: vi.fn().mockReturnValue('decoded text')
}))

// TextEncoderのモック
global.TextEncoder = vi.fn().mockImplementation(() => ({
  encode: vi.fn().mockReturnValue(new Uint8Array([116, 101, 115, 116]))
}))

// イベント関連のモック
window.addEventListener = vi.fn()
window.removeEventListener = vi.fn()

// fetch APIのデフォルトモック
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  status: 200,
  json: vi.fn().mockResolvedValue({}),
  text: vi.fn().mockResolvedValue(''),
  blob: vi.fn().mockResolvedValue(new Blob()),
  headers: new Map()
})