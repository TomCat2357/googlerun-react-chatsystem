#!/usr/bin/env python3
"""
シンプルなFirestoreエミュレーターDB操作テスト

このスクリプトは、Firestoreエミュレーターを使用して基本的なCRUD操作をテストします。
・データの保存（Create）
・データの読み取り（Read）  
・データの更新（Update）
・データの削除（Delete）
・クエリ操作
"""

import os
import json
from datetime import datetime
from google.cloud import firestore


def setup_environment():
    """エミュレーター用の環境変数設定"""
    os.environ['FIRESTORE_EMULATOR_HOST'] = 'localhost:8081'
    os.environ['GOOGLE_CLOUD_PROJECT'] = 'test-emulator-project'
    
    print(f"✅ 環境変数設定完了:")
    print(f"   FIRESTORE_EMULATOR_HOST: {os.environ.get('FIRESTORE_EMULATOR_HOST')}")
    print(f"   GOOGLE_CLOUD_PROJECT: {os.environ.get('GOOGLE_CLOUD_PROJECT')}")


def test_basic_crud_operations():
    """基本的なCRUD操作のテスト"""
    print("\n" + "="*50)
    print("🔸 基本的なCRUD操作テスト開始")
    print("="*50)
    
    # Firestoreクライアント初期化
    db = firestore.Client()
    
    # テスト用データ
    user_data = {
        'name': '田中太郎',
        'email': 'tanaka@example.com',
        'age': 30,
        'department': 'エンジニアリング',
        'skills': ['Python', 'JavaScript', 'React'],
        'created_at': firestore.SERVER_TIMESTAMP,
        'is_active': True
    }
    
    user_id = 'user_001'
    collection_name = 'users'
    
    try:
        # === CREATE (データ保存) ===
        print("\n1️⃣ CREATE: データ保存テスト")
        user_ref = db.collection(collection_name).document(user_id)
        user_ref.set(user_data)
        print(f"✅ ユーザーデータを保存しました: {user_id}")
        
        # === READ (データ読み取り) ===
        print("\n2️⃣ READ: データ読み取りテスト")
        doc = user_ref.get()
        
        if doc.exists:
            saved_data = doc.to_dict()
            print(f"✅ データ読み取り成功:")
            print(f"   名前: {saved_data['name']}")
            print(f"   メール: {saved_data['email']}")
            print(f"   年齢: {saved_data['age']}")
            print(f"   部署: {saved_data['department']}")
            print(f"   スキル: {', '.join(saved_data['skills'])}")
            print(f"   ステータス: {'アクティブ' if saved_data['is_active'] else '非アクティブ'}")
        else:
            print("❌ ドキュメントが見つかりません")
            return False
        
        # === UPDATE (データ更新) ===
        print("\n3️⃣ UPDATE: データ更新テスト")
        # 年齢を更新し、新しいスキルを追加
        update_data = {
            'age': 31,
            'skills': firestore.ArrayUnion(['Docker', 'Kubernetes']),
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        user_ref.update(update_data)
        print("✅ データ更新完了（年齢+1、スキル追加）")
        
        # 更新後のデータ確認
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        print(f"   更新後年齢: {updated_data['age']}")
        print(f"   更新後スキル: {', '.join(updated_data['skills'])}")
        
        # === DELETE (データ削除) ===
        print("\n4️⃣ DELETE: データ削除テスト")
        user_ref.delete()
        print(f"✅ ユーザーデータを削除しました: {user_id}")
        
        # 削除確認
        deleted_doc = user_ref.get()
        if not deleted_doc.exists:
            print("✅ 削除確認完了: ドキュメントが存在しません")
        else:
            print("❌ 削除失敗: ドキュメントがまだ存在します")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ CRUD操作でエラーが発生しました: {e}")
        return False


def test_query_operations():
    """クエリ操作のテスト"""
    print("\n" + "="*50)
    print("🔸 クエリ操作テスト開始")
    print("="*50)
    
    db = firestore.Client()
    collection_name = 'employees'
    
    try:
        # テスト用の複数データを作成
        print("\n1️⃣ テストデータ作成")
        test_employees = [
            {
                'name': '山田花子',
                'department': 'マーケティング',
                'salary': 5000000,
                'experience_years': 3,
                'skills': ['SQL', 'Excel', 'PowerBI']
            },
            {
                'name': '佐藤次郎',
                'department': 'エンジニアリング', 
                'salary': 7000000,
                'experience_years': 5,
                'skills': ['Python', 'AWS', 'Docker']
            },
            {
                'name': '高橋三郎',
                'department': 'エンジニアリング',
                'salary': 8500000,
                'experience_years': 8,
                'skills': ['Java', 'Kubernetes', 'Terraform']
            },
            {
                'name': '田島美咲',
                'department': 'デザイン',
                'salary': 4500000,
                'experience_years': 2,
                'skills': ['Photoshop', 'Illustrator', 'Figma']
            }
        ]
        
        # データを保存
        for i, employee in enumerate(test_employees):
            employee['created_at'] = firestore.SERVER_TIMESTAMP
            employee['employee_id'] = f'emp_{i+1:03d}'
            
            db.collection(collection_name).document(f'employee_{i+1}').set(employee)
        
        print(f"✅ {len(test_employees)}件のテストデータを作成しました")
        
        # === WHERE句によるフィルタリング ===
        print("\n2️⃣ WHERE句によるフィルタリングテスト")
        
        # エンジニアリング部門の社員を検索
        engineering_query = db.collection(collection_name).where('department', '==', 'エンジニアリング')
        engineering_employees = list(engineering_query.stream())
        
        print(f"🔍 エンジニアリング部門の社員: {len(engineering_employees)}名")
        for emp_doc in engineering_employees:
            emp_data = emp_doc.to_dict()
            print(f"   - {emp_data['name']} (経験年数: {emp_data['experience_years']}年)")
        
        # 高給与社員を検索（600万円以上）
        high_salary_query = db.collection(collection_name).where('salary', '>=', 6000000)
        high_salary_employees = list(high_salary_query.stream())
        
        print(f"\n🔍 高給与社員（600万円以上）: {len(high_salary_employees)}名")
        for emp_doc in high_salary_employees:
            emp_data = emp_doc.to_dict()
            print(f"   - {emp_data['name']} (給与: {emp_data['salary']:,}円)")
        
        # === ORDER BY句による並び替え ===
        print("\n3️⃣ ORDER BY句による並び替えテスト")
        
        # 経験年数の降順で並び替え
        ordered_query = db.collection(collection_name).order_by('experience_years', direction=firestore.Query.DESCENDING)
        ordered_employees = list(ordered_query.stream())
        
        print("🔍 経験年数順（降順）:")
        for emp_doc in ordered_employees:
            emp_data = emp_doc.to_dict()
            print(f"   - {emp_data['name']}: {emp_data['experience_years']}年")
        
        # === LIMIT句による件数制限 ===
        print("\n4️⃣ LIMIT句による件数制限テスト")
        
        # 上位2名のみ取得
        limited_query = db.collection(collection_name).order_by('salary', direction=firestore.Query.DESCENDING).limit(2)
        top_earners = list(limited_query.stream())
        
        print("🔍 給与上位2名:")
        for emp_doc in top_earners:
            emp_data = emp_doc.to_dict()
            print(f"   - {emp_data['name']}: {emp_data['salary']:,}円")
        
        # === 複合クエリ ===
        print("\n5️⃣ 複合クエリテスト")
        
        # エンジニアリング部門かつ経験年数5年以上
        complex_query = (db.collection(collection_name)
                        .where('department', '==', 'エンジニアリング')
                        .where('experience_years', '>=', 5))
        senior_engineers = list(complex_query.stream())
        
        print(f"🔍 シニアエンジニア（経験5年以上）: {len(senior_engineers)}名")
        for emp_doc in senior_engineers:
            emp_data = emp_doc.to_dict()
            print(f"   - {emp_data['name']} (経験: {emp_data['experience_years']}年, スキル: {', '.join(emp_data['skills'])})")
        
        # === 配列フィールドのクエリ ===
        print("\n6️⃣ 配列フィールドのクエリテスト")
        
        # Pythonスキルを持つ社員
        python_query = db.collection(collection_name).where('skills', 'array_contains', 'Python')
        python_developers = list(python_query.stream())
        
        print(f"🔍 Pythonスキル保有者: {len(python_developers)}名")
        for emp_doc in python_developers:
            emp_data = emp_doc.to_dict()
            print(f"   - {emp_data['name']}: {', '.join(emp_data['skills'])}")
        
        # === データ件数の取得 ===
        print("\n7️⃣ データ件数取得テスト")
        
        all_employees = list(db.collection(collection_name).stream())
        print(f"🔍 全社員数: {len(all_employees)}名")
        
        # 部門別集計
        departments = {}
        for emp_doc in all_employees:
            emp_data = emp_doc.to_dict()
            dept = emp_data['department']
            departments[dept] = departments.get(dept, 0) + 1
        
        print("🔍 部門別人数:")
        for dept, count in departments.items():
            print(f"   - {dept}: {count}名")
        
        # === クリーンアップ ===
        print("\n8️⃣ テストデータクリーンアップ")
        for emp_doc in all_employees:
            emp_doc.reference.delete()
        print("✅ 全テストデータを削除しました")
        
        return True
        
    except Exception as e:
        print(f"❌ クエリ操作でエラーが発生しました: {e}")
        return False


def test_transaction_operations():
    """トランザクション操作のテスト"""
    print("\n" + "="*50)
    print("🔸 トランザクション操作テスト開始")
    print("="*50)
    
    db = firestore.Client()
    
    try:
        # テスト用のアカウントデータ作成
        print("\n1️⃣ テスト用アカウントデータ作成")
        
        account_a_ref = db.collection('accounts').document('account_a')
        account_b_ref = db.collection('accounts').document('account_b')
        
        account_a_ref.set({
            'name': 'アカウントA',
            'balance': 10000,
            'created_at': firestore.SERVER_TIMESTAMP
        })
        
        account_b_ref.set({
            'name': 'アカウントB', 
            'balance': 5000,
            'created_at': firestore.SERVER_TIMESTAMP
        })
        
        print("✅ テスト用アカウントを作成しました")
        print("   アカウントA: 10,000円")
        print("   アカウントB: 5,000円")
        
        # === トランザクションによる送金処理 ===
        print("\n2️⃣ トランザクション送金処理テスト")
        
        transfer_amount = 3000
        
        @firestore.transactional
        def transfer_money(transaction, from_ref, to_ref, amount):
            """トランザクション内での送金処理"""
            # 送金元の残高確認
            from_doc = from_ref.get(transaction=transaction)
            from_data = from_doc.to_dict()
            
            if from_data['balance'] < amount:
                raise ValueError(f"残高不足: 現在残高 {from_data['balance']}円 < 送金額 {amount}円")
            
            # 送金先の情報取得
            to_doc = to_ref.get(transaction=transaction)
            to_data = to_doc.to_dict()
            
            # 残高更新
            transaction.update(from_ref, {
                'balance': from_data['balance'] - amount,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            transaction.update(to_ref, {
                'balance': to_data['balance'] + amount,
                'updated_at': firestore.SERVER_TIMESTAMP  
            })
            
            return {
                'from_balance': from_data['balance'] - amount,
                'to_balance': to_data['balance'] + amount
            }
        
        # トランザクション実行
        transaction = db.transaction()
        result = transfer_money(transaction, account_a_ref, account_b_ref, transfer_amount)
        
        print(f"✅ 送金処理完了: {transfer_amount:,}円をアカウントA→アカウントBに送金")
        print(f"   アカウントA残高: {result['from_balance']:,}円")
        print(f"   アカウントB残高: {result['to_balance']:,}円")
        
        # === 残高確認 ===
        print("\n3️⃣ 送金後残高確認")
        
        final_account_a = account_a_ref.get().to_dict()
        final_account_b = account_b_ref.get().to_dict()
        
        print(f"✅ 最終残高確認:")
        print(f"   アカウントA: {final_account_a['balance']:,}円")
        print(f"   アカウントB: {final_account_b['balance']:,}円")
        print(f"   合計: {final_account_a['balance'] + final_account_b['balance']:,}円")
        
        # === 残高不足エラーのテスト ===
        print("\n4️⃣ 残高不足エラーテスト")
        
        try:
            # 現在の残高以上の金額を送金しようとする
            excessive_amount = final_account_a['balance'] + 1000
            transaction2 = db.transaction()
            transfer_money(transaction2, account_a_ref, account_b_ref, excessive_amount)
            print("❌ 残高不足エラーが発生すべきでした")
            return False
            
        except ValueError as e:
            print(f"✅ 期待通りの残高不足エラーが発生: {e}")
        
        # === クリーンアップ ===
        print("\n5️⃣ テストデータクリーンアップ")
        account_a_ref.delete()
        account_b_ref.delete()
        print("✅ テスト用アカウントを削除しました")
        
        return True
        
    except Exception as e:
        print(f"❌ トランザクション操作でエラーが発生しました: {e}")
        return False


def main():
    """メインテスト実行関数"""
    print("🚀 シンプルなFirestoreエミュレーターDB操作テスト開始")
    print("="*60)
    
    # 環境設定
    setup_environment()
    
    # テスト実行
    tests = [
        ("基本CRUD操作", test_basic_crud_operations),
        ("クエリ操作", test_query_operations),
        ("トランザクション操作", test_transaction_operations)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🔥 {test_name}テスト実行中...")
        try:
            result = test_func()
            results.append((test_name, result))
            
            if result:
                print(f"✅ {test_name}: 成功")
            else:
                print(f"❌ {test_name}: 失敗")
                
        except Exception as e:
            print(f"❌ {test_name}: 例外発生 - {e}")
            results.append((test_name, False))
    
    # 結果サマリー
    print("\n" + "="*60)
    print("📊 テスト結果サマリー")
    print("="*60)
    
    success_count = sum(1 for _, result in results if result)
    total_count = len(results)
    
    for test_name, result in results:
        status = "✅ 成功" if result else "❌ 失敗"
        print(f"  {test_name}: {status}")
    
    print(f"\n🎯 総合結果: {success_count}/{total_count} テスト成功")
    success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
    print(f"📈 成功率: {success_rate:.1f}%")
    
    if success_count == total_count:
        print("\n🎉 全てのテストが成功しました！")
        print("✨ Firestoreエミュレーターが完全に動作しています。")
    else:
        print("\n⚠️ 一部のテストが失敗しました。")
        print("🔧 エミュレーターの設定やネットワーク接続を確認してください。")
    
    return success_count == total_count


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
