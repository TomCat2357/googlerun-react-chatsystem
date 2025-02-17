// src/components/Geocoding/GeocodingPage.tsx
import React, { useState, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as indexedDBUtils from "../../utils/indexedDBUtils";
import * as Config from "../../config";
import * as Encoding from "encoding-japanese";
import { MapControls } from "./MapControls";
import { imageCache } from "../../utils/imageCache";

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

  // 地図表示用のstate
  const [showSatellite, setShowSatellite] = useState(false);
  const [showStreetView, setShowStreetView] = useState(false);
  const [satelliteZoom, setSatelliteZoom] = useState(18);
  const [streetViewHeading, setStreetViewHeading] = useState(0);
  const [streetViewPitch, setStreetViewPitch] = useState(0);
  const [streetViewFov, setStreetViewFov] = useState(90);
  const [isLoadingImages, setIsLoadingImages] = useState(false);

  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // 地図画像取得関数
  const fetchMapImage = async (
    lat: number,
    lng: number,
    type: "satellite" | "streetview"
  ): Promise<string> => {
    const cacheKey =
      type === "satellite"
        ? { type, lat, lng, zoom: satelliteZoom }
        : { type, lat, lng, heading: streetViewHeading, pitch: streetViewPitch, fov: streetViewFov };

    const cachedImage = imageCache.get(cacheKey);
    if (cachedImage) {
      return cachedImage;
    }

    const endpoint = type === "satellite" ? "static-map" : "street-view";
    const params = new URLSearchParams({
      latitude: lat.toString(),
      longitude: lng.toString(),
      ...(type === "satellite"
        ? { zoom: satelliteZoom.toString(), maptype: "satellite" }
        : {
            heading: streetViewHeading.toString(),
            pitch: streetViewPitch.toString(),
            fov: streetViewFov.toString()
          })
    });

    try {
      const response = await fetch(
        `${API_BASE_URL}/backend/${endpoint}?${params.toString()}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(`画像取得エラー: ${response.statusText}`);
      }

      const blob = await response.blob();
      const base64 = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result as string);
        reader.readAsDataURL(blob);
      });

      imageCache.set(cacheKey, base64);
      return base64;
    } catch (error) {
      console.error(`${type}画像取得エラー:`, error);
      return "";
    }
  };

  // 結果に画像を追加する関数
  const addImagesToResults = async (currentResults: GeoResult[]) => {
    setIsLoadingImages(true);
    try {
      const updatedResults = await Promise.all(
        currentResults.map(async (result) => {
          if (result.latitude === null || result.longitude === null) {
            return result;
          }
          const [satelliteImage, streetViewImage] = await Promise.all([
            showSatellite ? fetchMapImage(result.latitude, result.longitude, "satellite") : Promise.resolve(""),
            showStreetView ? fetchMapImage(result.latitude, result.longitude, "streetview") : Promise.resolve(""),
          ]);
          return {
            ...result,
            satelliteImage: satelliteImage || undefined,
            streetViewImage: streetViewImage || undefined,
          };
        })
      );
      setResults(updatedResults);
    } finally {
      setIsLoadingImages(false);
    }
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
      result.fetchedAt ? new Date(result.fetchedAt).toLocaleString("ja-JP") : "",
      result.isCached ? "キャッシュ" : "API取得",
    ]);

    const csvContent = [header, ...rows]
      .map((row) =>
        row
          .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
          .join(",")
      )
      .join("\n");

    let blob: Blob;
    if (csvEncoding === "utf8") {
      blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });
    } else {
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

  // 送信処理（入力内容に応じたジオコーディング＋画像取得）
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
    let finalResults: GeoResult[] = [];

    try {
      if (inputMode === "address") {
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

        const mergedResults: { [query: string]: GeoResult } = {
          ...cachedResults,
          ...fetchedResults,
        };
        finalResults = allLines.map((line) => mergedResults[line]);
      } else {
        // 緯度経度入力の場合
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

        const mergedResults: { [query: string]: GeoResult } = {
          ...cachedResults,
          ...fetchedResults,
        };
        finalResults = [];
        allLines.forEach((line) => {
          if (errorResults[line]) {
            finalResults.push(errorResults[line]);
          } else if (originalMapping[line]) {
            const key = originalMapping[line];
            const res = mergedResults[key];
            res.original = line;
            finalResults.push(res);
          }
        });
      }
      console.log("送信成功", finalResults);
      setResults(finalResults);
      await addImagesToResults(finalResults);
    } catch (error) {
      console.error("送信エラー", error);
    } finally {
      setIsSending(false);
    }
  };

  // 地図設定が変更されたときに画像を再取得する
  useEffect(() => {
    const timer = setTimeout(() => {
      if (results.length > 0 && (showSatellite || showStreetView)) {
        addImagesToResults(results);
      }
    }, 500); // 500ms後にAPIコールを実行
    return () => clearTimeout(timer);
  }, [showSatellite, showStreetView, satelliteZoom, streetViewHeading, streetViewPitch, streetViewFov]);
  
  return (
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4 text-gray-100">ジオコーディング</h1>

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
      />

      {/* 入力モード選択 */}
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

      {/* テキスト入力エリア */}
      <div className="mb-4">
        <label className="block text-sm font-medium mb-2 text-gray-200">
          {inputMode === "address"
            ? "1行毎に住所や施設名等の「キーワード」を入力すると、緯度経度を返します。"
            : "1行毎に「緯度,経度」を入力すると、住所を返します。"}
        </label>
        <textarea
          value={inputText}
          onChange={handleTextChange}
          className="w-full h-64 p-2 bg-gray-800 text-gray-100 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500"
          placeholder={inputMode === "address" ? "例：札幌市役所" : "例：35.6812996,139.7670658"}
        />
      </div>

      {/* アクションボタン */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-gray-200">
          有効な行数: <strong>{lineCount}</strong>
        </div>
        <div className="flex items-center space-x-4">
          <button
            onClick={handleSendLines}
            disabled={isSending || isLoadingImages}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {isSending || isLoadingImages ? "処理中..." : "送信"}
          </button>
          <button
            onClick={handleDownloadCSV}
            disabled={isSending || results.length === 0}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            CSVダウンロード
          </button>
        </div>
      </div>

      {/* 結果テーブル */}
      {results.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-gray-200">
            <thead>
              <tr className="bg-gray-700">
                <th className="px-4 py-2">No.</th>
                <th className="px-4 py-2">クエリー</th>
                {inputMode === "address" ? (
                  <>
                    <th className="px-4 py-2">緯度</th>
                    <th className="px-4 py-2">経度</th>
                  </>
                ) : (
                  <th className="px-4 py-2">住所</th>
                )}
                {showSatellite && <th className="px-4 py-2">衛星写真</th>}
                {showStreetView && <th className="px-4 py-2">ストリートビュー</th>}
              </tr>
            </thead>
            <tbody>
              {results.map((result, index) => (
                <tr key={index} className="border-b border-gray-700">
                  <td className="px-4 py-2">{index + 1}</td>
                  <td className="px-4 py-2">{result.original || result.query}</td>
                  {inputMode === "address" ? (
                    <>
                      <td className="px-4 py-2">
                        {result.latitude !== null ? result.latitude.toFixed(7) : "-"}
                      </td>
                      <td className="px-4 py-2">
                        {result.longitude !== null ? result.longitude.toFixed(7) : "-"}
                      </td>
                    </>
                  ) : (
                    <td className="px-4 py-2">
                      {result.formatted_address || result.error || "-"}
                    </td>
                  )}
                  {showSatellite && (
                    <td className="px-4 py-2">
                      {result.satelliteImage && (
                        <img
                          src={result.satelliteImage}
                          alt="衛星写真"
                          className="max-w-xs"
                        />
                      )}
                    </td>
                  )}
                  {showStreetView && (
                    <td className="px-4 py-2">
                      {result.streetViewImage && (
                        <img
                          src={result.streetViewImage}
                          alt="ストリートビュー"
                          className="max-w-xs"
                        />
                      )}
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
