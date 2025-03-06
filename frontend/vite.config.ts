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
        manualChunks: (id) => {
          // ライブラリごとに異なるチャンクに分ける
          if (id.includes('node_modules/pdfjs-dist')) {
            return 'vendor-pdf';
          }
          if (id.includes('node_modules/mammoth')) {
            return 'vendor-mammoth';
          }
          if (id.includes('node_modules/xlsx')) {
            return 'vendor-xlsx';
          }
          
          // React関連
          if (id.includes('node_modules/react') || 
              id.includes('node_modules/react-dom') ||
              id.includes('node_modules/react-router-dom')) {
            return 'vendor-react';
          }
          
          // Firebase関連
          if (id.includes('node_modules/firebase')) {
            return 'vendor-firebase';
          }
          
          // チャット関連のコンポーネント
          if (id.includes('src/components/Chat/ChatPage.tsx')) {
            return 'feature-chat-core';
          }
          if (id.includes('src/components/Chat/ChatMessages.tsx')) {
            return 'feature-chat-messages';
          }
          if (id.includes('src/components/Chat/ChatSidebar.tsx')) {
            return 'feature-chat-sidebar';
          }
          if (id.includes('src/components/Chat/ChatInput.tsx')) {
            return 'feature-chat-input';
          }
          if (id.includes('src/components/Chat/FilePreview.tsx') || 
              id.includes('src/components/Chat/FileViewerModal.tsx')) {
            return 'feature-chat-file-preview';
          }
          
          // ファイル処理関連のロジックを分離
          if (id.includes('src/utils/fileUtils.ts')) {
            // fileUtilsの実装内容から判断して適切なチャンクに割り当てる
            if (id.includes('processImageFile')) {
              return 'utils-file-image';
            }
            if (id.includes('processAudioFile')) {
              return 'utils-file-audio';
            }
            if (id.includes('processPdf')) {
              return 'utils-file-pdf';
            }
            if (id.includes('processDocx')) {
              return 'utils-file-docx';
            }
            if (id.includes('processCsv') || id.includes('processText')) {
              return 'utils-file-text';
            }
            return 'utils-file-common'; // その他のコード
          }
          
          // ジオコーディング関連
          if (id.includes('src/components/Geocoding/GeocodingPage.tsx')) {
            return 'feature-geocoding-page';
          }
          if (id.includes('src/components/Geocoding/MapControls.tsx')) {
            return 'feature-geocoding-map';
          }
          
          // 音声関連
          if (id.includes('src/components/SpeechToText/SpeechToTextPage.tsx')) {
            return 'feature-speech-page';
          }
          if (id.includes('src/components/SpeechToText') && 
              !id.includes('SpeechToTextPage.tsx')) {
            return 'feature-speech-components';
          }
          
          // 認証関連
          if (id.includes('src/components/Auth') || 
              id.includes('src/contexts/AuthContext.tsx')) {
            return 'feature-auth';
          }
          
          // その他のユーティリティ
          if (id.includes('src/utils/ChunkedUpload.tsx')) {
            return 'utils-chunked-upload';
          }
          if (id.includes('src/utils/indexedDBUtils.ts') || 
              id.includes('src/utils/imageCache.ts')) {
            return 'utils-db';
          }
        }
      }
    },
    // チャンクサイズの警告閾値を引き上げ
    chunkSizeWarningLimit: 1000
  }
})