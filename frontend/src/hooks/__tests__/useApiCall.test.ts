import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useApiCall } from '../useApiCall'

// axiosをモック
vi.mock('axios', () => ({
  default: {
    request: vi.fn()
  }
}))

// useTokenをモック
vi.mock('../useToken', () => ({
  useToken: () => ({
    getToken: vi.fn().mockResolvedValue('mock-token')
  })
}))

describe('useApiCall', () => {
  const mockAxios = vi.mocked(await import('axios')).default

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('API呼び出しが成功する場合', async () => {
    const mockResponse = { data: { message: 'success' } }
    mockAxios.request.mockResolvedValueOnce(mockResponse)

    const { result } = renderHook(() => useApiCall())
    
    const response = await result.current.apiCall({
      url: '/test',
      method: 'GET'
    })

    expect(response).toEqual(mockResponse)
    expect(mockAxios.request).toHaveBeenCalledWith(expect.objectContaining({
      url: '/test',
      method: 'GET',
      headers: expect.objectContaining({
        'Authorization': 'Bearer mock-token'
      })
    }))
  })

  it('API呼び出しが失敗する場合', async () => {
    const mockError = new Error('API Error')
    mockAxios.request.mockRejectedValueOnce(mockError)

    const { result } = renderHook(() => useApiCall())
    
    await expect(result.current.apiCall({
      url: '/test',
      method: 'GET'
    })).rejects.toThrow('API Error')
  })
})