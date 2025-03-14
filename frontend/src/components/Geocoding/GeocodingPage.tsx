// src/components/Geocoding/GeocodingPage.tsx
import React, { useState, useRef } from "react";
import { useToken } from "../../hooks/useToken";
import * as indexedDBUtils from "../../utils/indexedDBUtils";
import * as Config from "../../config";
import * as Encoding from "encoding-japanese";
import { MapControls } from "./MapControls";
import { imageCache } from "../../utils/imageCache";
import generateId from "../../utils/idGenerator";

// メッセージタイプの定義（APIレスポンスと互換性を保つ）
enum MessageType {
  GEOCODE_RESULT = "GEOCODE_RESULT",
  IMAGE_RESULT = "IMAGE_RESULT",
  ERROR = "ERROR",
  COMPLETE = "COMPLETE",
}

// メッセージインターフェース
interface Message {
  type: MessageType;
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

// TTL取得用の定数
const GOOGLE_MAPS_API_CACHE_TTL = Number(
  Config.getServerConfig().GOOGLE_MAPS_API_CACHE_TTL || 86400000
);

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
    req.onsuccess = () => {
      const result = req.result ? req.result : null;

      // TTLチェック: TTL内のキャッシュデータのみを返す
      if (result && result.fetchedAt) {
        const now = Date.now();
        const age = now - result.fetchedAt;
        if (age < GOOGLE_MAPS_API_CACHE_TTL) {
          resolve(result);
        } else {
          console.log(`キャッシュの有効期限切れ: ${query}, 経過時間=${age}ms`);
          resolve(null);
        }
      } else {
        resolve(null);
      }
    };
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

// 画像キャッシュのヘルパー関数
function getCachedImage(
  lat: number,
  lng: number,
  options: any,
  type: "satellite" | "streetview"
): string | undefined {
  if (!lat || !lng) return undefined;

  if (type === "satellite") {
    return imageCache.get({
      type: "satellite",
      lat,
      lng,
      zoom: options.satelliteZoom,
    });
  } else {
    return imageCache.get({
      type: "streetview",
      lat,
      lng,
      heading: options.streetViewNoHeading ? null : options.streetViewHeading,
      pitch: options.streetViewPitch,
      fov: options.streetViewFov,
    });
  }
}

const GeocodingPage = () => {
  // 入力・結果関連のstate
  const [inputText, setInputText] = useState("");
  const [lineCount, setLineCount] = useState(0);
  const [isSending, setIsSending] = useState(false);
  const [results, setResults] = useState<GeoResult[]>([]);
  const [inputMode, setInputMode] = useState<"address" | "latlng">("address");
  const [csvEncoding, setCsvEncoding] = useState<"utf8" | "shift-jis">("shift-jis");
  const [progress, setProgress] = useState(0);

  // エラー関連のstate
  const [fetchError, setFetchError] = useState("");
  
  // 地図表示用のstate
  const [showSatellite, setShowSatellite] = useState(false);
  const [showStreetView, setShowStreetView] = useState(false);
  const [satelliteZoom, setSatelliteZoom] = useState(18);
  const [streetViewHeading, setStreetViewHeading] = useState(0);
  const [streetViewPitch, setStreetViewPitch] = useState(0);
  const [streetViewFov, setStreetViewFov] = useState(90);
  const [streetViewNoHeading, setStreetViewNoHeading] = useState(true);

  const token = useToken();

  // リクエストの中止用コントローラー
  const abortControllerRef = useRef<AbortController | null>(null);

  // メッセージ処理関数
  const handleMessage = (message: Message) => {
    console.log(`メッセージ処理: ${message.type}`);
    switch (message.type) {
      case MessageType.GEOCODE_RESULT:
        handleGeocodeResult(message.payload);
        break;
      case MessageType.IMAGE_RESULT:
        handleImageResult(message.payload);
        break;
      case MessageType.ERROR:
        handleError(message.payload);
        break;
      case MessageType.COMPLETE:
        handleComplete(message.payload);
        break;
      default:
        console.warn("不明なメッセージタイプ:", message.type);
    }
  };

  // ジオコーディング結果を処理する関数
  const handleGeocodeResult = (payload: any) => {
    console.log(`ジオコーディング結果受信: index=${payload.index}`);
    const { index, result } = payload;

    setResults((prevResults) => {
      const newResults = [...prevResults];
      // キャッシュデータを保存
      if (!result.isCached) {
        setCachedResult(result).catch((err) =>
          console.error("キャッシュ保存エラー:", err)
        );
      }

      // 画像のロード状態を設定
      if (
        (showSatellite || showStreetView) &&
        result.latitude !== null &&
        result.longitude !== null
      ) {
        result.imageLoading = true;
      }

      // 既存の結果を更新または新しい結果を追加
      if (index < newResults.length) {
        newResults[index] = {
          ...newResults[index],
          ...result,
          isProcessing: false,
        };
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
    console.log(`画像結果受信: index=${payload.index}`);
    const { index, satelliteImage, streetViewImage } = payload;

    setResults((prevResults) => {
      const newResults = [...prevResults];
      if (index < newResults.length) {
        const result = newResults[index];

        // イメージデータを更新し、ロード状態を解除
        newResults[index] = {
          ...result,
          satelliteImage: satelliteImage || result.satelliteImage,
          streetViewImage: streetViewImage || result.streetViewImage,
          imageLoading: false,
        };

        // 衛星画像をキャッシュ
        if (
          satelliteImage &&
          result.latitude !== null &&
          result.longitude !== null
        ) {
          imageCache.set(
            {
              type: "satellite",
              lat: result.latitude,
              lng: result.longitude,
              zoom: satelliteZoom,
            },
            satelliteImage
          );
        }

        // ストリートビュー画像をキャッシュ
        if (
          streetViewImage &&
          result.latitude !== null &&
          result.longitude !== null
        ) {
          imageCache.set(
            {
              type: "streetview",
              lat: result.latitude,
              lng: result.longitude,
              heading: streetViewNoHeading ? null : streetViewHeading,
              pitch: streetViewPitch,
              fov: streetViewFov,
            },
            streetViewImage
          );
        }
      }
      return newResults;
    });

    // 進捗状況の更新
    setProgress(payload.progress || 0);
  };

  // エラーを処理する関数
  const handleError = (payload: any) => {
    console.error("エラー:", payload);
    alert(`エラーが発生しました: ${payload.message || "不明なエラー"}`);
    setIsSending(false);
    setFetchError(payload.message || "不明なエラー");
  };

  // 処理完了を処理する関数
  const handleComplete = (payload: any) => {
    console.log("処理が完了しました:", payload);
    setIsSending(false);
    setProgress(100);
  };

  // HTTPリクエストを使用してジオコーディングを行う
  const fetchGeocodingResults = async (linesToSend: string[], queryToIndexMap: Map<string, number[]>) => {
    if (!token) {
      alert("認証トークンが取得できません。再ログインしてください。");
      return false;
    }

    try {
      // 重複排除して一意のクエリだけを送信
      const uniqueLines = linesToSend;

      // リクエストの設定
      const options = {
        showSatellite,
        showStreetView,
        satelliteZoom,
        streetViewHeading: streetViewNoHeading ? null : streetViewHeading,
        streetViewPitch,
        streetViewFov,
      };

      // APIエンドポイントのURL
      const endpoint = 
        process.env.NODE_ENV === "development" 
          ? "http://localhost:8080/backend/geocoding"
          : "/backend/geocoding";

      // 中止用のコントローラーを作成
      abortControllerRef.current = new AbortController();
      
      // リクエストボディ
      const body = JSON.stringify({
        mode: inputMode,
        lines: uniqueLines,
        options,
      });

      // fetchリクエストを開始
      const response = await fetch(endpoint, {
        method: "POST",
        headers:{
          "Content-Type" : "application/json",
          "X-Request-Id" : generateId(),
          "Authorization" : `Bearer ${token}`
        },
        body,
        signal: abortControllerRef.current.signal,
      });

      // エラーチェック
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`APIエラー (${response.status}): ${errorText}`);
      }

      // StreamingResponseを読み込む
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("レスポンスボディを読み取れません");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      // ストリームを読み込む
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // バッファに追加
        buffer += decoder.decode(value, { stream: true });

        // 完全なJSONメッセージを処理
        let newlineIndex;
        while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
          const messageText = buffer.slice(0, newlineIndex);
          buffer = buffer.slice(newlineIndex + 1);

          try {
            const message = JSON.parse(messageText);
            
            // オリジナルインデックスの変換処理
            if (message.type === MessageType.GEOCODE_RESULT || message.type === MessageType.IMAGE_RESULT) {
              const serverIndex = message.payload.index;
              const query = uniqueLines[serverIndex];
              const indices = queryToIndexMap.get(query) || [];
              
              // 各インデックスで結果を更新
              indices.forEach((idx) => {
                const modifiedPayload = {
                  ...message.payload,
                  index: idx,
                };
                
                // 適切なハンドラーを呼び出す
                handleMessage({
                  type: message.type,
                  payload: modifiedPayload,
                });
              });
            } else {
              // その他のメッセージタイプはそのまま処理
              handleMessage(message);
            }
          } catch (e) {
            console.error("JSONパースエラー:", e, messageText);
          }
        }
      }

      return true;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        console.log("リクエストがキャンセルされました");
      } else {
        console.error("ジオコーディングリクエストエラー:", error);
        const errorMessage = error instanceof Error ? error.message : "不明なエラーが発生しました";
        setFetchError(errorMessage);
        alert(`エラーが発生しました: ${errorMessage}`);
      }
      return false;
    }
  };

  // 送信処理
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
    setFetchError("");

    // 初期結果配列とクエリーマッピングの準備
    const initialResults: GeoResult[] = [];

    // 重複管理: クエリー -> インデックスリストのマップ
    const queryToIndexMap = new Map<string, number[]>();

    // 先にキャッシュチェックして初期結果を設定
    const timestamp = Date.now();
    const linesToSend: string[] = [];

    // 各行についてキャッシュをチェック
    for (let i = 0; i < allLines.length; i++) {
      const line = allLines[i];

      // キャッシュチェック
      const cachedResult = await getCachedResult(line);

      if (cachedResult && cachedResult.fetchedAt) {
        // キャッシュがある場合は、それを使用
        console.log(
          `キャッシュ利用: ${line}, 取得日時=${new Date(
            cachedResult.fetchedAt
          ).toLocaleString()}`
        );
        initialResults.push({
          ...cachedResult,
          isCached: true,
          imageLoading: false,
        });

        // 画像キャッシュをチェック
        if (
          (showSatellite || showStreetView) &&
          cachedResult.latitude !== null &&
          cachedResult.longitude !== null
        ) {
          const options = {
            satelliteZoom,
            streetViewHeading: streetViewNoHeading ? null : streetViewHeading,
            streetViewPitch,
            streetViewFov,
            streetViewNoHeading,
          };

          let needImageRequest = false;

          // 衛星画像キャッシュをチェック
          if (showSatellite) {
            const cachedSatelliteImage = getCachedImage(
              cachedResult.latitude,
              cachedResult.longitude,
              options,
              "satellite"
            );

            if (cachedSatelliteImage) {
              initialResults[i].satelliteImage = cachedSatelliteImage;
            } else {
              needImageRequest = true;
            }
          }

          // ストリートビュー画像キャッシュをチェック
          if (showStreetView) {
            const cachedStreetViewImage = getCachedImage(
              cachedResult.latitude,
              cachedResult.longitude,
              options,
              "streetview"
            );

            if (cachedStreetViewImage) {
              initialResults[i].streetViewImage = cachedStreetViewImage;
            } else {
              needImageRequest = true;
            }
          }

          // 画像リクエストが必要な場合のみ imageLoading フラグを設定
          if (needImageRequest) {
            initialResults[i].imageLoading = true;

            // クエリーマッピングに追加（画像だけを取得するため）
            if (!queryToIndexMap.has(line)) {
              queryToIndexMap.set(line, [i]);
              linesToSend.push(line);
            } else {
              queryToIndexMap.get(line)?.push(i);
            }
          }
        }
      } else {
        // キャッシュがない場合は、初期状態を設定
        initialResults.push({
          query: line,
          status: "PROCESSING",
          formatted_address: "",
          latitude: null,
          longitude: null,
          location_type: "",
          place_id: "",
          types: "",
          isProcessing: true,
          mode: inputMode as "address" | "latlng",
          fetchedAt: timestamp,
        });

        // クエリーマッピングに追加
        if (!queryToIndexMap.has(line)) {
          queryToIndexMap.set(line, [i]);
          linesToSend.push(line);
        } else {
          queryToIndexMap.get(line)?.push(i);
        }
      }
    }

    // 初期結果を設定
    setResults(initialResults);

    // サーバーに送信するクエリがある場合のみ処理
    if (linesToSend.length > 0) {
      console.log(`重複排除後のクエリ数: ${linesToSend.length}件`);

      // HTTPリクエストを実行
      const success = await fetchGeocodingResults(linesToSend, queryToIndexMap);
      if (!success) {
        setIsSending(false);
      }
    } else {
      // すべてキャッシュヒットの場合は即時完了
      console.log(
        "すべてキャッシュから取得済み。APIリクエストは不要です。"
      );
      // すべての結果で imageLoading フラグを確実に false に設定
      setResults(
        initialResults.map((result) => ({
          ...result,
          imageLoading: false,
        }))
      );
      setIsSending(false);
      setProgress(100);
    }
  };

  // 処理中断ハンドラー
  const handleCancelRequest = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsSending(false);
    }
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

  return (
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4 text-gray-100">
        ジオコーディング
      </h1>

      {/* エラーメッセージの表示 */}
      {fetchError && (
        <div className="mb-4">
          <span className="text-red-400">{fetchError}</span>
        </div>
      )}

      {/* 地図コントロール */}
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

      {/* テキスト入力エリア */}
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

      {/* アクションボタン */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-gray-200">
          有効な行数: <strong>{lineCount}</strong>
        </div>
        <div className="flex items-center space-x-4">
          {/* 送信ボタン（または中止ボタン） */}
          {isSending ? (
            <button
              onClick={handleCancelRequest}
              className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
            >
              中止
            </button>
          ) : (
            <button
              onClick={handleSendLines}
              disabled={lineCount === 0}
              className={`px-4 py-2 text-white rounded transition-colors duration-200 ${
                lineCount === 0
                  ? "bg-blue-400 cursor-not-allowed opacity-50"
                  : "bg-blue-600 hover:bg-blue-700"
              }`}
            >
              送信
            </button>
          )}
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
                      <span className="inline-block animate-pulse bg-yellow-500 text-gray-900 px-2 py-1 rounded">
                        処理中...
                      </span>
                    ) : result.imageLoading ? (
                      <span className="inline-block animate-pulse bg-blue-500 text-white px-2 py-1 rounded">
                        画像取得中...
                      </span>
                    ) : result.error ? (
                      <span className="inline-block bg-red-500 text-white px-2 py-1 rounded">
                        エラー
                      </span>
                    ) : (
                      <span className="inline-block bg-green-500 text-white px-2 py-1 rounded">
                        完了
                        {result.isCached && " (キャッシュ)"}
                      </span>
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