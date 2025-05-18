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

# ロガーの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# プロジェクト情報とエミュレータの設定
PROJECT_ID = "supportaisystem20250412"
FIRESTORE_PORT = 8081
GCS_PORT = 9000

# GCSエミュレータのデータ保存先 (Dockerモード専用)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GCS_DATA_PATH_DOCKER = os.path.join(BASE_DIR, 'gcs_data_docker')
# GCS_DATA_PATH_LOCAL = os.path.join(BASE_DIR, 'gcs_data_local') # ローカルバイナリモード用パスは削除

def create_initial_data(fs_client, gcs_client):
    """初期データの作成（必要に応じて）"""
    logger.info("初期データの設定を行います...")
    
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
            "created_at": time.time(),
            "audio_file": "sample.mp3",
            "result_file": ""
        })
        logger.info("Firestoreに初期データを作成しました")
    except Exception as e:
        logger.warning(f"Firestore初期データ作成でエラーが発生しました: {e}")

def run_emulators(init_data=False): # use_docker 引数を削除
    """FirestoreとGCSエミュレータを起動する関数"""
    logger.info("エミュレータを起動します...")
    
    try:
        # Firestoreエミュレータの起動
        # executable_path はご自身の環境に合わせてgcloudコマンドのパスを指定
        with firestore_emulator_context(
            project_id=PROJECT_ID, 
            port=FIRESTORE_PORT, 
            executable_path='gcloud'
        ) as fs_emulator_client:
            logger.info(f"Firestore Emulator Host: {os.getenv('FIRESTORE_EMULATOR_HOST')}")
            logger.info(f"Firestore Emulator Project ID: {fs_emulator_client.project}")

            # GCSエミュレータの起動 (常にDockerを使用)
            host_data_path = GCS_DATA_PATH_DOCKER
            logger.info(f"GCS Emulator: Docker モードで起動します")
            with gcs_emulator_context(
                project_id=PROJECT_ID, 
                port=GCS_PORT, 
                use_docker=True, # 明示的にTrueを指定 (元々デフォルトだがより明確に)
                host_data_path=host_data_path
            ) as gcs_emulator_client:
                _run_with_emulators(fs_emulator_client, gcs_emulator_client, init_data)

    except RuntimeError as e:
        logger.error(f"エミュレータの起動に失敗しました: {e}")
    except KeyboardInterrupt:
        logger.info("エミュレータを停止します。")
    finally:
        logger.info("エミュレータの実行を終了します。")

def _run_with_emulators(fs_client, gcs_client, init_data):
    """エミュレータが起動した後の処理"""
    logger.info(f"GCS Emulator Host: {os.getenv('STORAGE_EMULATOR_HOST')}")
    logger.info(f"GCS Emulator Project ID: {gcs_client.project}")
    
    # 初期データの作成（オプション）
    if init_data:
        create_initial_data(fs_client, gcs_client)
    
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
    # parser.add_argument('--no-docker', action='store_true', help='Dockerを使用せずにローカルバイナリを使用') # --no-docker オプションを削除
    parser.add_argument('--init-data', action='store_true', help='初期データを作成')
    args = parser.parse_args()
    
    # ディレクトリの作成 (Dockerモード用のみ)
    os.makedirs(GCS_DATA_PATH_DOCKER, exist_ok=True)
    # os.makedirs(GCS_DATA_PATH_LOCAL, exist_ok=True) # ローカルバイナリモード用パスは削除
    
    # エミュレータの起動 (use_dockerは常にTrueとして扱われる)
    run_emulators(init_data=args.init_data)