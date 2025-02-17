// src/pages/geocodingpage.tsx
import React, { useState } from "react";
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
  // 緯度経度入力の場合、元の入力値を保持する（例："35.6812996,139.7670658"）
  original?: string;
  // 追加: 取得時のモード ("address" または "latlng")
  mode?: "address" | "latlng";
}

// IndexedDB用の関数（GeocodeCacheDB）
function openCacheDB(): Promise<IDBDatabase> {
  return indexedDBUtils.openDB("GeocodeCacheDB", 1, (db) => {
    if (!db.objectStoreNames.contains("geocodeCache")) {
      db.createObjectStore("geocodeCache", { keyPath: "query" });
    }
  });
}

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

// GeoResult オブジェクトそのものを保存する
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
  const [inputText, setInputText] = useState("");
  const [lineCount, setLineCount] = useState(0);
  const [isSending, setIsSending] = useState(false);
  // サーバから取得した詳細な結果を保持する
  const [results, setResults] = useState<GeoResult[]>([]);
  // 入力モードの状態（"address" または "latlng"）　デフォルトは "address"
  const [inputMode, setInputMode] = useState<"address" | "latlng">("address");
  // CSV出力エンコーディングの選択状態（"utf8" または "shift-jis"）
  const [csvEncoding, setCsvEncoding] = useState<"utf8" | "shift-jis">("shift-jis");
  const token = useToken();

  const API_BASE_URL: string = Config.API_BASE_URL;

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value;
    setInputText(text);
    // 入力モードにより、有効行の判定を変更
    let validLines: string[] = [];
    if (inputMode === "address") {
      validLines = text.split("\n").filter((line) => line.trim().length > 0);
    } else {
      // 緯度経度モードの場合、空白削除後、正しい形式の行のみカウント
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

  const handleSendLines = async () => {
    const allLines = inputText
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    if (allLines.length === 0) return;

    const confirmed = window.confirm(`入力件数は${allLines.length}件です。実行しますか？`);
    if (!confirmed) return;

    setIsSending(true);
    const timestamp = Date.now();

    try {
      if (inputMode === "address") {
        // クエリー入力の場合（従来の処理）
        const cachedResults: { [query: string]: GeoResult } = {};
        const queriesToFetch: string[] = [];

        await Promise.all(
          allLines.map(async (line) => {
            const query = line;
            try {
              const cached = await getCachedResult(query);
              if (cached && timestamp - (cached.fetchedAt || 0) < Config.CACHE_TTL_MS) {
                cachedResults[query] = { ...cached, isCached: true };
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
          const response = await fetch(`${API_BASE_URL}/backend/address2coordinates`, {
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
          queriesToFetch.forEach((query, index) => {
            const geoResult: GeoResult = {
              query,
              ...data.results[index],
              isCached: false,
              fetchedAt: timestamp,
              mode: "address",
            };
            fetchedResults[query] = geoResult;
            setCachedResult(geoResult).catch((err) =>
              console.error("キャッシュ保存エラー:", err)
            );
          });
        }

        const mergedResults: { [query: string]: GeoResult } = { ...cachedResults, ...fetchedResults };
        const finalResults: GeoResult[] = allLines.map((line) => mergedResults[line]);
        console.log("送信成功", finalResults);
        setResults(finalResults);
      } else {
        // 緯度経度入力の場合：各行を「数字,数字」の形式に整形し、範囲チェックおよび四捨五入（小数第8桁目で四捨五入して小数第7桁まで）を実施
        const pattern = /^-?\d+(\.\d+)?,-?\d+(\.\d+)?$/;
        const validLines: string[] = [];
        const errorResults: { [original: string]: GeoResult } = {};
        const originalMapping: { [original: string]: string } = {};

        allLines.forEach((line) => {
          const noSpace = line.replace(/\s/g, "");
          if (!pattern.test(noSpace)) {
            errorResults[line] = {
              query: line,
              status: "INVALID_FORMAT",
              formatted_address: "",
              latitude: null,
              longitude: null,
              location_type: "",
              place_id: "",
              types: "",
              error: "無効な形式",
              mode: "latlng",
            };
          } else {
            const parts = noSpace.split(",");
            let lat = parseFloat(parts[0]);
            let lng = parseFloat(parts[1]);
            if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
              errorResults[line] = {
                query: line,
                status: "INVALID_RANGE",
                formatted_address: "",
                latitude: lat,
                longitude: lng,
                location_type: "",
                place_id: "",
                types: "",
                error: "範囲外",
                mode: "latlng",
              };
            } else {
              // 小数第8桁目で四捨五入し、小数第7桁までの文字列に変換
              lat = Math.round(lat * 1e7) / 1e7;
              lng = Math.round(lng * 1e7) / 1e7;
              const roundedLine = `${lat.toFixed(7)},${lng.toFixed(7)}`;
              validLines.push(roundedLine);
              originalMapping[line] = roundedLine;
            }
          }
        });

        // キャッシュチェック
        const cachedResults: { [query: string]: GeoResult } = {};
        const queriesToFetch: string[] = [];
        await Promise.all(
          validLines.map(async (query) => {
            try {
              const cached = await getCachedResult(query);
              if (cached && timestamp - (cached.fetchedAt || 0) < Config.CACHE_TTL_MS) {
                cachedResults[query] = { ...cached, isCached: true };
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
          const response = await fetch(`${API_BASE_URL}/backend/latlng2query`, {
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
          queriesToFetch.forEach((query, index) => {
            const geoResult: GeoResult = {
              query,
              ...data.results[index],
              isCached: false,
              fetchedAt: timestamp,
              mode: "latlng",
            };
            fetchedResults[query] = geoResult;
            setCachedResult(geoResult).catch((err) =>
              console.error("キャッシュ保存エラー:", err)
            );
          });
        }

        const mergedResults: { [query: string]: GeoResult } = { ...cachedResults, ...fetchedResults };
        const finalResults: GeoResult[] = [];
        allLines.forEach((line) => {
          if (errorResults[line]) {
            finalResults.push(errorResults[line]);
          } else if (originalMapping[line]) {
            const key = originalMapping[line];
            // ここで元の入力値もセットする
            const res = mergedResults[key];
            res.original = line;
            finalResults.push(res);
          }
        });
        console.log("送信成功", finalResults);
        setResults(finalResults);
      }
    } catch (error) {
      console.error("送信エラー", error);
    } finally {
      setIsSending(false);
    }
  };

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

    let blob: Blob;
    if (csvEncoding === "utf8") {
      // UTF-8の場合はそのままBlob生成
      blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });
    } else {
      // Shift-JISの場合、エンコード変換
      const codeArray = Encoding.stringToCode(csvContent);
      const sjisArray = Encoding.convert(codeArray, "SJIS");
      blob = new Blob([new Uint8Array(sjisArray)], { type: "text/csv;charset=shift_jis" });
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
        <label className="block text-sm font-medium text-gray-200 mb-2">入力モード</label>
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
      <div className="mb-4">
        <label htmlFor="addressInput" className="block text-sm font-medium mb-2 text-gray-200">
          {inputMode === "address"
            ? "1行毎に住所や施設名等の「キーワード」を入力すると、緯度経度を返します。"
            : "1行毎に「緯度,経度」を入力すると、住所を返します。"}
        </label>
        <textarea
          id="addressInput"
          value={inputText}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          className="w-full h-64 p-2 bg-gray-800 text-gray-100 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder={
            inputMode === "address"
              ? `札幌市役所　札幌市中央区北１条西２丁目
札幌市北区北８条西３丁目４－６
東京タワー`
              : `35.6812996,139.7670658`
          }
        />
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4">
        <span className="text-sm text-gray-200 mb-2 sm:mb-0">
          有効な行数: <strong>{lineCount}</strong>
        </span>
        <div className="flex items-center space-x-2">
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
          {/* CSV出力エンコーディング選択用のラジオボタン */}
          <div className="flex items-center text-gray-200">
            <label className="mr-2">
              <input
                type="radio"
                name="csvEncoding"
                value="utf8"
                checked={csvEncoding === "utf8"}
                onChange={() => setCsvEncoding("utf8")}
              />{" "}
              UTF-8
            </label>
            <label>
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
                {/* 結果ごとの mode に合わせてヘッダーを表示（※ここでは先頭の結果で判定） */}
                {results[0]?.mode === "address" ? (
                  <>
                    <th className="px-2 py-1">クエリー</th>
                    <th className="px-2 py-1">緯度</th>
                    <th className="px-2 py-1">経度</th>
                  </>
                ) : (
                  <>
                    <th className="px-2 py-1">クエリー</th>
                    <th className="px-2 py-1">住所</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {results.map((result, index) => (
                <tr
                  key={index}
                  className={`border-b border-gray-700 ${
                    result.isCached ? "bg-blue-800" : "bg-green-800"
                  }`}
                >
                  <td className="px-2 py-1">{index + 1}</td>
                  {result.mode === "address" ? (
                    <>
                      <td className="px-2 py-1">{result.query}</td>
                      <td className="px-2 py-1">
                        {result.latitude !== null ? Number(result.latitude).toFixed(7) : "-"}
                      </td>
                      <td className="px-2 py-1">
                        {result.longitude !== null ? Number(result.longitude).toFixed(7) : "-"}
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-2 py-1">{result.original || result.query}</td>
                      <td className="px-2 py-1">
                        {result.formatted_address || result.error || "-"}
                      </td>
                    </>
                  )}
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
