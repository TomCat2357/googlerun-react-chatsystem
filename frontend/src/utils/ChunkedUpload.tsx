// frontend/src/utils/ChunkedUpload.tsx
import * as Config from "../config";

// Uint8ArrayをBase64に変換するヘルパー関数
function uint8ToBase64(data: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < data.byteLength; i++) {
    binary += String.fromCharCode(data[i]);
  }
  return btoa(binary);
}

export async function sendChunkedRequest(chatRequest: any, token: string, destUrl: string): Promise<Response> {
  // Configモジュールからサーバー設定を取得し、最大プロンプトサイズ（バイト数）をパースする
  const serverConfig = Config.getServerConfig();
  const MAX_PAYLOAD_SIZE = serverConfig.MAX_PAYLOAD_SIZE || 500000;
  
  // 音声データかどうかを判定
  const isSpeechRequest = destUrl.includes('/speech2text');
  const isBinary = isSpeechRequest;
  
  const jsonStr = JSON.stringify(chatRequest);
  const encoder = new TextEncoder();
  const data = encoder.encode(jsonStr);
  const totalChunks = Math.ceil(data.length / MAX_PAYLOAD_SIZE);
  
  // ユニークなチャンクIDを生成（例：タイムスタンプ＋乱数）
  const chunkId = Date.now().toString() + Math.random().toString(36).substr(2, 9);
  let finalResponse: Response | null = null;

  console.log(`総データサイズ: ${data.length} バイト, 合計チャンク数: ${totalChunks}, 音声データ: ${isSpeechRequest}`);

  try {
    for (let i = 0; i < totalChunks; i++) {
      const start = i * MAX_PAYLOAD_SIZE;
      const end = Math.min(start + MAX_PAYLOAD_SIZE, data.length);
      const chunkData = data.slice(start, end);
      const base64Chunk = uint8ToBase64(chunkData);
      
      console.log(`チャンク ${i+1}/${totalChunks} を送信中: ${chunkData.length} バイト`);
      
      const payload = {
        chunked: true,
        chunkId,
        chunkIndex: i,
        totalChunks,
        chunkData: base64Chunk,
        isBinary // 音声データの場合はバイナリフラグをtrueに設定
      };
      
      try {
        // 送信先URL（destUrl）に対してPOSTリクエストを実施
        const response = await fetch(destUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
          body: JSON.stringify(payload),
        });
        
        if (!response.ok) {
          // エラーレスポンスのボディを取得して詳細情報を表示
          try {
            const errorData = await response.json();
            throw new Error(`サーバーエラー: ${response.status} ${response.statusText}, 詳細: ${JSON.stringify(errorData)}`);
          } catch (jsonError) {
            throw new Error(`サーバーエラー: ${response.status} ${response.statusText}`);
          }
        }
        
        if (i < totalChunks - 1) {
          // 最終チャンク以外の場合は、レスポンスをJSONとして解析
          const resJson = await response.json();
          console.log(`チャンク ${i+1}/${totalChunks} レスポンス:`, resJson);
          
          // ステータスチェック
          if (resJson.status !== "chunk_received") {
            throw new Error(`チャンク ${i+1}/${totalChunks} の処理中にエラーが発生しました: ${JSON.stringify(resJson)}`);
          }
        } else {
          // 最終チャンクの場合はレスポンスを保持
          console.log(`最終チャンク ${i+1}/${totalChunks} が送信されました`);
          finalResponse = response;
        }
      } catch (error) {
        console.error(`チャンク ${i+1}/${totalChunks} の送信中にエラーが発生:`, error);
        throw new Error(`チャンク ${i+1}/${totalChunks} の送信エラー: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    
    if (!finalResponse) {
      throw new Error("送信エラー：最終チャンクのレスポンスが取得できませんでした");
    }
    
    console.log("すべてのチャンクが正常に送信されました");
    return finalResponse;
  } catch (error) {
    console.error("チャンク送信処理でエラーが発生:", error);
    throw error;
  }
}