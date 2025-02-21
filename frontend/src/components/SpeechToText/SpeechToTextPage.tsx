// frontend/src/components/SpeechToText/SpeechToTextPage.tsx

import React, { useState, useRef, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import Encoding from "encoding-japanese";

interface AudioInfo {
  duration: number;
  fileName?: string;
  fileSize?: number | null;
  mimeType?: string;
}

interface TimedSegment {
  start_time: string; // "HH:MM:SS"
  end_time: string;   // "HH:MM:SS"
  text: string;
}

/**
 * "HH:MM:SS" → 秒数
 */
const timeStringToSeconds = (timeStr: string): number => {
  const parts = timeStr.split(":").map(Number);
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
};

/**
 * 秒数 → "HH:MM:SS"
 */
const secondsToTimeString = (seconds: number): string => {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  return `${hrs.toString().padStart(2, "0")}:${mins
    .toString()
    .padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

const SpeechToTextPage = () => {
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // ---------- 音声データ関連の状態 ----------
  const [uploadMode, setUploadMode] = useState<"file" | "base64">("file");
  const [fileBase64Data, setFileBase64Data] = useState("");
  const [pastedBase64Data, setPastedBase64Data] = useState("");
  const audioData = fileBase64Data || pastedBase64Data;
  const preview = audioData.substring(0, 30);

  const [audioInfo, setAudioInfo] = useState<AudioInfo | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  // ---------- メタ情報 ----------
  const [description, setDescription] = useState("");
  const [recordingDate, setRecordingDate] = useState("");

  // ---------- 文字起こし結果（単語 or フレーズ単位） ----------
  const [timedTranscript, setTimedTranscript] = useState<TimedSegment[]>([]);

  // ---------- 再生コントロール ----------
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [sliderValue, setSliderValue] = useState(0);

  // ---------- UI制御 ----------
  const [cursorTime, setCursorTime] = useState<string | null>(null);
  const [showTimestamps, setShowTimestamps] = useState(false);
  const [isSending, setIsSending] = useState(false); // 処理中フラグ

  // ===========================================================
  //  ファイル選択 / Base64 貼り付け
  // ===========================================================
  /**
   * ファイルの lastModified を "YYYY/mm/dd" 形式に変換
   */
  const formatDate = (timestamp: number): string => {
    const date = new Date(timestamp);
    const year = date.getFullYear();
    const month = ("0" + (date.getMonth() + 1)).slice(-2);
    const day = ("0" + date.getDate()).slice(-2);
    return `${year}/${month}/${day}`;
  };

  /**
   * ファイル選択/ドラッグ時の処理
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
      setSliderValue(0);
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

    // UIリセット
    setFileBase64Data(fileData);
    setPastedBase64Data("");
    setTimedTranscript([]);
    setCursorTime(null);

    // 説明・録音日を自動設定
    setDescription(file.name);
    setRecordingDate(formatDate(file.lastModified));
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

  /**
   * Base64テキストを貼り付ける場合
   */
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
      setSliderValue(0);
    };
    audio.onerror = () => {
      alert("無効な音声データです");
      setPastedBase64Data("");
      setAudioInfo(null);
    };
    setPastedBase64Data(dataUrl);
    setTimedTranscript([]);
    setCursorTime(null);
  };

  const handleTextInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setFileBase64Data("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    if (value.trim() !== "") {
      processBase64Data(value);
    } else {
      setAudioInfo(null);
    }
  };

  // ===========================================================
  //  再生・スライダー連動
  // ===========================================================
  const handlePlayPause = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      // カーソル位置があればそこにジャンプ
      if (cursorTime) {
        audioRef.current.currentTime = timeStringToSeconds(cursorTime);
      }
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      const current = audioRef.current.currentTime;
      setCurrentTime(current);
      setSliderValue(current);
      if (isPlaying) {
        setCursorTime(secondsToTimeString(current));
      }
    }
  };

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = Number(e.target.value);
    setSliderValue(newValue);
    if (audioRef.current) {
      audioRef.current.currentTime = newValue;
    }
    setCurrentTime(newValue);
    setCursorTime(secondsToTimeString(newValue));
  };

  // ===========================================================
  //  文字起こし
  // ===========================================================
  const handleSend = async () => {
    if (!audioData) {
      alert("送信するデータがありません");
      return;
    }
    setIsSending(true);
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
        if (data.error) {
          console.error("Speech2Text error:", data.error);
        } else {
          if (data.timed_transcription) {
            setTimedTranscript(data.timed_transcription);
          } else {
            setTimedTranscript([]);
          }
        }
      } else {
        console.error("サーバーエラー");
      }
    } catch (error) {
      console.error(error);
    } finally {
      setIsSending(false);
    }
  };

  // ===========================================================
  //  セッションのバイナリ保存/読込
  // ===========================================================
  const handleClearBoth = () => {
    setFileBase64Data("");
    setPastedBase64Data("");
    setAudioInfo(null);
    setDescription("");
    setRecordingDate("");
    setTimedTranscript([]);
    setCursorTime(null);
    setSliderValue(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsPlaying(false);
    }
  };

  const handleSaveSession = () => {
    if (!audioData) {
      alert("保存する音声データがありません");
      return;
    }
    const session = {
      audioData,
      description,
      recordingDate,
      timedTranscript,
    };
    const jsonString = JSON.stringify(session);
    const encoder = new TextEncoder();
    const binaryData = encoder.encode(jsonString);
    const blob = new Blob([binaryData], { type: "application/octet-stream" });

    let safeDescription = description.trim() ? description.trim() : "session";
    let safeRecordingDate = recordingDate.trim()
      ? recordingDate.trim().replace(/[:]/g, "-")
      : new Date().toISOString().replace(/[:]/g, "-");

    if (!safeRecordingDate) {
      safeRecordingDate = new Date().toISOString().replace(/[:]/g, "-");
    }
    const filename = `${safeDescription}_${safeRecordingDate}.bin`;

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // ※ ここがポイント：ファイル選択ダイアログを開く前に value="" をセットし、二重呼び出しを回避
  const fileInputSessionRef = useRef<HTMLInputElement>(null);
  const openSessionFileDialog = () => {
    if (!fileInputSessionRef.current) return;
    // 連続で同じファイルを選択した場合でも onChange が発火するようにする
    fileInputSessionRef.current.value = "";
    // ダイアログを開く
    fileInputSessionRef.current.click();
  };

  const handleLoadSession = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const result = event.target?.result;
      if (result instanceof ArrayBuffer) {
        const decoder = new TextDecoder();
        const text = decoder.decode(result);
        try {
          const session = JSON.parse(text);
          if (session.audioData) {
            setFileBase64Data(session.audioData);
            setPastedBase64Data("");
          }
          setDescription(session.description || "");
          setRecordingDate(session.recordingDate || "");
          setTimedTranscript(session.timedTranscript || []);
        } catch (e) {
          alert("セッション読込エラー: " + e);
        }
      }
    };
    reader.readAsArrayBuffer(file);
  };

  // ===========================================================
  //  テキストのダウンロード & クリップボードコピー
  // ===========================================================
  // 単語(フレーズ)をスペース区切りで連結し、1行テキストを作成
  const getJoinedText = (): string => {
    return timedTranscript.map((seg) => seg.text).join(" ");
  };

  const [selectedEncoding, setSelectedEncoding] = useState("utf8");

  const handleDownload = () => {
    const textContent = getJoinedText();
    let blob;
    let filename = "transcription.txt";
    if (selectedEncoding === "utf8") {
      blob = new Blob([textContent], { type: "text/plain;charset=utf-8" });
    } else {
      const sjisArray = Encoding.convert(textContent, {
        to: "SJIS",
        type: "array",
      });
      blob = new Blob([new Uint8Array(sjisArray)], {
        type: "text/plain;charset=shift_jis",
      });
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

  const [copied, setCopied] = useState(false);
  const handleCopyToClipboard = async () => {
    const textContent = getJoinedText();
    try {
      await navigator.clipboard.writeText(textContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 500);
    } catch (error) {
      alert("コピーに失敗しました: " + error);
    }
  };

  // ===========================================================
  //  文字起こしテキスト中のカーソル連動
  // ===========================================================
  // 単語(フレーズ)をクリックしたらその時間へ
  const handleSegmentClick = (segment: TimedSegment) => {
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      }
      const stSec = timeStringToSeconds(segment.start_time);
      audioRef.current.currentTime = stSec;
      setSliderValue(stSec);
      setCurrentTime(stSec);
      setCursorTime(segment.start_time);
    }
  };

  // ダブルクリックでその時間から再生
  const handleSegmentDoubleClick = (segment: TimedSegment) => {
    if (audioRef.current) {
      const stSec = timeStringToSeconds(segment.start_time);
      audioRef.current.currentTime = stSec;
      setSliderValue(stSec);
      setCurrentTime(stSec);
      audioRef.current.play();
      setIsPlaying(true);
      setCursorTime(segment.start_time);
    }
  };

  return (
    <div className="p-4 overflow-y-auto bg-dark-primary text-white min-h-screen">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">音声文字起こし</h1>
        <button
          onClick={handleClearBoth}
          className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
        >
          クリア
        </button>
      </div>

      {/* セッション保存／読込 */}
      <div className="flex space-x-4 mb-6">
        <button
          onClick={handleSaveSession}
          className="bg-indigo-500 hover:bg-indigo-600 text-white font-bold py-2 px-4 rounded"
        >
          セッション保存
        </button>
        {/* ボタンを押すとダイアログを開く → onChangeで読込 */}
        <button
          onClick={openSessionFileDialog}
          className="bg-indigo-500 hover:bg-indigo-600 text-white font-bold py-2 px-4 rounded"
        >
          セッション読込
        </button>
        <input
          type="file"
          accept=".bin"
          ref={fileInputSessionRef}
          style={{ display: "none" }}
          onChange={handleLoadSession}
        />
      </div>

      {/* 説明・録音日 */}
      <div className="mb-6">
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-200">説明</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
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
            onChange={(e) => setRecordingDate(e.target.value)}
            placeholder="YYYY/mm/dd"
            className="w-full p-2 text-black"
          />
        </div>
      </div>

      {/* アップロード */}
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
            <input
              type="file"
              ref={fileInputRef}
              accept="audio/*"
              onChange={handleFileChange}
              className="hidden"
            />
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
            アップロードされたデータの先頭:{" "}
            <span className="text-green-300">{preview}</span>
          </p>
        </div>

        {audioInfo && (
          <div className="mb-4">
            <p className="text-sm">
              音声情報:{" "}
              {audioInfo.fileName && `ファイル名: ${audioInfo.fileName}, `}
              {audioInfo.duration !== undefined &&
                `再生時間: ${audioInfo.duration.toFixed(2)}秒, `}
              {audioInfo.fileSize !== null &&
                audioInfo.fileSize !== undefined &&
                `ファイルサイズ: ${(audioInfo.fileSize / 1024).toFixed(1)}KB, `}
              {audioInfo.mimeType && `MIMEタイプ: ${audioInfo.mimeType}`}
            </p>
          </div>
        )}
      </div>

      {/* 再生コントロール */}
      {audioInfo && (
        <div className="mb-6">
          <div className="flex items-center mb-4">
            <button
              onClick={handlePlayPause}
              className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded mr-4"
            >
              {isPlaying ? "一時停止" : "再生"}
            </button>
            <select
              value={playbackSpeed}
              onChange={(e) => {
                const speed = Number(e.target.value);
                setPlaybackSpeed(speed);
                if (audioRef.current) {
                  audioRef.current.playbackRate = speed;
                }
              }}
              className="p-2 text-black"
            >
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

          <div className="flex items-center space-x-2">
            <span className="w-16 text-right">
              {secondsToTimeString(sliderValue)}
            </span>
            <input
              type="range"
              min={0}
              max={audioInfo.duration.toFixed(2)}
              step={1}
              value={sliderValue}
              onChange={handleSliderChange}
              className="flex-1"
            />
            <span className="w-16">
              {audioInfo.duration
                ? secondsToTimeString(audioInfo.duration)
                : "00:00:00"}
            </span>
          </div>
        </div>
      )}

      {audioData && (
        <audio ref={audioRef} src={audioData} onTimeUpdate={handleTimeUpdate} />
      )}

      {/* 送信ボタン */}
      <button
        onClick={handleSend}
        disabled={isSending}
        className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded"
      >
        {isSending ? "処理中..." : "送信"}
      </button>

      {/* 文字起こし結果（単語/フレーズごと） */}
      <div className="mt-6">
        <h2 className="text-xl font-bold mb-2">文字起こし結果</h2>

        {timedTranscript.length > 0 && (
          <div
            className="p-2 bg-white text-black rounded"
            style={{ lineHeight: "1.8em", maxHeight: "300px", overflowY: "auto" }}
          >
            {/* すでに表示したタイムスタンプ秒数を記憶して、重複を避ける */}
            {(() => {
              let lastTimestampSec = -1;
              return timedTranscript.map((segment, index) => {
                const segmentStartSec = timeStringToSeconds(segment.start_time);
                const segmentEndSec = timeStringToSeconds(segment.end_time);

                // 現在時間がこのセグメントの範囲内かどうか
                const isActive =
                  currentTime >= segmentStartSec && currentTime < segmentEndSec;

                const style: React.CSSProperties = {
                  cursor: "pointer",
                  backgroundColor:
                    isActive || (cursorTime === segment.start_time)
                      ? "#ffd700"
                      : "transparent",
                  padding: "0 2px",
                  marginRight: "2px",
                };

                // タイムスタンプ表示の判定
                let timestampSpan: JSX.Element | null = null;
                if (
                  showTimestamps &&
                  segmentStartSec % 60 === 0 && // 1分毎
                  segmentStartSec !== lastTimestampSec // 直前と同じなら表示しない
                ) {
                  timestampSpan = (
                    <span className="mr-1 text-blue-700">
                      [{segment.start_time}]
                    </span>
                  );
                  lastTimestampSec = segmentStartSec;
                }

                return (
                  <span
                    key={index}
                    style={style}
                    onClick={() => handleSegmentClick(segment)}
                    onDoubleClick={() => handleSegmentDoubleClick(segment)}
                  >
                    {timestampSpan}
                    {segment.text}
                  </span>
                );
              });
            })()}
          </div>
        )}
      </div>

      {/* ダウンロード & コピー & エンコーディング選択 */}
      {timedTranscript.length > 0 && (
        <div className="mt-6 flex items-center space-x-4">
          <button
            onClick={handleDownload}
            className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded"
          >
            ダウンロード
          </button>

          <button
            onClick={handleCopyToClipboard}
            className={`bg-gray-500 hover:bg-gray-600 text-white font-bold py-2 px-4 rounded ${
              copied ? "animate-bounce" : ""
            }`}
          >
            クリップボードにコピー
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
      )}
    </div>
  );
};

export default SpeechToTextPage;
