// src/pages/geocodingpage.tsx
import React, { useState, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as indexedDBUtils from "../../utils/indexedDBUtils";
import * as Config from "../../config";
import * as Encoding from "encoding-japanese";

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
  // キャッシュから取得したかどうか（true: キャッシュ, false: 新規取得）
  isCached?: boolean;
  // データ取得日時（UNIXミリ秒）
  fetchedAt?: number;
}

// IndexedDB用の関数（GeocodeCacheDB）
function openCacheDB(): Promise<IDBDatabase> {
  return indexedDBUtils.openDB("GeocodeCacheDB", 1, (db) => {
    if (!db.objectStoreNames.contains("geocodeCache")) {
      db.createObjectStore("geocodeCache", { keyPath: "query" });
    }
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
  const token = useToken();

  const API_BASE_URL: string = Config.API_BASE_URL;

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
      // キャッシュチェック
      const cachedResults: { [query: string]: GeoResult } = {};
      const queriesToFetch: string[] = [];

      await Promise.all(
        validLines.map(async (line) => {
          const query = line.trim();
          try {
            const cached = await getCachedResult(query);
            if (cached && now - cached.timestamp < Config.CACHE_TTL_MS) {
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
        // API取得結果は入力行順（重複含む）で返される前提
        queriesToFetch.forEach((query, index) => {
          const fetchedAt = Date.now();
          fetchedResults[query] = { ...data.results[index], isCached: false, fetchedAt };
          setCachedResult(query, data.results[index]).catch((err) =>
            console.error("キャッシュ保存エラー:", err)
          );
        });
      }

      // キャッシュ済みと新規取得分のマージ
      const mergedResults: { [query: string]: GeoResult } = { ...cachedResults, ...fetchedResults };
      const finalResults: GeoResult[] = validLines.map((line) => mergedResults[line.trim()]);
      console.log("送信成功", finalResults);
      setResults(finalResults);
    } catch (error) {
      console.error("送信エラー", error);
    } finally {
      setIsSending(false);
    }
  };

  // CSVダウンロード処理（Shift_JIS変換付き）
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
      result.fetchedAt ? new Date(result.fetchedAt).toLocaleString("ja-JP") : "",
      result.isCached ? "キャッシュ" : "API取得",
    ]);

    const csvContent =
      [header, ...rows]
        .map((row) =>
          row
            .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
            .join(",")
        )
        .join("\n");

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
                <tr key={index} className={`border-b border-gray-700 ${result.isCached ? "bg-blue-800" : "bg-green-800"}`}>
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
