// src/components/Geocoding/GeocodingPage.tsx
import React, { useState, useEffect, useRef } from "react";
import { useToken } from "../../hooks/useToken";
import * as indexedDBUtils from "../../utils/indexedDBUtils";
import * as Config from "../../config";
import * as Encoding from "encoding-japanese";
import { MapControls } from "./MapControls";
import { imageCache } from "../../utils/imageCache";

// WebSocketメッセージタイプの定義
enum WebSocketMessageType {
  GEOCODE_REQUEST = 'GEOCODE_REQUEST',
  GEOCODE_RESULT = 'GEOCODE_RESULT',
  IMAGE_REQUEST = 'IMAGE_REQUEST',
  IMAGE_RESULT = 'IMAGE_RESULT',
  ERROR = 'ERROR',
  COMPLETE = 'COMPLETE'
}

// WebSocketメッセージインターフェース
interface WebSocketMessage {
  type: WebSocketMessageType;
  payload: any;
}

export interface GeoResult {
  query: string;
  status: string;
  formatted_address: string;
  latitude: number | null;
  longitude: number | null;
  location_type: string;
  place_id: string;
  types: string;
  error?: string;
  isCached?: boolean;
  fetchedAt?: number;
  original?: string;
  mode?: "address" | "latlng";
  satelliteImage?: string;
  streetViewImage?: string;
  // 処理状態を示すフラグ
  isProcessing?: boolean;
  imageLoading?: boolean;
}

// IndexedDB用の関数（GeocodeCacheDB）
function openCacheDB(): Promise<IDBDatabase> {
  return indexedDBUtils.openDB("GeocodeCacheDB", 1, (db) => {
    if (!db.objectStoreNames.contains("geocodeCache")) {
      db.createObjectStore("geocodeCache", { keyPath: "query" });
    }
  });
}

// キャッシュから結果を取得する関数
async function getCachedResult(query: string): Promise<GeoResult | null> {
  const db = await openCacheDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction("geocodeCache", "readonly");
    const store = transaction.objectStore("geocodeCache");
    const req = store.get(query);
    req.onsuccess = () => resolve(req.result ? req.result : null);
    req.onerror = () => reject(req.error);
  });
}

