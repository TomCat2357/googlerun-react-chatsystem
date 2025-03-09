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
    // チャンクサイズ警告のしきい値を調整
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // コード分割戦略の最適化
        manualChunks: (id) => {
          // React関連ライブラリ
          if (id.includes('node_modules/react') || 
              id.includes('node_modules/react-dom') || 
              id.includes('node_modules/react-router')) {
            return 'vendor-react';
          }
          
          // Firebase関連ライブラリ
          if (id.includes('node_modules/firebase')) {
            return 'vendor-firebase';
          }
          
          // PDF・ファイル処理関連ライブラリ（ChatPageで大部分を占める）
          if (id.includes('node_modules/pdfjs-dist') || 
              id.includes('node_modules/mammoth') || 
              id.includes('node_modules/xlsx')) {
            return 'vendor-file-processing';
          }
          
          // チャットコンポーネント
          if (id.includes('/components/Chat/')) {
            // ファイル関連機能を分割
            if (id.includes('FilePreview') || 
                id.includes('FileViewerModal') || 
                id.includes('fileUtils')) {
              return 'chat-file-components';
            }
            return 'chat-components';
          }
          
          // ユーティリティ関数
          if (id.includes('/utils/')) {
            return 'app-utils';
          }
        }
      }
    },
    // 最適化設定
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: false, // コンソールログを削除
        drop_debugger: false
      }
    }
  },
  // 依存関係の最適化
  optimizeDeps: {
    include: [
      'react', 
      'react-dom', 
      'react-router-dom',
      'firebase/auth',
      'firebase/app',
      'axios'
    ]
  }
})