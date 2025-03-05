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
          
          // チャット機能を細かく分割
          'feature-chat-core': [
            './src/components/Chat/ChatPage.tsx'
          ],
          'feature-chat-messages': [
            './src/components/Chat/ChatMessages.tsx'
          ],
          'feature-chat-sidebar': [
            './src/components/Chat/ChatSidebar.tsx'
          ],
          
          // ジオコーディング機能
          'feature-geocoding': [
            './src/components/Geocoding/GeocodingPage.tsx',
            './src/components/Geocoding/MapControls.tsx'
          ],
          // 音声文字起こし機能
          'feature-speech': [
            './src/components/SpeechToText/SpeechToTextPage.tsx'
          ],
          // 認証関連
          'feature-auth': [
            './src/components/Auth/LoginButton.tsx',
            './src/components/Auth/LogoutButton.tsx',
            './src/contexts/AuthContext.tsx'
          ],
          
          // ユーティリティ関数を分割
          'utils-file-processing': [
            './src/utils/fileUtils.ts'
          ],
          'utils-chunked-upload': [
            './src/utils/ChunkedUpload.tsx'
          ],
          'utils-db': [
            './src/utils/indexedDBUtils.ts',
            './src/utils/imageCache.ts'
          ],
          
          // 大きなライブラリを別チャンクに
          'vendor-pdf': ['pdfjs-dist'],
          'vendor-doc': ['mammoth', 'xlsx'],
          'vendor-encoding': ['encoding-japanese'],
          'vendor-axios': ['axios']
        }
      }
    },
    // チャンクサイズの警告閾値を引き上げ（一時的な対策）
    chunkSizeWarningLimit: 1000
  }
})