// キャッシュに結果を保存する関数
async function setCachedResult(result: GeoResult): Promise<void> {
  const db = await openCacheDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction("geocodeCache", "readwrite");
    const store = transaction.objectStore("geocodeCache");
    const req = store.put(result);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

const GeocodingPage = () => {
  // 入力・結果関連のstate
  const [inputText, setInputText] = useState("");
  const [lineCount, setLineCount] = useState(0);
  const [isSending, setIsSending] = useState(false);
  const [results, setResults] = useState<GeoResult[]>([]);
  const [inputMode, setInputMode] = useState<"address" | "latlng">("address");
  const [csvEncoding, setCsvEncoding] = useState<"utf8" | "shift-jis">("shift-jis");
  const [progress, setProgress] = useState(0); // 処理進捗率
  
  // WebSocket関連のstate
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const socketRef = useRef<WebSocket | null>(null);
  
  // 地図表示用のstate
  const [showSatellite, setShowSatellite] = useState(false);
  const [showStreetView, setShowStreetView] = useState(false);
  const [satelliteZoom, setSatelliteZoom] = useState(18);
  const [streetViewHeading, setStreetViewHeading] = useState(0);
  const [streetViewPitch, setStreetViewPitch] = useState(0);
  const [streetViewFov, setStreetViewFov] = useState(90);
  const [isLoadingImages, setIsLoadingImages] = useState(false);
  const [streetViewNoHeading, setStreetViewNoHeading] = useState(true);

  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;
  
  // WebSocket接続を確立
  useEffect(() => {
    // ページロード時にWebSocket接続を試みる
    if (token) {
      connectWebSocket();
    }
    
    // クリーンアップ関数
    return () => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [token]); // tokenが更新されたら再接続
  
  // WebSocketの接続を確立する関数
  const connectWebSocket = () => {
    // 既存の接続がある場合は閉じる
    if (socketRef.current) {
      if (socketRef.current.readyState === WebSocket.OPEN || 
          socketRef.current.readyState === WebSocket.CONNECTING) {
        socketRef.current.close();
      }
      socketRef.current = null;
    }
    
    // WebSocketのURLを作成（相対パスを使用）
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // 現在のホスト名を使用
    const host = window.location.host; 
    const wsUrl = `${wsProtocol}//${host}/ws/geocoding`;
    
    console.log(`WebSocket接続を試みます: ${wsUrl}`);
    
    try {
      socketRef.current = new WebSocket(wsUrl);
      
      socketRef.current.onopen = () => {
        console.log('WebSocket接続が確立されました');
        setIsConnected(true);
        setConnectionError("");
        
        // 認証メッセージを送信
        if (socketRef.current && token) {
          console.log('認証メッセージを送信します');
          socketRef.current.send(JSON.stringify({
            type: 'AUTH',
            payload: { token }
          }));
        }
      };
      
      socketRef.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          handleWebSocketMessage(message);
        } catch (error) {
          console.error('WebSocketメッセージの解析エラー:', error);
        }
      };
      
      socketRef.current.onerror = (error) => {
        console.error('WebSocketエラー:', error);
        setConnectionError("WebSocket接続でエラーが発生しました。");
      };
      
      socketRef.current.onclose = (event) => {
        console.log('WebSocket接続が閉じられました:', event.code, event.reason);
        setIsConnected(false);
        
        // 異常終了の場合、5秒後に再接続を試みる
        if (!event.wasClean) {
          setTimeout(() => {
            connectWebSocket();
          }, 5000);
        }
      };
    } catch (error) {
      console.error('WebSocket接続の確立に失敗しました:', error);
      setConnectionError("WebSocket接続の確立に失敗しました。");
    }
  };
  
  // WebSocketメッセージを処理する関数
  const handleWebSocketMessage = (message: WebSocketMessage) => {
    switch (message.type) {
      case WebSocketMessageType.GEOCODE_RESULT:
        handleGeocodeResult(message.payload);
        break;
      case WebSocketMessageType.IMAGE_RESULT:
        handleImageResult(message.payload);
        break;
      case WebSocketMessageType.ERROR:
        handleError(message.payload);
        break;
      case WebSocketMessageType.COMPLETE:
        handleComplete(message.payload);
        break;
      default:
        console.warn('不明なメッセージタイプ:', message.type);
    }
  };
  
  // ジオコーディング結果を処理する関数
  const handleGeocodeResult = (payload: any) => {
    const { index, result } = payload;
    
    setResults(prevResults => {
      const newResults = [...prevResults];
      // キャッシュデータを保存
      if (!result.isCached) {
        setCachedResult(result).catch(err => console.error("キャッシュ保存エラー:", err));
      }
      
      // 画像のロード状態を設定
      if ((showSatellite || showStreetView) && result.latitude !== null && result.longitude !== null) {
        result.imageLoading = true;
      }
      
      // 既存の結果を更新または新しい結果を追加
      if (index < newResults.length) {
        newResults[index] = { ...newResults[index], ...result, isProcessing: false };
      } else {
        newResults.push({ ...result, isProcessing: false });
      }
      
      return newResults;
    });
    
    // 進捗状況の更新
    setProgress(payload.progress || 0);
  };
  
  // 画像結果を処理する関数
  const handleImageResult = (payload: any) => {
    const { index, satelliteImage, streetViewImage } = payload;
    
    setResults(prevResults => {
      const newResults = [...prevResults];
      if (index < newResults.length) {
        // イメージデータを更新し、ロード状態を解除
        newResults[index] = {
          ...newResults[index],
          satelliteImage: satelliteImage || newResults[index].satelliteImage,
          streetViewImage: streetViewImage || newResults[index].streetViewImage,
          imageLoading: false
        };
      }
      return newResults;
    });
    
    // 進捗状況の更新
    setProgress(payload.progress || 0);
  };
  
  // エラーを処理する関数
  const handleError = (payload: any) => {
    console.error('WebSocketエラー:', payload);
    alert(`エラーが発生しました: ${payload.message || '不明なエラー'}`);
    setIsSending(false);
  };
  
  // 処理完了を処理する関数
  const handleComplete = (payload: any) => {
    console.log('処理が完了しました:', payload);
    setIsSending(false);
    setProgress(100);
  };
  
  // WebSocketを通じてジオコーディングリクエストを送信する関数
  const sendGeocodeRequest = (lines: string[]) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      alert('WebSocket接続が確立されていません。再接続してください。');
      connectWebSocket();
      return;
    }
    
    const request: WebSocketMessage = {
      type: WebSocketMessageType.GEOCODE_REQUEST,
      payload: {
        mode: inputMode,
        lines,
        options: {
          showSatellite,
          showStreetView,
          satelliteZoom,
          streetViewHeading: streetViewNoHeading ? null : streetViewHeading,
          streetViewPitch,
          streetViewFov
        }
      }
    };
    
    socketRef.current.send(JSON.stringify(request));
  };

  // テキストエリアの内容変更時処理
  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value;
    setInputText(text);
    let validLines: string[] = [];
    if (inputMode === "address") {
      validLines = text.split("\n").filter((line) => line.trim().length > 0);
    } else {
      const pattern = /^-?\d+(\.\d+)?,-?\d+(\.\d+)?$/;
      validLines = text
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => {
          const noSpace = line.replace(/\s/g, "");
          return pattern.test(noSpace);
        });
    }
    setLineCount(validLines.length);
  };

  // CSVダウンロード処理
  const handleDownloadCSV = () => {
    if (results.length === 0) return;
    const header = [
      "No.",
      "クエリー",
      "ステータス",
      "Formatted Address",
      "Latitude",
      "Longitude",
      "Location Type",
      "Place ID",
      "Types",
      "エラー",
      "データ取得日時",
      "キャッシュ利用",
    ];
    const rows = results.map((result, index) => [
      index + 1,
      result.query,
      result.status,
      result.formatted_address,
      result.latitude ?? "",
      result.longitude ?? "",
      result.location_type,
      result.place_id,
      result.types,
      result.error || "",
      result.fetchedAt
        ? new Date(result.fetchedAt).toLocaleString("ja-JP")
        : "",
      result.isCached ? "キャッシュ" : "API取得",
    ]);

    const csvContent = [header, ...rows]
      .map((row) =>
        row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")
      )
      .join("\n");

    let blob: Blob;
    if (csvEncoding === "utf8") {
      blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });
    } else {
      const codeArray = Encoding.stringToCode(csvContent);
      const sjisArray = Encoding.convert(codeArray, "SJIS");
      blob = new Blob([new Uint8Array(sjisArray)], {
        type: "text/csv;charset=shift_jis",
      });
    }

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "geocoding_results.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  // 送信処理（WebSocketを使用）
  const handleSendLines = async () => {
    const allLines = inputText
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    
    if (allLines.length === 0) return;

    // 画像表示の有無に応じた上限件数を設定
    const maxBatchSize =
      showSatellite || showStreetView
        ? Config.getServerConfig().GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE
        : Config.getServerConfig().GEOCODING_NO_IMAGE_MAX_BATCH_SIZE;

    if (allLines.length > maxBatchSize) {
      alert(
        `入力された件数は${allLines.length}件ですが、1回の送信で取得可能な上限は${maxBatchSize}件です。\n` +
          `件数を減らして再度送信してください。`
      );
      return;
    }

    setIsSending(true);
    setProgress(0);
    
    // WebSocketが未接続の場合は再接続を試みる
    if (!isConnected) {
      console.log('WebSocketが未接続です。接続を試みます。');
      connectWebSocket();
      
      // 接続完了を待つ（最大5秒）
      let attempts = 0;
      while (!isConnected && attempts < 10) {
        await new Promise(resolve => setTimeout(resolve, 500));
        attempts++;
      }
      
      if (!isConnected) {
        alert('WebSocket接続を確立できませんでした。ページをリロードして再試行してください。');
        setIsSending(false);
        return;
      }
    }
    
    // WebSocketが接続されていることを再確認
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      alert('WebSocket接続が確立されていません。再接続してください。');
      setIsSending(false);
      return;
    }
    
    // 初期結果配列をセットアップ（処理中の表示用）
    const initialResults = allLines.map(line => ({
      query: line,
      status: "PROCESSING",
      formatted_address: "",
      latitude: null,
      longitude: null,
      location_type: "",
      place_id: "",
      types: "",
      isProcessing: true,
      mode: inputMode as "address" | "latlng"
    }));
    
    setResults(initialResults);
    
    // WebSocketを通じてリクエストを送信
    sendGeocodeRequest(allLines);
  };

  // 結果クリアボタンのハンドラー
  const handleClearResults = () => {
    setResults([]);
    setProgress(0);
  };

  // テキストボックスクリアボタンのハンドラー
  const handleClearText = () => {
    setInputText("");
    setLineCount(0);
  };
  
  // 再接続ボタンのハンドラー
  const handleReconnect = () => {
    connectWebSocket();
  };

  return (
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4 text-gray-100">
        ジオコーディング
      </h1>
      
      {/* WebSocket接続状態 */}
      <div className="mb-4 flex items-center">
        <div className={`w-3 h-3 rounded-full mr-2 ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
        <span className="text-gray-200 mr-4">
          {isConnected ? 'WebSocket接続済み' : 'WebSocket未接続'}
        </span>
        {!isConnected && (
          <button
            onClick={handleReconnect}
            className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            再接続
          </button>
        )}
        {connectionError && (
          <span className="text-red-400 ml-4">{connectionError}</span>
        )}
      </div>

      {/* 地図コントロール（結果が表示されていても操作可能） */}
      <MapControls
        showSatellite={showSatellite}
        showStreetView={showStreetView}
        onShowSatelliteChange={setShowSatellite}
        onShowStreetViewChange={setShowStreetView}
        satelliteZoom={satelliteZoom}
        onSatelliteZoomChange={setSatelliteZoom}
        streetViewHeading={streetViewHeading}
        onStreetViewHeadingChange={setStreetViewHeading}
        streetViewPitch={streetViewPitch}
        onStreetViewPitchChange={setStreetViewPitch}
        streetViewFov={streetViewFov}
        onStreetViewFovChange={setStreetViewFov}
        streetViewNoHeading={streetViewNoHeading}
        onStreetViewNoHeadingChange={setStreetViewNoHeading}
      />

      {/* 入力モード選択 */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-200 mb-2">
          入力モード
        </label>
        <div>
          <label className="mr-4 text-gray-200">
            <input
              type="radio"
              name="inputMode"
              value="address"
              checked={inputMode === "address"}
              onChange={() => setInputMode("address")}
            />{" "}
            住所等⇒緯度経度
          </label>
          <label className="text-gray-200">
            <input
              type="radio"
              name="inputMode"
              value="latlng"
              checked={inputMode === "latlng"}
              onChange={() => setInputMode("latlng")}
            />{" "}
            緯度経度⇒住所
          </label>
        </div>
      </div>

      {/* テキスト入力エリアとテキストクリアボタンを同一行に配置 */}
      <div className="mb-4">
        <div className="mb-2 flex justify-between items-center">
          <label className="text-sm font-medium text-gray-200">
            {inputMode === "address"
              ? "1行毎に住所や施設名等の「キーワード」を入力すると、緯度経度を返します。"
              : "1行毎に「緯度,経度」を入力すると、住所を返します。"}
          </label>
          <button
            onClick={handleClearText}
            disabled={inputText.trim() === ""}
            className="px-4 py-2 bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:opacity-50"
          >
            テキストボックスをクリア
          </button>
        </div>
        <textarea
          value={inputText}
          onChange={handleTextChange}
          className="w-full h-64 p-2 bg-gray-800 text-gray-100 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500"
          placeholder={
            inputMode === "address"
              ? "例：札幌市役所"
              : "例：35.6812996,139.7670658"
          }
        />
      </div>

      {/* アクションボタン（有効行数/送信/CSVダウンロード/CSVエンコーディングラジオボタン/結果クリア） */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-gray-200">
          有効な行数: <strong>{lineCount}</strong>
        </div>
        <div className="flex items-center space-x-4">
          <button
            onClick={handleSendLines}
            disabled={isSending || !isConnected || lineCount === 0}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {isSending ? "処理中..." : "送信"}
          </button>
          <button
            onClick={handleDownloadCSV}
            disabled={isSending || results.length === 0}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            CSVダウンロード
          </button>
          <div className="flex items-center space-x-2">
            <label className="text-gray-200">
              <input
                type="radio"
                name="csvEncoding"
                value="utf8"
                checked={csvEncoding === "utf8"}
                onChange={() => setCsvEncoding("utf8")}
              />{" "}
              UTF-8
            </label>
            <label className="text-gray-200">
              <input
                type="radio"
                name="csvEncoding"
                value="shift-jis"
                checked={csvEncoding === "shift-jis"}
                onChange={() => setCsvEncoding("shift-jis")}
              />{" "}
              Shift-JIS
            </label>
          </div>
          <button
            onClick={handleClearResults}
            disabled={results.length === 0}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
          >
            結果をクリア
          </button>
        </div>
      </div>
      
      {/* 進捗バー */}
      {isSending && (
        <div className="w-full bg-gray-700 rounded-full h-4 mb-4">
          <div
            className="bg-blue-600 h-4 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          ></div>
          <div className="text-center text-gray-200 text-sm mt-1">
            {Math.round(progress)}% 完了
          </div>
        </div>
      )}

      {/* 結果テーブル */}
      {results.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-gray-200">
            <thead>
              <tr className="bg-gray-700">
                <th className="px-4 py-2">No.</th>
                <th className="px-4 py-2">クエリー</th>
                <th className="px-4 py-2">状態</th>
                {inputMode === "address" ? (
                  <>
                    <th className="px-4 py-2">緯度</th>
                    <th className="px-4 py-2">経度</th>
                  </>
                ) : (
                  <th className="px-4 py-2">住所</th>
                )}
                {showSatellite && <th className="px-4 py-2">衛星写真</th>}
                {showStreetView && (
                  <th className="px-4 py-2">ストリートビュー</th>
                )}
              </tr>
            </thead>
            <tbody>
              {results.map((result, index) => (
                <tr key={index} className="border-b border-gray-700">
                  <td className="px-4 py-2">{index + 1}</td>
                  <td className="px-4 py-2">
                    {result.original || result.query}
                  </td>
                  <td className="px-4 py-2">
                    {result.isProcessing ? (
                      <span className="inline-block animate-pulse bg-yellow-500 text-gray-900 px-2 py-1 rounded">処理中...</span>
                    ) : result.imageLoading ? (
                      <span className="inline-block animate-pulse bg-blue-500 text-white px-2 py-1 rounded">画像取得中...</span>
                    ) : result.error ? (
                      <span className="inline-block bg-red-500 text-white px-2 py-1 rounded">エラー</span>
                    ) : (
                      <span className="inline-block bg-green-500 text-white px-2 py-1 rounded">完了</span>
                    )}
                  </td>
                  {inputMode === "address" ? (
                    <>
                      <td className="px-4 py-2">
                        {result.latitude !== null
                          ? result.latitude.toFixed(7)
                          : "-"}
                      </td>
                      <td className="px-4 py-2">
                        {result.longitude !== null
                          ? result.longitude.toFixed(7)
                          : "-"}
                      </td>
                    </>
                  ) : (
                    <td className="px-4 py-2">
                      {result.formatted_address || result.error || "-"}
                    </td>
                  )}
                  {showSatellite && (
                    <td className="px-4 py-2">
                      {result.satelliteImage ? (
                        <img
                          src={result.satelliteImage}
                          alt="衛星写真"
                          className="max-w-xs"
                        />
                      ) : result.isProcessing || result.imageLoading ? (
                        <div className="w-64 h-64 bg-gray-700 animate-pulse flex items-center justify-center">
                          <span className="text-gray-400">読み込み中...</span>
                        </div>
                      ) : null}
                    </td>
                  )}
                  {showStreetView && (
                    <td className="px-4 py-2">
                      {result.streetViewImage ? (
                        <img
                          src={result.streetViewImage}
                          alt="ストリートビュー"
                          className="max-w-xs"
                        />
                      ) : result.isProcessing || result.imageLoading ? (
                        <div className="w-64 h-64 bg-gray-700 animate-pulse flex items-center justify-center">
                          <span className="text-gray-400">読み込み中...</span>
                        </div>
                      ) : null}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default GeocodingPage;