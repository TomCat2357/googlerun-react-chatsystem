// frontend/src/components/SpeechToText/SpeechToTextPage.tsx

import React, { useState, useRef, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import Encoding from "encoding-japanese";
import * as indexedDBUtils from "../../utils/indexedDBUtils";

interface AudioInfo {
  duration: number;
  fileName?: string;
  fileSize?: number | null;
  mimeType?: string;
}

interface SpeechRecord {
  // 共通DBのキーは正規化済みの音声データ文字列
  audioKey: string;
  audioData: string;
  description: string;
  recordingDate: string;
  transcription: string;
  lastUpdateTime: string;
}

interface TimedSegment {
  start_time: string; // "HH:MM:SS"形式
  end_time: string;
  text: string;
}

/**
 * 共通の SpeechToText 用 IndexedDB オープン関数  
 * DB名："SpeechToTextDB"、オブジェクトストア名："speechRecords"  
 * キーは audioKey（正規化済み音声データ）とする。
 */
const openSpeechDB = (): Promise<IDBDatabase> => {
  return indexedDBUtils.openDB("SpeechToTextDB", 1, (db) => {
    if (!db.objectStoreNames.contains("speechRecords")) {
      db.createObjectStore("speechRecords", { keyPath: "audioKey" });
    }
  });
};

/**
 * ファイルの lastModified プロパティ（ミリ秒）を "YYYY/mm/dd" 形式に変換する関数
 */
const formatDate = (timestamp: number): string => {
  const date = new Date(timestamp);
  const year = date.getFullYear();
  const month = ("0" + (date.getMonth() + 1)).slice(-2);
  const day = ("0" + date.getDate()).slice(-2);
  return `${year}/${month}/${day}`;
};

/**
 * "HH:MM:SS"形式の文字列を秒数に変換するヘルパー関数
 */
const timeStringToSeconds = (timeStr: string): number => {
  const parts = timeStr.split(":").map(Number);
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
};

const SpeechToTextPage = () => {
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // アップロードモード、音声データ、文字起こし結果、その他各種状態
  const [uploadMode, setUploadMode] = useState<"file" | "base64">("file");
  const [fileBase64Data, setFileBase64Data] = useState("");
  const [pastedBase64Data, setPastedBase64Data] = useState("");
  const audioData = fileBase64Data || pastedBase64Data;
  const preview = audioData.substring(0, 30);
  const [outputText, setOutputText] = useState("");
  const [audioInfo, setAudioInfo] = useState<AudioInfo | null>(null);
  const [isSending, setIsSending] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 説明・録音日・履歴管理用の状態
  const [description, setDescription] = useState("");
  const [recordingDate, setRecordingDate] = useState("");
  const [currentAudioKey, setCurrentAudioKey] = useState<string | null>(null);
  const [speechRecords, setSpeechRecords] = useState<SpeechRecord[]>([]);
  const debounceTimer = useRef<number | null>(null);

  // 追加：再生・一時停止、再生速度、現在時刻、タイムドセグメント、カーソル位置、タイムスタンプ表示の状態
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [timedTranscript, setTimedTranscript] = useState<TimedSegment[]>([]);
  const [cursorTime, setCursorTime] = useState<string | null>(null);
  const [showTimestamps, setShowTimestamps] = useState(false);

  const audioRef = useRef<HTMLAudioElement>(null);

  /**
   * 現在のセッション内容をDBに保存する関数。
   * ※保存対象は、文字起こし結果が存在し、かつエラーでない場合に限定する。
   */
  const updateCurrentSpeechRecord = async () => {
    // 文字起こし結果が空、またはエラーのときは保存しない
    if (!outputText.trim() || !audioData || outputText.startsWith("エラーが発生しました:")) return;
    const normalizedAudio = audioData.replace(/^data:audio\/[a-zA-Z0-9]+;base64,/, "");
    setCurrentAudioKey(normalizedAudio);
    const record: SpeechRecord = {
      audioKey: normalizedAudio,
      audioData,
      description,
      recordingDate,
      transcription: outputText,
      lastUpdateTime: new Date().toISOString(),
    };
    try {
      const db = await openSpeechDB();
      const transaction = db.transaction("speechRecords", "readwrite");
      const store = transaction.objectStore("speechRecords");
      store.put(record);
      loadSpeechRecords();
    } catch (error) {
      console.error("Speech record update error:", error);
    }
  };

  // 説明、録音日、音声データ、文字起こし結果の変更後、1秒後に自動保存（デバウンス）
  useEffect(() => {
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
    }
    debounceTimer.current = window.setTimeout(() => {
      updateCurrentSpeechRecord();
    }, 1000);
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [description, recordingDate, audioData, outputText]);

  // DBから全レコードを読み込み、最終更新日時の新しい順に並べる
  const loadSpeechRecords = async () => {
    try {
      const db = await openSpeechDB();
      const transaction = db.transaction("speechRecords", "readonly");
      const store = transaction.objectStore("speechRecords");
      const request = store.getAll();
      request.onsuccess = (e) => {
        const records = (e.target as IDBRequest).result as SpeechRecord[];
        const sortedRecords = records.sort(
          (a, b) =>
            new Date(b.lastUpdateTime).getTime() -
            new Date(a.lastUpdateTime).getTime()
        );
        setSpeechRecords(sortedRecords);
      };
      request.onerror = () => {
        console.error("Failed to load speech records", request.error);
      };
    } catch (error) {
      console.error("Error loading speech records:", error);
    }
  };

  useEffect(() => {
    loadSpeechRecords();
  }, []);

  // 履歴（レコード）ボタンを押したとき、該当レコードの内容を復元する
  const restoreHistory = (record: SpeechRecord) => {
    setDescription(record.description);
    setRecordingDate(record.recordingDate);
    setFileBase64Data(record.audioData);
    setPastedBase64Data("");
    setOutputText(record.transcription);
    setCurrentAudioKey(record.audioKey);
  };

  // 「履歴保存」ボタン：DB上の全レコードをJSONとしてダウンロード
  const downloadHistory = () => {
    const historyData = JSON.stringify(speechRecords, null, 2);
    const blob = new Blob([historyData], { type: "application/json" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `speech-history-${new Date().toISOString()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  // 「履歴読込」ボタン：JSONファイルをアップロードしてDBを上書き・復元
  const uploadHistory = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const content = e.target?.result as string;
        const uploadedRecords = JSON.parse(content) as SpeechRecord[];
        const db = await openSpeechDB();
        const transaction = db.transaction("speechRecords", "readwrite");
        const store = transaction.objectStore("speechRecords");
        store.clear().onsuccess = () => {
          uploadedRecords.forEach((record) => store.add(record));
          setSpeechRecords(uploadedRecords);
        };
      } catch (error) {
        console.error("履歴アップロードエラー:", error);
      }
    };
    reader.readAsText(file);
  };

  // 説明・録音日の入力変更ハンドラー
  const handleDescriptionChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDescription(e.target.value);
  };
  const handleRecordingDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setRecordingDate(e.target.value);
  };

  /**
   * ファイル選択／ドラッグ時の処理  
   * ファイル読み込み後、Base64文字列に変換し、  
   * ・自動で説明と録音日を設定（ファイル名、作成日）  
   * ・正規化した音声データキーでDBを確認し、既存レコードがあればその内容を復元する
   */
  const processFile = async (file: File) => {
    if (!file.type.startsWith("audio/")) {
      alert("音声ファイル以外はアップロードできません");
      return;
    }
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    audio.src = url;
    audio.onloadedmetadata = () => {
      setAudioInfo({
        duration: audio.duration,
        fileName: file.name,
        fileSize: file.size,
        mimeType: file.type,
      });
      URL.revokeObjectURL(url);
    };
    audio.onerror = () => {
      alert("無効な音声データです");
      setFileBase64Data("");
      setAudioInfo(null);
      URL.revokeObjectURL(url);
    };

    const fileData = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target?.result) {
          resolve(event.target.result as string);
        } else {
          reject(new Error("ファイル読み込みエラー"));
        }
      };
      reader.onerror = () => reject(new Error("ファイル読み込みエラー"));
      reader.readAsDataURL(file);
    });

    setFileBase64Data(fileData);
    setPastedBase64Data("");
    // 自動で説明（ファイル名）と録音日（ファイルの最終更新日）を設定
    setDescription(file.name);
    setRecordingDate(formatDate(file.lastModified));

    const normalizedAudio = fileData.replace(/^data:audio\/[a-zA-Z0-9]+;base64,/, "");
    try {
      const db = await openSpeechDB();
      const record = await indexedDBUtils.getItemFromStore<SpeechRecord>(
        db,
        "speechRecords",
        normalizedAudio
      );
      if (record) {
        restoreHistory(record);
      }
    } catch (error) {
      console.error("DBチェックエラー:", error);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    processFile(file);
  };

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    processFile(file);
  };

  // Base64貼り付けの場合の処理
  const isValidBase64String = (str: string): boolean => {
    const cleaned = str.replace(/\s/g, "");
    if (cleaned === "") return false;
    if (cleaned.startsWith("data:")) {
      const parts = cleaned.split(",");
      if (parts.length < 2) return false;
      return /^[A-Za-z0-9+/=]+$/.test(parts[1]);
    } else {
      return /^[A-Za-z0-9+/=]+$/.test(cleaned);
    }
  };

  const processBase64Data = (data: string) => {
    let dataUrl = data;
    const cleaned = data.replace(/\s/g, "");
    if (!isValidBase64String(cleaned)) {
      alert("無効なBase64データです");
      setPastedBase64Data("");
      setAudioInfo(null);
      return;
    }
    if (!cleaned.startsWith("data:")) {
      dataUrl = "data:audio/mpeg;base64," + cleaned;
    }
    const audio = new Audio();
    audio.src = dataUrl;
    audio.onloadedmetadata = () => {
      setAudioInfo({
        duration: audio.duration,
        fileName: "Base64貼り付けデータ",
        fileSize: null,
        mimeType: audio.src.substring(5, audio.src.indexOf(";")),
      });
    };
    audio.onerror = () => {
      alert("無効な音声データです");
      setPastedBase64Data("");
      setAudioInfo(null);
    };
    setPastedBase64Data(dataUrl);
  };

  const handleTextInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setFileBase64Data("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setPastedBase64Data(value);
    if (value.trim() !== "") {
      processBase64Data(value);
    } else {
      setAudioInfo(null);
    }
  };

  // クリアボタン：全入力・結果・メタ情報をリセット
  const handleClearBoth = () => {
    setFileBase64Data("");
    setPastedBase64Data("");
    setOutputText("");
    setAudioInfo(null);
    setDescription("");
    setRecordingDate("");
    setCurrentAudioKey(null);
    setTimedTranscript([]);
    setCursorTime(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsPlaying(false);
    }
  };

  /**
   * 送信ボタン押下時の処理  
   * ・音声データの正規化キーでDBからレコードを確認し、なければバックエンドへリクエスト  
   * ・送信後は現在のセッション内容をDBに保存する
   */
  const handleSend = async () => {
    if (!audioData) {
      alert("送信するデータがありません");
      return;
    }
    setIsSending(true);
    const normalizedAudio = audioData.replace(/^data:audio\/[a-zA-Z0-9]+;base64,/, "");
    try {
      const db = await openSpeechDB();
      const record = await indexedDBUtils.getItemFromStore<SpeechRecord>(
        db,
        "speechRecords",
        normalizedAudio
      );
      if (record && record.transcription) {
        setOutputText(record.transcription);
        setIsSending(false);
        updateCurrentSpeechRecord();
        return;
      }
    } catch (dbError) {
      console.error("DBチェックエラー:", dbError);
    }
  
    try {
      const response = await fetch(`${API_BASE_URL}/backend/speech2text`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ audio_data: audioData }),
      });
      if (response.ok) {
        const data = await response.json();
        // もしエラーが返ってきた場合はDBに保存しない
        if (data.error) {
          setOutputText("エラーが発生しました: " + data.error);
        } else {
          setOutputText(data.transcription);
          if (data.timed_transcription) {
            setTimedTranscript(data.timed_transcription);
          }
          const db = await openSpeechDB();
          await indexedDBUtils.setItemToStore(db, "speechRecords", {
            audioKey: normalizedAudio,
            audioData,
            description,
            recordingDate,
            transcription: data.transcription,
            lastUpdateTime: new Date().toISOString(),
          });
          updateCurrentSpeechRecord();
        }
      } else {
        setOutputText("エラーが発生しました");
      }
    } catch (error) {
      console.error(error);
      setOutputText("エラーが発生しました");
    } finally {
      setIsSending(false);
    }
  };
  

  const [selectedEncoding, setSelectedEncoding] = useState("utf8");
  const handleDownload = () => {
    let blob;
    let filename = "transcription.txt";
    if (selectedEncoding === "utf8") {
      blob = new Blob([outputText], { type: "text/plain;charset=utf-8" });
    } else {
      const sjisArray = Encoding.convert(outputText, { to: "SJIS", type: "array" });
      blob = new Blob([new Uint8Array(sjisArray)], { type: "text/plain;charset=shift_jis" });
      filename = "transcription_sjis.txt";
    }
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  // 再生/一時停止ボタンのハンドラー
  const handlePlayPause = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      // 一時停止中にカーソル位置が設定されていればそこから再生
      if (cursorTime) {
        audioRef.current.currentTime = timeStringToSeconds(cursorTime);
      }
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  // オーディオ再生中の時間更新処理
  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  // テキストセグメントのシングルクリック：再生中なら一時停止、停止中ならカーソル移動
  const handleSegmentClick = (segment: TimedSegment) => {
    if (isPlaying && audioRef.current) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      setCursorTime(segment.start_time);
    }
  };

  // テキストセグメントのダブルクリック：その位置から再生開始
  const handleSegmentDoubleClick = (segment: TimedSegment) => {
    if (audioRef.current) {
      audioRef.current.currentTime = timeStringToSeconds(segment.start_time);
      audioRef.current.play();
      setIsPlaying(true);
      setCursorTime(segment.start_time);
    }
  };

  // 再生速度変更ハンドラー
  const handleSpeedChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const speed = Number(e.target.value);
    setPlaybackSpeed(speed);
    if (audioRef.current) {
      audioRef.current.playbackRate = speed;
    }
  };

  return (
    <div className="flex flex-1 h-[calc(100vh-64px)] mt-2 overflow-hidden">
      {/* サイドバー：DBに保存された全レコード一覧 */}
      <div className="w-64 bg-gray-800 shadow-lg p-4 overflow-y-auto">
        <h2 className="text-lg font-semibold mb-4 text-gray-100">音声文字起こし履歴</h2>
        <div className="flex space-x-2 mb-6">
          <button
            onClick={downloadHistory}
            className="flex-1 p-2 bg-green-500 hover:bg-green-600 text-white rounded-lg"
          >
            履歴保存
          </button>
          <label className="flex-1">
            <input type="file" accept=".json" onChange={uploadHistory} className="hidden" />
            <span className="block p-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg text-center cursor-pointer">
              履歴読込
            </span>
          </label>
        </div>
        <div className="space-y-2">
          {speechRecords.map((record) => (
            <div
              key={record.audioKey}
              onClick={() => restoreHistory(record)}
              className="p-2 hover:bg-gray-700 text-gray-100 rounded cursor-pointer"
            >
              <div className="font-medium">
                {record.description.trim() !== ""
                  ? record.description.slice(0, 20)
                  : record.transcription.slice(0, 20) + '...'}
              </div>
              <div className="text-sm text-gray-400">{record.recordingDate}</div>
            </div>
          ))}
        </div>
      </div>

      {/* メインエリア：音声アップロード・文字起こしインターフェース */}
      <div className="flex-1 p-4 overflow-y-auto bg-dark-primary text-white">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">音声文字起こし</h1>
          <button
            onClick={handleClearBoth}
            className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
          >
            クリア
          </button>
        </div>

        {/* 説明と録音日の入力欄 */}
        <div className="mb-6">
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-200">説明</label>
            <input
              type="text"
              value={description}
              onChange={handleDescriptionChange}
              maxLength={20}
              placeholder="20文字以内"
              className="w-full p-2 text-black"
            />
          </div>
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-200">録音日</label>
            <input
              type="text"
              value={recordingDate}
              onChange={handleRecordingDateChange}
              placeholder="YYYY/mm/dd"
              className="w-full p-2 text-black"
            />
          </div>
        </div>

        {/* アップロードセクション */}
        <div className="mb-6">
          <h2 className="text-xl font-bold mb-2">音声データのアップロード方法</h2>
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-200 mb-2">
              アップロード方法
            </label>
            <div>
              <label className="mr-4 text-gray-200">
                <input
                  type="radio"
                  name="uploadMode"
                  value="file"
                  checked={uploadMode === "file"}
                  onChange={() => {
                    setUploadMode("file");
                    handleClearBoth();
                  }}
                />{" "}
                ファイル選択
              </label>
              <label className="text-gray-200">
                <input
                  type="radio"
                  name="uploadMode"
                  value="base64"
                  checked={uploadMode === "base64"}
                  onChange={() => {
                    setUploadMode("base64");
                    handleClearBoth();
                  }}
                />{" "}
                Base64貼り付け
              </label>
            </div>
          </div>

          {uploadMode === "file" ? (
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
              className="border-dashed border-2 border-gray-400 p-4 mb-4 text-center cursor-pointer"
              onClick={() => fileInputRef.current?.click()}
            >
              ここにドラッグ＆ドロップするか、クリックしてファイルを選択してください（音声ファイル）
              <input type="file" ref={fileInputRef} accept="audio/*" onChange={handleFileChange} className="hidden" />
            </div>
          ) : (
            <div className="mb-4">
              <label className="block mb-2">Base64エンコードされたデータを貼り付け</label>
              <textarea
                placeholder="Base64データを貼り付けてください"
                onChange={handleTextInputChange}
                value={pastedBase64Data}
                className="w-full p-2 text-black"
                rows={4}
              />
            </div>
          )}

          <div className="mb-4">
            <p className="text-sm">
              アップロードされたデータの先頭: <span className="text-green-300">{preview}</span>
            </p>
          </div>

          {audioInfo && (
            <div className="mb-4">
              <p className="text-sm">
                音声情報:{" "}
                {audioInfo.fileName && `ファイル名: ${audioInfo.fileName}, `}
                {audioInfo.duration !== undefined && `再生時間: ${audioInfo.duration.toFixed(2)}秒, `}
                {audioInfo.fileSize !== null &&
                  audioInfo.fileSize !== undefined &&
                  `ファイルサイズ: ${(audioInfo.fileSize / 1024).toFixed(1)}KB, `}
                {audioInfo.mimeType && `MIMEタイプ: ${audioInfo.mimeType}`}
              </p>
            </div>
          )}
        </div>

        {/* 再生コントロール */}
        <div className="mb-6">
          <button
            onClick={handlePlayPause}
            className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded mr-4"
          >
            {isPlaying ? "一時停止" : "再生"}
          </button>
          <select value={playbackSpeed} onChange={handleSpeedChange} className="p-2 text-black">
            <option value={0.5}>0.5x</option>
            <option value={1}>1x</option>
            <option value={1.5}>1.5x</option>
            <option value={2}>2x</option>
          </select>
          <label className="ml-4">
            <input
              type="checkbox"
              checked={showTimestamps}
              onChange={() => setShowTimestamps(!showTimestamps)}
            />{" "}
            タイムスタンプ表示
          </label>
        </div>

        {/* 隠しオーディオ要素 */}
        {audioData && (
          <audio
            ref={audioRef}
            src={audioData}
            onTimeUpdate={handleTimeUpdate}
          />
        )}

        {/* 送信ボタン */}
        <button
          onClick={handleSend}
          disabled={isSending}
          className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded"
        >
          {isSending ? "処理中..." : "送信"}
        </button>

        {/* 文字起こし結果の表示（インタラクティブなテキスト） */}
        <div className="mt-6">
          <h2 className="text-xl font-bold mb-2">文字起こし結果</h2>
          <div className="p-2 bg-white text-black rounded" style={{ maxHeight: "300px", overflowY: "auto" }}>
            {timedTranscript.length > 0 ? (
              timedTranscript.map((segment, index) => {
                // 現在の再生位置に近いセグメントをハイライト
                const segmentStartSec = timeStringToSeconds(segment.start_time);
                const segmentEndSec = timeStringToSeconds(segment.end_time);
                const isActive =
                  currentTime >= segmentStartSec && currentTime < segmentEndSec;
                const style: React.CSSProperties = {
                  cursor: "pointer",
                  backgroundColor: isActive || (cursorTime === segment.start_time) ? "#ffd700" : "transparent",
                  padding: "2px 0",
                };
                return (
                  <div
                    key={index}
                    style={style}
                    onClick={() => handleSegmentClick(segment)}
                    onDoubleClick={() => handleSegmentDoubleClick(segment)}
                  >
                    {showTimestamps && <span className="mr-2 text-blue-700">[{segment.start_time}]</span>}
                    <span>{segment.text}</span>
                  </div>
                );
              })
            ) : (
              <textarea value={outputText} readOnly className="w-full p-2 text-black" rows={6} />
            )}
          </div>
        </div>

        {/* ダウンロードボタンとエンコーディング選択 */}
        <div className="mt-6 flex items-center space-x-4">
          <button
            onClick={handleDownload}
            className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded"
          >
            ダウンロード
          </button>
          <div className="flex items-center space-x-2">
            <label className="text-gray-200">
              <input
                type="radio"
                name="encoding"
                value="utf8"
                checked={selectedEncoding === "utf8"}
                onChange={() => setSelectedEncoding("utf8")}
              />{" "}
              UTF-8
            </label>
            <label className="text-gray-200">
              <input
                type="radio"
                name="encoding"
                value="shift-jis"
                checked={selectedEncoding === "shift-jis"}
                onChange={() => setSelectedEncoding("shift-jis")}
              />{" "}
              Shift-JIS
            </label>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SpeechToTextPage;
