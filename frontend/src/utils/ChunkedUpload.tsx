// frontend/src/components/ChunkedUpload.tsx
import { getServerConfig } from "../config";

// ユーティリティ：Uint8ArrayをBase64文字列に変換
function uint8ToBase64(uint8Array: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < uint8Array.byteLength; i++) {
    binary += String.fromCharCode(uint8Array[i]);
  }
  return btoa(binary);
}

/**
 * sendChunkedRequest
 * チャットリクエストオブジェクトをチャンク分割してサーバーへ送信する関数
 *
 * @param chatRequest - 送信するチャットリクエスト（JSONオブジェクト）
 * @param token - 認証トークン
 * @param apiBaseUrl - APIのベースURL
 * @returns サーバーからの最終レスポンス
 */
export async function sendChunkedRequest(chatRequest: any, token: string, apiBaseUrl: string): Promise<Response> {
  // サーバー設定から最大プロンプトサイズ（バイト数）を取得（例：500KB）
  const serverConfig = getServerConfig();
  const MAX_PAYLOAD_SIZE = parseInt(serverConfig.MAX_PAYLOAD_SIZE, 10);

  const jsonStr = JSON.stringify(chatRequest);
  const encoder = new TextEncoder();
  const data = encoder.encode(jsonStr);
  const totalChunks = Math.ceil(data.length / MAX_PAYLOAD_SIZE);
  // ユニークなチャンクIDを生成（例：タイムスタンプ＋乱数）
  const chunkId = Date.now().toString() + Math.random().toString(36).substr(2, 9);
  let finalResponse: Response | null = null;

  for (let i = 0; i < totalChunks; i++) {
    const start = i * MAX_PAYLOAD_SIZE;
    const end = Math.min(start + MAX_PAYLOAD_SIZE, data.length);
    const chunkData = data.slice(start, end);
    const base64Chunk = uint8ToBase64(chunkData);
    const payload = {
      chunked: true,
      chunkId,
      chunkIndex: i,
      totalChunks,
      chunkData: base64Chunk
    };
    const response = await fetch(`${apiBaseUrl}/backend/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
    if (i < totalChunks - 1) {
      // 中間チャンクの場合、ログ出力（レスポンス内容はチャンク受信状況）
      const resJson = await response.json();
      console.log("Chunk response:", resJson);
    } else {
      // 最終チャンクのレスポンスを最終レスポンスとして扱う
      finalResponse = response;
    }
  }
  if (!finalResponse) {
    throw new Error("送信エラー：最終チャンクのレスポンスがありません");
  }
  return finalResponse;
}
