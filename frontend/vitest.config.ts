import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    coverage: {
      reporter: ['text', 'html', 'json', 'lcov'],
      exclude: [
        'node_modules/',
        'dist/',
        'src/test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/index.ts',
        '**/index.tsx',
        'src/firebase/',
        'src/vite-env.d.ts'
      ],
      include: [
        'src/**/*.{ts,tsx}',
        '!src/**/*.{test,spec}.{ts,tsx}',
        '!src/test/**/*'
      ],
      thresholds: {
        global: {
          branches: 70,
          functions: 70,
          lines: 70,
          statements: 70
        }
      }
    },
    // テストファイルのパターン
    include: [
      'src/**/*.{test,spec}.{js,ts,jsx,tsx}'
    ],
    // タイムアウト設定
    testTimeout: 10000,
    // モックのリセット
    clearMocks: true,
    restoreMocks: true,
    // 並列実行設定
    pool: 'threads',
    poolOptions: {
      threads: {
        singleThread: false,
        maxThreads: 4,
        minThreads: 1
      }
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@components': path.resolve(__dirname, './src/components'),
      '@utils': path.resolve(__dirname, './src/utils'),
      '@hooks': path.resolve(__dirname, './src/hooks'),
      '@contexts': path.resolve(__dirname, './src/contexts'),
      '@types': path.resolve(__dirname, './src/types'),
    }
  }
})