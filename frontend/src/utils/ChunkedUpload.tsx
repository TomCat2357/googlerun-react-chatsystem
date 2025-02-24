export async function sendChunkedRequest(chatRequest: any, token: string, destUrl: string): Promise<Response> {
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
      // 送信先URL（destUrl）をそのまま利用
      const response = await fetch(destUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (i < totalChunks - 1) {
        const resJson = await response.json();
        console.log("Chunk response:", resJson);
      } else {
        finalResponse = response;
      }
    }
    if (!finalResponse) {
      throw new Error("送信エラー：最終チャンクのレスポンスがありません");
    }
    return finalResponse;
  }
  