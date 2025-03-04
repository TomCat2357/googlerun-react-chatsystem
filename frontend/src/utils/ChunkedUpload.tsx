// frontend/src/utils/ChunkedUpload.tsx
import * as Config from "../config";

// Uint8ArrayをBase64に変換するヘルパー関数
function uint8ToBase64(data: Uint8Array): string {
  let binary = "";
  const chunkSize = 1024;
  // 大きなデータを処理する際の最適化
  for (let i = 0; i < data.byteLength; i += chunkSize) {
    const chunk = data.slice(i, Math.min(i + chunkSize, data.byteLength));
    binary += String.fromCharCode.apply(null, Array.from(chunk));
  }
  return btoa(binary);
}

export async function sendChunkedRequest(chatRequest: any, token: string, destUrl: string): Promise<Response> {
  // Configモジュールからサーバー設定を取得
  const serverConfig = Config.getServerConfig();
  // より小さなチャンクサイズを設定（バイナリデータの場合は特に重要）
  const MAX_PAYLOAD_SIZE = Math.min(serverConfig.MAX_PAYLOAD_SIZE || 500000, 250000);
  
  // 音声データかどうかを判定
  const isSpeechRequest = destUrl.includes('/speech2text');
  const isBinary = isSpeechRequest;
  
  let data: Uint8Array;
  
  // 音声リクエストの場合はそのままバイナリデータを利用
  if (isSpeechRequest && typeof chatRequest.audio_data === 'string') {
    // Base64文字列からバイナリデータへの変換
    try {
      // Base64のヘッダー部分を除去する必要がある場合
      let base64Data = chatRequest.audio_data;
      if (base64Data.includes(',')) {
        base64Data = base64Data.split(',')[1];
      }
      
      const binaryString = atob(base64Data);
      data = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        data[i] = binaryString.charCodeAt(i);
      }
    } catch (e) {
      console.error('Base64デコードエラー:', e);
      throw new Error('音声データの変換に失敗しました');
    }
  } else {
    // 通常のJSONデータ
    const jsonStr = JSON.stringify(chatRequest);
    const encoder = new TextEncoder();
    data = encoder.encode(jsonStr);
  }
  
  const totalChunks = Math.ceil(data.length / MAX_PAYLOAD_SIZE);
  
  // ユニークなチャンクIDを生成（例：タイムスタンプ＋乱数）
  const chunkId = `chunk_${Date.now().toString()}_${Math.random().toString(36).substr(2, 9)}`;
  let finalResponse: Response | null = null;

  console.log(`総データサイズ: ${data.length} バイト, 合計チャンク数: ${totalChunks}, 音声データ: ${isSpeechRequest}`);

  try {
    for (let i = 0; i < totalChunks; i++) {
      const start = i * MAX_PAYLOAD_SIZE;
      const end = Math.min(start + MAX_PAYLOAD_SIZE, data.length);
      const chunkData = data.slice(start, end);
      
      // チャンクごとに進捗を表示するためのログ
      const percentComplete = Math.round((i / totalChunks) * 100);
      console.log(`チャンク ${i+1}/${totalChunks} を送信中: ${chunkData.length} バイト (${percentComplete}% 完了)`);
      
      // 小さなチャンクに分けてBase64エンコード
      const base64Chunk = uint8ToBase64(chunkData);
      
      const payload = {
        chunked: true,
        chunkId,
        chunkIndex: i,
        totalChunks,
        chunkData: base64Chunk,
        isBinary
      };
      
      try {
        // 送信先URL（destUrl）に対してPOSTリクエスト
        const response = await fetch(destUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
          body: JSON.stringify(payload),
        });
        
        if (!response.ok) {
          // エラーレスポンスの詳細情報を取得
          try {
            const errorData = await response.json();
            console.error(`チャンク ${i+1}/${totalChunks} 処理エラー:`, errorData);
            throw new Error(`サーバーエラー: ${response.status} ${response.statusText}, 詳細: ${JSON.stringify(errorData)}`);
          } catch (jsonError) {
            throw new Error(`サーバーエラー: ${response.status} ${response.statusText}`);
          }
        }
        
        // 最終チャンク以外はレスポンスをチェック
        if (i < totalChunks - 1) {
          const resJson = await response.json();
          
          // 進捗状況を詳細に表示
          if (resJson.status === "chunk_received") {
            console.log(`チャンク ${i+1}/${totalChunks} 受信確認: ${resJson.received}/${resJson.total} (${Math.round((resJson.received/resJson.total)*100)}%)`);
          } else {
            throw new Error(`チャンク処理エラー: ${JSON.stringify(resJson)}`);
          }
        } else {
          // 最終チャンクの場合はレスポンスを保持
          console.log(`最終チャンク ${i+1}/${totalChunks} が送信されました`);
          finalResponse = response;
        }
        
        // サーバー負荷軽減のための短い遅延を追加（大量のチャンクがある場合）
        if (totalChunks > 100 && i % 10 === 0) {
          await new Promise(resolve => setTimeout(resolve, 100));
        }
      } catch (error) {
        console.error(`チャンク ${i+1}/${totalChunks} の送信中にエラー:`, error);
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