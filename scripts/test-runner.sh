#!/bin/bash

# アドバンスドテスト実行スクリプト
# Advanced Test Execution Scripts

set -e

# 色付きの出力関数
print_header() {
    echo -e "\033[1;34m=== $1 ===\033[0m"
}

print_success() {
    echo -e "\033[1;32m✓ $1\033[0m"
}

print_error() {
    echo -e "\033[1;31m✗ $1\033[0m"
}

print_info() {
    echo -e "\033[1;33m• $1\033[0m"
}

# 使用方法の表示
show_usage() {
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  unit                バックエンド単体テスト実行"
    echo "  integration         バックエンド統合テスト実行"
    echo "  frontend            フロントエンドテスト実行"
    echo "  whisper             Whisper機能テスト実行"
    echo "  performance         パフォーマンステスト実行"
    echo "  behavior-driven     振る舞い駆動テスト実行"
    echo "  emulator            エミュレータテスト実行"
    echo "  fast                高速テストのみ実行"
    echo "  coverage            カバレッジレポート付きテスト実行"
    echo "  all                 全テスト実行"
    echo "  help                このヘルプを表示"
    echo ""
    echo "Advanced Examples:"
    echo "  $0 unit              # 高速な単体テストのみ"
    echo "  $0 integration       # 統合テスト（エミュレータ使用）"
    echo "  $0 performance       # パフォーマンステスト"
    echo "  $0 coverage          # カバレッジレポート生成"
}

# バックエンド単体テスト
run_backend_unit_tests() {
    print_header "バックエンド単体テスト実行"
    cd backend
    pytest -m "unit and not integration and not slow" \
           --tb=short \
           --durations=10 \
           -v
    cd ..
    print_success "バックエンド単体テスト完了"
}

# バックエンド統合テスト
run_backend_integration_tests() {
    print_header "バックエンド統合テスト実行（エミュレータ使用）"
    
    # エミュレータ起動チェック
    print_info "GCPエミュレータの起動確認..."
    if ! python tests/app/gcp_emulator_run.py --check 2>/dev/null; then
        print_info "エミュレータを起動中..."
        python tests/app/gcp_emulator_run.py &
        EMULATOR_PID=$!
        sleep 5
    fi
    
    pytest -m "integration or emulator" \
           --tb=short \
           --durations=10 \
           -v
    
    # エミュレータ停止（必要に応じて）
    if [ ! -z "$EMULATOR_PID" ]; then
        print_info "エミュレータを停止中..."
        kill $EMULATOR_PID 2>/dev/null || true
    fi
    
    print_success "バックエンド統合テスト完了"
}

# フロントエンドテスト
run_frontend_tests() {
    print_header "フロントエンドテスト実行"
    cd frontend
    
    # 基本テスト実行
    npm run test:run
    
    print_success "フロントエンドテスト完了"
    cd ..
}

# Whisper機能テスト
run_whisper_tests() {
    print_header "Whisper機能テスト実行"
    
    # バックエンドWhisperテスト
    pytest -m "whisper" \
           --tb=short \
           -v
    
    # フロントエンドWhisperテスト
    cd frontend
    npm run test:run -- --reporter=verbose "src/components/Whisper"
    cd ..
    
    print_success "Whisper機能テスト完了"
}

# パフォーマンステスト
run_performance_tests() {
    print_header "パフォーマンステスト実行"
    
    # バックエンドパフォーマンステスト
    pytest -m "performance or benchmark" \
           --tb=no \
           -v \
           --durations=0
    
    # フロントエンドパフォーマンステスト
    cd frontend
    npm run test:run -- --reporter=verbose "src/**/*.performance.test.*"
    cd ..
    
    print_success "パフォーマンステスト完了"
}

# 振る舞い駆動テスト
run_behavior_driven_tests() {
    print_header "振る舞い駆動テスト実行"
    
    # バックエンド振る舞い駆動テスト
    pytest -m "behavior_driven" \
           --tb=short \
           -v
    
    # フロントエンド振る舞い駆動テスト
    cd frontend
    npm run test:run -- --reporter=verbose "src/**/*BehaviorDriven*.test.*"
    cd ..
    
    print_success "振る舞い駆動テスト完了"
}

# エミュレータテスト
run_emulator_tests() {
    print_header "GCPエミュレータテスト実行"
    
    # エミュレータ起動
    print_info "GCPエミュレータを起動中..."
    python tests/app/gcp_emulator_run.py &
    EMULATOR_PID=$!
    sleep 5
    
    # エミュレータの動作確認
    pytest tests/app/test_emulator_availability.py -v
    
    # エミュレータ使用テスト実行
    pytest -m "emulator" \
           --tb=short \
           -v
    
    # エミュレータ停止
    print_info "エミュレータを停止中..."
    kill $EMULATOR_PID 2>/dev/null || true
    
    print_success "エミュレータテスト完了"
}

# 高速テスト
run_fast_tests() {
    print_header "高速テスト実行"
    
    # バックエンド高速テスト
    pytest -m "fast and not slow and not very_slow" \
           --tb=line \
           -v \
           --durations=5
    
    # フロントエンド高速テスト
    cd frontend
    npm run test:run -- --reporter=basic
    cd ..
    
    print_success "高速テスト完了"
}

# カバレッジレポート付きテスト
run_coverage_tests() {
    print_header "カバレッジレポート付きテスト実行"
    
    # バックエンドカバレッジ
    pytest --cov=backend \
           --cov-report=html:htmlcov \
           --cov-report=xml \
           --cov-report=term-missing \
           --cov-fail-under=70 \
           -m "not very_slow"
    
    # フロントエンドカバレッジ
    cd frontend
    npm run test:coverage
    cd ..
    
    print_success "カバレッジレポート生成完了"
    print_info "バックエンドレポート: htmlcov/index.html"
    print_info "フロントエンドレポート: frontend/coverage/index.html"
}

# 全テスト実行
run_all_tests() {
    print_header "全テスト実行"
    
    # 順次実行
    run_fast_tests
    run_backend_unit_tests
    run_frontend_tests
    run_whisper_tests
    run_backend_integration_tests
    
    print_success "全テスト完了"
}

# メイン処理
case "${1:-help}" in
    "unit")
        run_backend_unit_tests
        ;;
    "integration")
        run_backend_integration_tests
        ;;
    "frontend")
        run_frontend_tests
        ;;
    "whisper")
        run_whisper_tests
        ;;
    "performance")
        run_performance_tests
        ;;
    "behavior-driven")
        run_behavior_driven_tests
        ;;
    "emulator")
        run_emulator_tests
        ;;
    "fast")
        run_fast_tests
        ;;
    "coverage")
        run_coverage_tests
        ;;
    "all")
        run_all_tests
        ;;
    "help"|*)
        show_usage
        ;;
esac

print_info "テスト実行スクリプトの実行完了"