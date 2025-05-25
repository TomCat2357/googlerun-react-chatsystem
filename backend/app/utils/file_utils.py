# app/utils/file_utils.py - ファイル処理ユーティリティ

import os
import base64
import io
import tempfile
import csv
from PIL import Image
from typing import Dict, List, Any, Optional, Tuple
import docx2txt
from common_utils.logger import logger
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
# 開発環境の場合はdevelop_env_pathに対応する.envファイルがある
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# 環境変数から直接取得
MAX_LONG_EDGE = int(os.environ["MAX_LONG_EDGE"])
MAX_IMAGE_SIZE = int(os.environ["MAX_IMAGE_SIZE"])

def process_uploaded_image(image_data: str) -> str:
    """
    画像データを処理し、サイズや形式を調整する
    """
    try:
        header = None
        if image_data.startswith("data:"):
            header, image_data = image_data.split(",", 1)
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        width, height = image.size
        logger.debug(
            "元の画像サイズ: %dx%dpx, 容量: %.1fKB",
            width,
            height,
            len(image_bytes) / 1024,
        )
        if max(width, height) > MAX_LONG_EDGE:
            scale = MAX_LONG_EDGE / max(width, height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.debug("リサイズ後: %dx%dpx", new_width, new_height)
        quality = 85
        output = io.BytesIO()
        output_format = "JPEG"
        mime_type = "image/jpeg"
        if header and "png" in header.lower():
            output_format = "PNG"
            mime_type = "image/png"
            image.save(output, format=output_format, optimize=True)
        else:
            image = image.convert("RGB")
            image.save(output, format=output_format, quality=quality, optimize=True)
        output_data = output.getvalue()
        logger.debug(
            "圧縮後の容量: %.1fKB (quality=%d)", len(output_data) / 1024, quality
        )
        while len(output_data) > MAX_IMAGE_SIZE and quality > 30:
            quality -= 10
            output = io.BytesIO()
            image.save(output, format=output_format, quality=quality, optimize=True)
            output_data = output.getvalue()
            logger.debug(
                "再圧縮後の容量: %.1fKB (quality=%d)", len(output_data) / 1024, quality
            )
        processed_base64 = base64.b64encode(output_data).decode("utf-8")
        return f"data:{mime_type};base64,{processed_base64}"
    except Exception as e:
        logger.error("画像処理エラー: %s", str(e), exc_info=True)
        return image_data

def process_audio_file(audio_data: Dict[str, str]) -> Dict[str, str]:
    """
    音声ファイルを処理する
    """
    try:
        name = audio_data.get("name", "audio.wav")
        content = audio_data.get("content", "")

        # ヘッダー除去（"data:audio/～;base64,..."形式の場合）
        mime_type = "audio/wav"  # デフォルト
        if content.startswith("data:"):
            mime_parts = content.split(",", 1)[0]
            if ";" in mime_parts and ":" in mime_parts:
                mime_type = mime_parts.split(":", 1)[1].split(";", 1)[0]
            content = content.split(",", 1)[1]

        logger.debug(
            f"音声ファイル処理: {name}, MIMEタイプ: {mime_type}, サイズ: {len(content)//1024}KB"
        )

        return {
            "name": name,
            "content": f"[Audio: {name}] 文字起こししてください",  # チャット履歴用表示テキストに文字起こし指示を追加
            "data": content,  # base64エンコードされたデータ
            "mime_type": mime_type,  # MIMEタイプを保存
        }
    except Exception as e:
        logger.error("音声ファイル処理エラー: %s", str(e), exc_info=True)
        return {
            "name": audio_data.get("name", "audio.mp3"),
            "content": "[Audio file processing error]",
            "data": "",
            "mime_type": "audio/mpeg",
        }

def process_text_file(text_file: Dict[str, str]) -> Dict[str, str]:
    """
    テキストファイルを処理する
    """
    try:
        name = text_file.get("name", "file.txt")
        content = text_file.get("content", "")
        file_type = text_file.get("type", "text")

        # ファイルタイプに応じた処理
        if file_type == "csv":
            # CSVのプレビューを作成
            preview = parse_csv_preview(content)
            return {"name": name, "type": "csv", "content": content, "preview": preview}
        elif file_type == "docx":
            return {
                "name": name,
                "type": "docx",
                "content": content,
                "preview": f"[Document: {name}]",
            }
        else:
            # 通常のテキストファイル
            return {
                "name": name,
                "type": "text",
                "content": content,
                "preview": content[:100] + ("..." if len(content) > 100 else ""),
            }
    except Exception as e:
        logger.error("テキストファイル処理エラー: %s", str(e), exc_info=True)
        return {
            "name": text_file.get("name", "file.txt"),
            "type": text_file.get("type", "text"),
            "content": "[Text file processing error]",
            "preview": "[Text file processing error]",
        }

def parse_csv_preview(content: str, max_rows: int = 5) -> str:
    """
    CSVの内容から簡単なプレビューを生成する
    """
    try:
        preview_lines = []
        csv_reader = csv.reader(content.splitlines())

        for i, row in enumerate(csv_reader):
            if i >= max_rows:
                preview_lines.append("...")
                break
            preview_lines.append(", ".join(row))

        return "\n".join(preview_lines)
    except Exception as e:
        logger.error("CSV解析エラー: %s", str(e), exc_info=True)
        return "[CSV parsing error]"

def process_docx_text(docx_content: str) -> str:
    """
    DOCXファイルの内容をテキストとして抽出する
    注: docx_contentはbase64エンコードされたデータ
    """
    try:
        # base64デコード
        binary_data = base64.b64decode(docx_content)

        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(binary_data)

        try:
            # docx2txtを使用してテキスト抽出
            text = docx2txt.process(temp_file_path)
            return text
        finally:
            # 一時ファイルを削除
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    except Exception as e:
        logger.error("DOCXテキスト抽出エラー: %s", str(e), exc_info=True)
        return "[DOCX text extraction error]"

def prepare_message_for_ai(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    メッセージを処理してAIモデルに送信できる形式に変換する
    - 画像のbase64データをURLとして処理する
    - テキストと音声ファイルをメッセージに挿入する
    """
    try:
        processed_message = {
            "role": message.get("role", "user"),
            "content": message.get("content", ""),
        }

        # 添付ファイルのテキスト内容を含める場合、元のコンテンツに追加
        additional_content = []

        # 音声ファイルの処理
        if "audioFiles" in message and message["audioFiles"]:
            for audio in message["audioFiles"]:
                processed_audio = process_audio_file(audio)
                additional_content.append(f"[音声ファイル: {processed_audio['name']}]")

        # テキストファイルの処理
        if "textFiles" in message and message["textFiles"]:
            for text_file in message["textFiles"]:
                processed_text = process_text_file(text_file)
                file_type_label = {
                    "text": "テキストファイル",
                    "csv": "CSVファイル",
                    "docx": "Wordファイル",
                }.get(processed_text["type"], "ファイル")

                additional_content.append(
                    f"\n--- {file_type_label}: {processed_text['name']} ---\n"
                )
                additional_content.append(processed_text["content"])
                additional_content.append("\n--- ファイル終了 ---\n")

        # 追加コンテンツがある場合はメッセージに追加
        if additional_content:
            if processed_message["content"]:
                processed_message["content"] += "\n\n"
            processed_message["content"] += "\n".join(additional_content)

        # 画像処理（従来の形式）
        if "images" in message and message["images"]:
            parts = []
            if processed_message["content"]:
                parts.append({"type": "text", "text": processed_message["content"]})

            for image in message["images"]:
                processed_image = process_uploaded_image(image)
                parts.append(
                    {"type": "image_url", "image_url": {"url": processed_image}}
                )

            processed_message["content"] = parts

        return processed_message
    except Exception as e:
        logger.error("メッセージ処理エラー: %s", str(e), exc_info=True)
        # エラーが発生した場合は、元のメッセージをそのまま返す
        return message