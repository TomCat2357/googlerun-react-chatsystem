import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import GeocodingPage from '../GeocodingPage'

// Firebase認証のモック
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    currentUser: { uid: 'test-uid' },
    loading: false
  })
}))

// useTokenのモック
vi.mock('../../../hooks/useToken', () => ({
  useToken: () => 'mock-token'
}))

// Configのモック
vi.mock('../../../config', () => ({
  getServerConfig: () => ({
    GOOGLE_MAPS_API_KEY: 'test-api-key',
    MAP_DEFAULT_ZOOM: 10
  }),
  API_BASE_URL: 'http://localhost:3000/api'
}))

// Google Maps APIのモック
const mockMap = {
  setCenter: vi.fn(),
  setZoom: vi.fn(),
  panTo: vi.fn()
}

const mockMarker = {
  setPosition: vi.fn(),
  setMap: vi.fn(),
  setVisible: vi.fn()
}

const mockGeocoder = {
  geocode: vi.fn()
}

global.google = {
  maps: {
    Map: vi.fn(() => mockMap),
    Marker: vi.fn(() => mockMarker),
    Geocoder: vi.fn(() => mockGeocoder),
    LatLng: vi.fn((lat, lng) => ({ lat: () => lat, lng: () => lng })),
    event: {
      addListener: vi.fn()
    },
    GeocoderStatus: {
      OK: 'OK',
      ZERO_RESULTS: 'ZERO_RESULTS'
    },
    MapTypeId: {
      ROADMAP: 'roadmap'
    }
  }
} as any

