// geocodingpage.tsx
import React, { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";
// encoding-japaneseライブラリをインポート
import * as Encoding from "encoding-japanese";

// キャッシュTTL（秒）を環境変数から取得（例：3600秒 = 1時間）
const CACHE_TTL = Number(import.meta.env.VITE_GOOGLE_MAPS_API_CACHE_TTL) || 3600;
const CACHE_TTL_MS = CACHE_TTL * 1000;

interface GeoResult {
  query: string;
  status: string;
  formatted_address: string;
  latitude: number | null;
  longitude: number | null;
  location_type: string;
  place_id: string;
  types: string;
  error?: string;
  // 追加：キャッシュから取得したかどうか（true: キャッシュ, false: 新規取得）
  isCached?: boolean;
  // 追加：データ取得日時（UNIXミリ秒）
  fetchedAt?: number;
}

// IndexedDB用の関数
function openCacheDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("GeocodeCacheDB", 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("geocodeCache")) {
        db.createObjectStore("geocodeCache", { keyPath: "query" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function getCachedResult(query: string): Promise<{ result: GeoResult; timestamp: number } | null> {
  const db = await openCacheDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction("geocodeCache", "readonly");
    const store = transaction.objectStore("geocodeCache");
    const req = store.get(query);
    req.onsuccess = () => resolve(req.result || null);
    req.onerror = () => reject(req.error);
  });
}

async function setCachedResult(query: string, result: GeoResult): Promise<void> {
  const db = await openCacheDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction("geocodeCache", "readwrite");
    const store = transaction.objectStore("geocodeCache");
    const data = { query, result, timestamp: Date.now() };
    const req = store.put(data);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

const GeocodingPage = () => {
  const [inputText, setInputText] = useState("");
  const [lineCount, setLineCount] = useState(0);
  const [isSending, setIsSending] = useState(false);
  // サーバから取得した詳細な結果を保持する
  const [results, setResults] = useState<GeoResult[]>([]);
  const [token, setToken] = useState<string>("");

  const { currentUser } = useAuth();
  const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL;

  useEffect(() => {
    if (currentUser) {
      currentUser
        .getIdToken()
        .then((t) => setToken(t))
        .catch((err) => console.error("トークン取得エラー:", err));
    }
  }, [currentUser]);

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value;
    setInputText(text);
    const validLines = text.split("\n").filter((line) => line.trim().length > 0);
    setLineCount(validLines.length);
  };

  // サーバから詳細なジオコーディング結果を取得し、キャッシュを利用する
  const handleSendLines = async () => {
    const validLines = inputText.split("\n").filter((line) => line.trim().length > 0);
    if (validLines.length === 0) return;

    const confirmed = window.confirm(`クエリー数は${validLines.length}件です。実行しますか？`);
    if (!confirmed) return;

    setIsSending(true);

    try {
      const now = Date.now();
      // 各行ごとにキャッシュチェック（ユニーク処理は行わない）
      const cachedResults: { [query: string]: GeoResult } = {};
      const queriesToFetch: string[] = [];

      await Promise.all(
        validLines.map(async (line) => {
          const query = line.trim();
          try {
            const cached = await getCachedResult(query);
            if (cached && now - cached.timestamp < CACHE_TTL_MS) {
              // キャッシュから取得した結果にはキャッシュフラグと取得日時を付加
              cachedResults[query] = { ...cached.result, isCached: true, fetchedAt: cached.timestamp };
            } else {
              queriesToFetch.push(query);
            }
          } catch (error) {
            queriesToFetch.push(query);
          }
        })
      );

      const fetchedResults: { [query: string]: GeoResult } = {};
      if (queriesToFetch.length > 0) {
        const response = await fetch(`${API_BASE_URL}/backend/query2coordinates`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ lines: queriesToFetch }),
        });
        if (!response.ok) {
          throw new Error("サーバーからエラーが返されました");
        }
        const data = await response.json();
        // サーバ側は入力行順（重複含む）に結果を返す想定
        queriesToFetch.forEach((query, index) => {
          const fetchedAt = Date.now();
          // API取得結果にはキャッシュフラグ（false）と取得日時を付加
          fetchedResults[query] = { ...data.results[index], isCached: false, fetchedAt };
          // キャッシュに保存（非同期）
          setCachedResult(query, data.results[index]).catch((err) =>
            console.error("キャッシュ保存エラー:", err)
          );
        });
      }

      // キャッシュ済みおよび新規取得分をマージ
      const mergedResults: { [query: string]: GeoResult } = { ...cachedResults, ...fetchedResults };

      // 入力行順に結果を再構築（重複している場合は同じ結果が複数回展開されます）
      const finalResults: GeoResult[] = validLines.map((line) => mergedResults[line.trim()]);

      console.log("送信成功", finalResults);
      setResults(finalResults);
    } catch (error) {
      console.error("送信エラー", error);
    } finally {
      setIsSending(false);
    }
  };

  // フロントエンド側で保持している詳細情報をもとにCSVファイルを生成してShift_JISでダウンロード
  // ※CSVにはデータ取得日時とキャッシュ利用状況も含める（画面表示はしません）
  const handleDownloadCSV = () => {
    if (results.length === 0) return;
    // ヘッダー行に「データ取得日時」と「キャッシュ利用」を追加
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
    // 各行のデータ
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
      result.fetchedAt ? new Date(result.fetchedAt).toLocaleString("ja-JP") : "",
      result.isCached ? "キャッシュ" : "API取得",
    ]);

    // CSV用の文字列生成（各項目をダブルクオートで囲み、カンマ区切り）
    const csvContent =
      [header, ...rows]
        .map((row) =>
          row
            .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
            .join(",")
        )
        .join("\n");

    // 文字列をコード配列に変換し、その後SJISに変換する
    const codeArray = Encoding.stringToCode(csvContent);
    const sjisArray = Encoding.convert(codeArray, "SJIS");

    const blob = new Blob([new Uint8Array(sjisArray)], { type: "text/csv;charset=shift_jis" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "geocoding_results.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendLines();
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4 text-gray-100">ジオコーディング</h1>
      <div className="mb-4">
        <label htmlFor="addressInput" className="block text-sm font-medium mb-2 text-gray-200">
          クエリー一覧（1行に1つのクエリーを入力）
        </label>
        <textarea
          id="addressInput"
          value={inputText}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          className="w-full h-64 p-2 bg-gray-800 text-gray-100 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder={`例:
札幌市役所 札幌市中央区北１条西２丁目
札幌市北区北２３条西４丁目３－４`}
        />
      </div>
      <div className="flex justify-between items-center mb-4">
        <span className="text-sm text-gray-200">
          有効な行数: <strong>{lineCount}</strong>
        </span>
        <div className="space-x-2">
          <button
            onClick={handleSendLines}
            disabled={isSending}
            className="px-4 py-2 bg-blue-600 text-gray-100 rounded hover:bg-blue-500 transition"
          >
            {isSending ? "送信中..." : "送信"}
          </button>
          <button
            onClick={handleDownloadCSV}
            disabled={isSending || results.length === 0}
            className="px-4 py-2 bg-green-600 text-gray-100 rounded hover:bg-green-500 transition"
          >
            CSVダウンロード
          </button>
        </div>
      </div>
      <div>
        <h2 className="text-xl font-bold mb-2 text-gray-100">ジオコーディング結果</h2>
        {results.length === 0 ? (
          <p className="text-gray-200">結果がまだありません。</p>
        ) : (
          <table className="w-full text-gray-200 border-collapse">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="px-2 py-1">No.</th>
                <th className="px-2 py-1">クエリー</th>
                <th className="px-2 py-1">緯度</th>
                <th className="px-2 py-1">経度</th>
              </tr>
            </thead>
            <tbody>
              {results.map((result, index) => (
                // キャッシュ結果は青系、新規取得結果は緑系の背景色を付与
                <tr
                  key={index}
                  className={`border-b border-gray-700 ${result.isCached ? "bg-blue-800" : "bg-green-800"}`}
                >
                  <td className="px-2 py-1">{index + 1}</td>
                  <td className="px-2 py-1">{result.query}</td>
                  <td className="px-2 py-1">
                    {result.latitude !== null ? Number(result.latitude).toFixed(7) : "-"}
                  </td>
                  <td className="px-2 py-1">
                    {result.longitude !== null ? Number(result.longitude).toFixed(7) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default GeocodingPage;
