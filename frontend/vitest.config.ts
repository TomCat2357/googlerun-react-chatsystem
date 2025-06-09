import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    
    // アドバンスドテスト技術対応の設定
    coverage: {
      provider: 'v8', // より高速で正確なカバレッジ
      reporter: ['text', 'html', 'json', 'lcov', 'text-summary'],
      exclude: [
        'node_modules/',
        'dist/',
        'src/test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/index.ts',
        '**/index.tsx',
        'src/firebase/',
        'src/vite-env.d.ts',
        // テストヘルパーとファクトリ
        'src/test/helpers/**',
        'src/test/factories/**',
        // モックファイル
        '**/__mocks__/**',
        '**/mocks/**'
      ],
      include: [
        'src/**/*.{ts,tsx}',
        '!src/**/*.{test,spec}.{ts,tsx}',
        '!src/test/**/*'
      ],
      thresholds: {
        global: {
          branches: 75,
          functions: 80,
          lines: 80,
          statements: 80
        },
        // コンポーネント別の詳細な閾値
        'src/components/': {
          branches: 80,
          functions: 85,
          lines: 85,
          statements: 85
        },
        'src/hooks/': {
          branches: 90,
          functions: 90,
          lines: 90,
          statements: 90
        },
        'src/utils/': {
          branches: 95,
          functions: 95,
          lines: 95,
          statements: 95
        }
      },
      // 未カバレッジファイルもレポートに含める
      all: true,
      // カバレッジレポートの詳細設定
      reportOnFailure: true,
      skipFull: false
    },
    
    // テストファイルのパターン（アドバンスドパターン対応）
    include: [
      'src/**/*.{test,spec}.{js,ts,jsx,tsx}',
      // 統合テスト
      'src/**/__tests__/integration/*.{js,ts,jsx,tsx}',
      // パフォーマンステスト
      'src/**/__tests__/performance/*.{js,ts,jsx,tsx}',
      // アクセシビリティテスト
      'src/**/__tests__/accessibility/*.{js,ts,jsx,tsx}',
      // ビジュアルリグレッションテスト
      'src/**/__tests__/visual/*.{js,ts,jsx,tsx}'
    ],
    
    // テスト除外パターン
    exclude: [
      'node_modules/',
      'dist/',
      'build/',
      // 特定の実験的テスト
      'src/**/__tests__/experimental/*.{js,ts,jsx,tsx}',
      // 手動実行のみのテスト
      'src/**/__tests__/manual/*.{js,ts,jsx,tsx}'
    ],
    
    // タイムアウト設定（アドバンスド）
    testTimeout: 15000, // 複雑なテスト用に増加
    hookTimeout: 15000,
    teardownTimeout: 5000,
    
    // モック設定の詳細化
    clearMocks: true,
    restoreMocks: true,
    resetMocks: false, // グローバルモックの保持
    
    // 並列実行設定（パフォーマンス最適化）
    pool: 'threads',
    poolOptions: {
      threads: {
        singleThread: false,
        maxThreads: Math.max(1, Math.floor(require('os').cpus().length / 2)),
        minThreads: 1,
        isolate: true
      }
    },
    
    // 高度なテストレポート設定
    reporter: ['verbose', 'json', 'html'],
    outputFile: {
      json: './test-results/vitest-results.json',
      html: './test-results/vitest-report.html'
    },
    
    // パフォーマンステスト用の設定
    benchmark: {
      include: ['src/**/*.{bench,benchmark}.{js,ts,jsx,tsx}'],
      exclude: ['node_modules/', 'dist/'],
      reporter: ['verbose']
    },
    
    // ウォッチモード設定
    watch: true,
    watchExclude: [
      'node_modules/',
      'dist/',
      '**/*.log',
      '**/coverage/**',
      '**/test-results/**'
    ],
    
    // デバッグ設定
    logHeapUsage: true,
    isolate: true,
    
    // 環境変数の設定
    env: {
      NODE_ENV: 'test',
      VITEST: 'true',
      // テスト用の設定値
      VITE_API_BASE_URL: 'http://localhost:3000',
      VITE_ENABLE_MOCK: 'true'
    },
    
    // グローバル設定
    globals: true,
    
    // TypeScript設定
    typecheck: {
      enabled: true,
      tsconfig: './tsconfig.json',
      include: ['src/**/*.{test,spec}.{ts,tsx}']
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
      '@test': path.resolve(__dirname, './src/test'),
      '@factories': path.resolve(__dirname, './src/test/factories'),
      '@helpers': path.resolve(__dirname, './src/test/helpers')
    }
  },
  
  // ビルド設定（テスト用）
  build: {
    sourcemap: true,
    minify: false
  },
  
  // 開発サーバー設定（テスト用）
  server: {
    port: 3000,
    host: true
  }
})