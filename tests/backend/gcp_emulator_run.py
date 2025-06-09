#!/usr/bin/env python3
# coding: utf-8

"""
FirestoreとGCSエミュレータを起動するスクリプト
このスクリプトは開発・テスト環境でGCP関連のエミュレータを起動します
"""

from common_utils.gcp_emulator import firestore_emulator_context, gcs_emulator_context
import os
import logging
import argparse
import time
from pathlib import Path
# Firestore および GCS のクライアントライブラリをインポート
from google.cloud import firestore
from google.cloud import storage


# ロガーの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# プロジェクト情報とエミュレータの設定
PROJECT_ID = "supportaisystem20250412"
FIRESTORE_PORT = 8081
GCS_PORT = 9000

# プロジェクトルートの推定
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
logger.info(f"Detected PROJECT_ROOT: {PROJECT_ROOT}")

# 注意: GCSエミュレータはin-memoryで動作し、データは永続化されません
logger.info("GCSエミュレータはin-memoryで動作し、データは永続化されません")

def create_initial_data(fs_emulator_instance, gcs_emulator_instance):
    """初期データの作成（必要に応じて）"""
    logger.info("初期データの設定を行います...")

    try:
        # エミュレータのプロジェクトIDを使用してクライアントを初期化
        fs_client = firestore.Client(project=fs_emulator_instance.project_id)
        gcs_client = storage.Client(project=gcs_emulator_instance.project_id)
    except Exception as e:
        logger.error(f"GCPクライアントの初期化に失敗しました: {e}")
        return

    # GCSバケットの作成例（Whisper用）
    try:
        bucket_name = "whisper-audio-storage"
        gcs_client.create_bucket(bucket_name)
        logger.info(f"バケット '{bucket_name}' を作成しました")
        
        # 出力用バケットも作成
        output_bucket = "whisper-results-storage"
        gcs_client.create_bucket(output_bucket)
        logger.info(f"バケット '{output_bucket}' を作成しました")
    except Exception as e:
        logger.warning(f"バケット作成でエラーが発生しました: {e}")
    
    # Firestoreの初期コレクション作成例
    try:
        # トランスクリプションジョブ用コレクション
        coll_ref = fs_client.collection("transcription_jobs")
        # サンプルドキュメント
        coll_ref.document("sample_job").set({
            "status": "pending",
            "created_at": firestore.SERVER_TIMESTAMP, # Firestoreサーバーのタイムスタンプを使用
            "audio_file": "sample.mp3",
            "result_file": ""
        })
        logger.info("Firestoreに初期データを作成しました")
    except Exception as e:
        logger.warning(f"Firestore初期データ作成でエラーが発生しました: {e}")

def run_emulators(init_data=False):
    """FirestoreとGCSエミュレータを起動する関数"""
    logger.info("エミュレータを起動します...")
    
    try:
        # Firestoreエミュレータの起動
        # executable_path はご自身の環境に合わせてgcloudコマンドのパスを指定
        with firestore_emulator_context(
            project_id=PROJECT_ID, 
            port=FIRESTORE_PORT, 
            executable_path='gcloud'
        ) as fs_emulator:
            logger.info(f"Firestore Emulator Host: {os.getenv('FIRESTORE_EMULATOR_HOST')}")
            logger.info(f"Firestore Emulator Project ID: {fs_emulator.project_id}")
            
            # GCSエミュレータの起動 (常にDockerを使用)
            logger.info(f"GCS Emulator: Docker モードで起動します")
            logger.info(f"注意: GCSエミュレータはin-memoryで動作し、データは永続化されません")
            
            with gcs_emulator_context(
                project_id=PROJECT_ID, 
                port=GCS_PORT, 
                use_docker=True, # 明示的にTrueを指定 (元々デフォルトだがより明確に)
                host_data_path=None  # データ永続化なし
            ) as gcs_emulator:
                _run_with_emulators(fs_emulator, gcs_emulator, init_data)

    except RuntimeError as e:
        logger.error(f"エミュレータの起動に失敗しました: {e}")
    except KeyboardInterrupt:
        logger.info("エミュレータを停止します。")
    finally:
        logger.info("エミュレータの実行を終了します。")

def _run_with_emulators(fs_emulator_instance, gcs_emulator_instance, init_data):
    """エミュレータが起動した後の処理"""
    logger.info(f"GCS Emulator Host: {os.getenv('STORAGE_EMULATOR_HOST')}")
    logger.info(f"GCS Emulator Project ID: {gcs_emulator_instance.project_id}")
    logger.info(f"GCS Emulator Container Name: {gcs_emulator_instance.container_name}")
    logger.info(f"Inside _run_with_emulators. init_data flag is: {init_data}")
    
    # GCSエミュレータはDockerコンテナ内でin-memoryで動作するため、
    # ホスト側のファイルシステムパスは使用しない
    logger.info("GCSエミュレータはコンテナ内でin-memoryで動作します")
    
    if init_data:
        logger.info("Condition for clearing GCS data is TRUE (init_data=True). Calling gcs_emulator_instance.clear_data().")
        logger.info("Clearing GCS data because --init-data was specified.")
        gcs_emulator_instance.clear_data() # ★ --init-data が指定された場合のみGCSデータをクリア
        logger.info("GCSデータクリア完了")
    else:
        logger.info("Condition for clearing GCS data is FALSE (init_data=False). Skipping gcs_emulator_instance.clear_data().")
    
    # 初期データの作成（オプション）
    if init_data:
        create_initial_data(fs_emulator_instance, gcs_emulator_instance)
    
    logger.info("---------------------------------------------")
    logger.info("両方のエミュレータが起動しました。Ctrl+Cで停止します。")
    logger.info("---------------------------------------------")
    logger.info(f"エミュレータの接続情報:")
    logger.info(f"Firestore: {os.getenv('FIRESTORE_EMULATOR_HOST')}")
    logger.info(f"GCS: {os.getenv('STORAGE_EMULATOR_HOST')}")
    logger.info("---------------------------------------------")
    
    # エミュレータを起動し続ける
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("エミュレータを停止します。")
        raise

if __name__ == '__main__':
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='FirestoreとGCSエミュレータを起動します (Dockerモード専用)')
    parser.add_argument('--init-data', action='store_true', help='初期データを作成')
    args = parser.parse_args()
    
    # エミュレータの起動
    run_emulators(init_data=args.init_data)