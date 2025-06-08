import { describe, it, expect } from 'vitest'
import { generateRequestId } from '../requestIdUtils'

describe('requestIdUtils', () => {
  it('generateRequestIdが正しい形式の文字列を生成する', () => {
    const requestId = generateRequestId()
    
    // F + 12文字の16進数文字列の形式をテスト
    const requestIdPattern = /^F[0-9a-f]{12}$/i
    expect(requestId).toMatch(requestIdPattern)
    expect(requestId).toHaveLength(13) // F + 12文字
  })

  it('連続して呼び出すと異なるIDが生成される', () => {
    const id1 = generateRequestId()
    const id2 = generateRequestId()
    
    expect(id1).not.toBe(id2)
  })
})