describe('GeocodingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    
    // 基本的なAPIレスポンスのモック
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        results: [
          {
            formatted_address: '東京都渋谷区渋谷1-1-1',
            geometry: {
              location: {
                lat: 35.6581,
                lng: 139.7414
              }
            },
            place_id: 'ChIJ5SZejrOLGGARCxhysTk3sLg'
          }
        ],
        status: 'OK'
      })
    })
  })

  it('ページが正しくレンダリングされる', () => {
    render(<GeocodingPage />)
    
    expect(screen.getByText(/住所検索・地図表示/)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/住所を入力してください/)).toBeInTheDocument()
    expect(screen.getByText('検索')).toBeInTheDocument()
  })

  it('住所検索が正しく動作する', async () => {
    mockGeocoder.geocode.mockImplementation((request, callback) => {
      callback([
        {
          formatted_address: '東京都渋谷区渋谷1-1-1',
          geometry: {
            location: {
              lat: () => 35.6581,
              lng: () => 139.7414
            }
          }
        }
      ], global.google.maps.GeocoderStatus.OK)
    })

    render(<GeocodingPage />)
    
    const addressInput = screen.getByPlaceholderText(/住所を入力してください/)
    const searchButton = screen.getByText('検索')
    
    fireEvent.change(addressInput, { 
      target: { value: '東京都渋谷区' } 
    })
    fireEvent.click(searchButton)

    await waitFor(() => {
      expect(screen.getByText('東京都渋谷区渋谷1-1-1')).toBeInTheDocument()
    })
  })

  it('検索結果が地図に表示される', async () => {
    mockGeocoder.geocode.mockImplementation((request, callback) => {
      callback([
        {
          formatted_address: '東京都渋谷区渋谷1-1-1',
          geometry: {
            location: {
              lat: () => 35.6581,
              lng: () => 139.7414
            }
          }
        }
      ], global.google.maps.GeocoderStatus.OK)
    })

    render(<GeocodingPage />)
    
    const addressInput = screen.getByPlaceholderText(/住所を入力してください/)
    const searchButton = screen.getByText('検索')
    
    fireEvent.change(addressInput, { 
      target: { value: '東京都渋谷区' } 
    })
    fireEvent.click(searchButton)

    await waitFor(() => {
      expect(mockMap.setCenter).toHaveBeenCalled()
      expect(mockMarker.setPosition).toHaveBeenCalled()
    })
  })

  it('無効な住所でエラーが表示される', async () => {
    mockGeocoder.geocode.mockImplementation((request, callback) => {
      callback([], global.google.maps.GeocoderStatus.ZERO_RESULTS)
    })

    render(<GeocodingPage />)
    
    const addressInput = screen.getByPlaceholderText(/住所を入力してください/)
    const searchButton = screen.getByText('検索')
    
    fireEvent.change(addressInput, { 
      target: { value: '存在しない住所' } 
    })
    fireEvent.click(searchButton)

    await waitFor(() => {
      expect(screen.getByText(/住所が見つかりませんでした/)).toBeInTheDocument()
    })
  })

  it('現在位置取得機能が動作する', async () => {
    // Geolocation APIのモック
    const mockGeolocation = {
      getCurrentPosition: vi.fn((success) => {
        success({
          coords: {
            latitude: 35.6762,
            longitude: 139.6503,
            accuracy: 50
          }
        })
      })
    }
    
    Object.defineProperty(navigator, 'geolocation', {
      value: mockGeolocation,
      configurable: true
    })

    render(<GeocodingPage />)
    
    const currentLocationButton = screen.getByText(/現在位置/)
    fireEvent.click(currentLocationButton)

    await waitFor(() => {
      expect(mockGeolocation.getCurrentPosition).toHaveBeenCalled()
      expect(mockMap.setCenter).toHaveBeenCalled()
    })
  })

  it('位置情報アクセス拒否時のエラーハンドリング', async () => {
    const mockGeolocation = {
      getCurrentPosition: vi.fn((success, error) => {
        error({
          code: 1,
          message: 'User denied the request for Geolocation.'
        })
      })
    }
    
    Object.defineProperty(navigator, 'geolocation', {
      value: mockGeolocation,
      configurable: true
    })

    render(<GeocodingPage />)
    
    const currentLocationButton = screen.getByText(/現在位置/)
    fireEvent.click(currentLocationButton)

    await waitFor(() => {
      expect(screen.getByText(/位置情報の取得が拒否されました/)).toBeInTheDocument()
    })
  })

  it('地図の種類切り替えが動作する', () => {
    render(<GeocodingPage />)
    
    const mapTypeSelect = screen.getByLabelText(/地図の種類/)
    
    fireEvent.change(mapTypeSelect, { target: { value: 'satellite' } })
    expect(mapTypeSelect).toHaveValue('satellite')
    
    fireEvent.change(mapTypeSelect, { target: { value: 'terrain' } })
    expect(mapTypeSelect).toHaveValue('terrain')
  })

  it('ズームレベル調整が動作する', () => {
    render(<GeocodingPage />)
    
    const zoomInButton = screen.getByText(/ズームイン/)
    const zoomOutButton = screen.getByText(/ズームアウト/)
    
    fireEvent.click(zoomInButton)
    expect(mockMap.setZoom).toHaveBeenCalled()
    
    fireEvent.click(zoomOutButton)
    expect(mockMap.setZoom).toHaveBeenCalled()
  })

  it('検索履歴機能が動作する', async () => {
    // LocalStorageのモック
    const mockLocalStorage = {
      getItem: vi.fn(() => JSON.stringify(['東京都渋谷区', '大阪府大阪市'])),
      setItem: vi.fn(),
      removeItem: vi.fn()
    }
    
    Object.defineProperty(window, 'localStorage', {
      value: mockLocalStorage,
      configurable: true
    })

    render(<GeocodingPage />)
    
    // 履歴ボタンをクリック
    const historyButton = screen.getByText(/履歴/)
    fireEvent.click(historyButton)

    await waitFor(() => {
      expect(screen.getByText('東京都渋谷区')).toBeInTheDocument()
      expect(screen.getByText('大阪府大阪市')).toBeInTheDocument()
    })
  })

  it('お気に入り登録機能が動作する', async () => {
    render(<GeocodingPage />)
    
    const addressInput = screen.getByPlaceholderText(/住所を入力してください/)
    const searchButton = screen.getByText('検索')
    
    fireEvent.change(addressInput, { 
      target: { value: '東京都渋谷区' } 
    })
    fireEvent.click(searchButton)

    await waitFor(() => {
      const favoriteButton = screen.getByText(/お気に入りに追加/)
      expect(favoriteButton).toBeInTheDocument()
      
      fireEvent.click(favoriteButton)
      expect(screen.getByText(/お気に入りに追加されました/)).toBeInTheDocument()
    })
  })

  it('ルート検索機能が動作する', async () => {
    render(<GeocodingPage />)
    
    const startInput = screen.getByPlaceholderText(/出発地/)
    const endInput = screen.getByPlaceholderText(/目的地/)
    const routeButton = screen.getByText('ルート検索')
    
    fireEvent.change(startInput, { target: { value: '東京駅' } })
    fireEvent.change(endInput, { target: { value: '渋谷駅' } })
    fireEvent.click(routeButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/geocoding/route'),
        expect.objectContaining({
          method: 'POST'
        })
      )
    })
  })

  it('逆ジオコーディング機能が動作する', async () => {
    render(<GeocodingPage />)
    
    // 地図上のクリックをシミュレート
    const mapContainer = screen.getByTestId('map-container')
    
    fireEvent.click(mapContainer, {
      clientX: 100,
      clientY: 100
    })

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/geocoding/reverse'),
        expect.objectContaining({
          method: 'POST'
        })
      )
    })
  })

  it('周辺施設検索機能が動作する', async () => {
    render(<GeocodingPage />)
    
    const addressInput = screen.getByPlaceholderText(/住所を入力してください/)
    const searchButton = screen.getByText('検索')
    
    fireEvent.change(addressInput, { 
      target: { value: '東京都渋谷区' } 
    })
    fireEvent.click(searchButton)

    await waitFor(() => {
      const nearbyButton = screen.getByText(/周辺施設/)
      fireEvent.click(nearbyButton)
      
      const facilitySelect = screen.getByLabelText(/施設タイプ/)
      fireEvent.change(facilitySelect, { target: { value: 'restaurant' } })
      
      const searchNearbyButton = screen.getByText('周辺検索')
      fireEvent.click(searchNearbyButton)
    })

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/geocoding/nearby'),
      expect.objectContaining({
        method: 'POST'
      })
    )
  })

  it('地図のスタイルカスタマイズが動作する', () => {
    render(<GeocodingPage />)
    
    const styleButton = screen.getByText(/スタイル設定/)
    fireEvent.click(styleButton)
    
    const darkModeToggle = screen.getByLabelText(/ダークモード/)
    fireEvent.click(darkModeToggle)
    
    expect(darkModeToggle).toBeChecked()
  })

  it('距離・時間測定機能が動作する', async () => {
    render(<GeocodingPage />)
    
    const measureButton = screen.getByText(/距離測定/)
    fireEvent.click(measureButton)
    
    // 測定モードでの地図クリックをシミュレート
    const mapContainer = screen.getByTestId('map-container')
    
    // 開始点
    fireEvent.click(mapContainer, { clientX: 100, clientY: 100 })
    
    // 終了点
    fireEvent.click(mapContainer, { clientX: 200, clientY: 200 })

    await waitFor(() => {
      expect(screen.getByText(/距離:/)).toBeInTheDocument()
    })
  })

  it('エクスポート機能が動作する', async () => {
    render(<GeocodingPage />)
    
    const addressInput = screen.getByPlaceholderText(/住所を入力してください/)
    const searchButton = screen.getByText('検索')
    
    fireEvent.change(addressInput, { 
      target: { value: '東京都渋谷区' } 
    })
    fireEvent.click(searchButton)

    await waitFor(() => {
      const exportButton = screen.getByText(/エクスポート/)
      fireEvent.click(exportButton)
      
      const exportFormatSelect = screen.getByLabelText(/形式/)
      fireEvent.change(exportFormatSelect, { target: { value: 'csv' } })
      
      const downloadButton = screen.getByText('ダウンロード')
      fireEvent.click(downloadButton)
    })

    // エクスポート処理の実行確認
    expect(screen.getByText(/エクスポートしています/)).toBeInTheDocument()
  })
})