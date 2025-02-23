import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // Reactとルーティング関連
          'vendor-react': [
            'react',
            'react-dom',
            'react-router-dom'
          ],
          // Firebase関連
          'vendor-firebase': [
            'firebase/app',
            'firebase/auth'
          ],

          // チャット機能
          'feature-chat': [
            '/src/components/Chat/ChatPage.tsx'
          ],
          // ジオコーディング機能
          'feature-geocoding': [
            '/src/components/Geocoding/GeocodingPage.tsx',
            '/src/components/Geocoding/MapControls.tsx'
          ],
          // 音声文字起こし機能
          'feature-speech': [
            '/src/components/SpeechToText/SpeechToTextPage.tsx'
          ],
          // 認証関連
          'feature-auth': [
            '/src/components/Auth/LoginButton.tsx',
            '/src/components/Auth/LogoutButton.tsx',
            '/src/contexts/AuthContext.tsx'
          ]
        }
      }
    },
    // チャンクサイズの警告閾値を調整（必要な場合）デフォルト:500(kb)
    // chunkSizeWarningLimit: 500
  }
})