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

export interface TimedSegment {
  start_time: string; // "HH:MM:SS"形式
  end_time: string;
  text: string;
}

/**
 * "HH:MM:SS"形式の文字列を秒数に変換するヘルパー関数
 */
const timeStringToSeconds = (timeStr: string): number => {
  const parts = timeStr.split(":").map(Number);
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
};

/**
 * 秒数を "HH:MM:SS" 形式の文字列に変換するヘルパー関数
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

  // アップロード方法（ファイル選択 or Base64貼り付け）関連の状態
  const [uploadMode, setUploadMode] = useState<"file" | "base64">("file");
  const [fileBase64Data, setFileBase64Data] = useState("");
  const [pastedBase64Data, setPastedBase64Data] = useState("");
  const audioData = fileBase64Data || pastedBase64Data;
  const preview = audioData.substring(0, 30);
  const [outputText, setOutputText] = useState("");
  const [audioInfo, setAudioInfo] = useState<AudioInfo | null>(null);
  const [isSending, setIsSending] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 説明・録音日などのメタ情報
  const [description, setDescription] = useState("");
  const [recordingDate, setRecordingDate] = useState("");

  // 再生・タイムスタンプ関連の状態
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [timedTranscript, setTimedTranscript] = useState<TimedSegment[]>([]);
  const [cursorTime, setCursorTime] = useState<string | null>(null);
  const [showTimestamps, setShowTimestamps] = useState(false);

  const audioRef = useRef<HTMLAudioElement>(null);

  // ----- ファイルアップロード／Base64貼り付け処理 -----

  // ファイルの lastModified を "YYYY/mm/dd" 形式に変換する関数
  const formatDate = (timestamp: number): string => {
    const date = new Date(timestamp);
    const year = date.getFullYear();
    const month = ("0" + (date.getMonth() + 1)).slice(-2);
    const day = ("0" + date.getDate()).slice(-2);
    return `${year}/${month}/${day}`;
  };

  /**
   * ファイル選択／ドラッグ時の処理  
   * ファイル読み込み後、Base64文字列に変換し、  
   * 自動で説明（ファイル名）と録音日（最終更新日）を設定する。
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
    setOutputText("");
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

  // クリアボタン：全入力・結果・メタ情報をリセットする
  const handleClearBoth = () => {
    setFileBase64Data("");
    setPastedBase64Data("");
    setOutputText("");
    setAudioInfo(null);
    setDescription("");
    setRecordingDate("");
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

  // ----- タイムスタンプの１分毎挿入処理 -----
  const addMinuteTimestamps = (
    segments: TimedSegment[],
    duration: number
  ): TimedSegment[] => {
    const newSegments = [...segments];
    const existingTimes = newSegments.map(seg => timeStringToSeconds(seg.start_time));
    const totalMinutes = Math.floor(duration / 60);
    for (let m = 1; m <= totalMinutes; m++) {
      const markerTime = m * 60;
      // 近傍に既にタイムスタンプが存在しない場合に挿入
      if (!existingTimes.some(t => Math.abs(t - markerTime) < 5)) {
        newSegments.push({
          start_time: secondsToTimeString(markerTime),
          end_time: secondsToTimeString(markerTime),
          text: `[タイムスタンプ ${secondsToTimeString(markerTime)}]`
        });
      }
    }
    newSegments.sort(
      (a, b) => timeStringToSeconds(a.start_time) - timeStringToSeconds(b.start_time)
    );
    return newSegments;
  };

  // ----- 音声文字起こしリクエスト -----
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
          setOutputText("エラーが発生しました: " + data.error);
        } else {
          setOutputText(data.transcription);
          if (data.timed_transcription) {
            let segments: TimedSegment[] = data.timed_transcription;
            if (audioInfo && audioInfo.duration) {
              segments = addMinuteTimestamps(segments, audioInfo.duration);
            }
            setTimedTranscript(segments);
          }
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

  // ----- テキストダウンロード -----
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

  // ----- 再生／一時停止、再生速度等の操作 -----
  const handlePlayPause = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
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
      if (isPlaying) {
        setCursorTime(secondsToTimeString(current));
      }
    }
  };

  const handleSegmentClick = (segment: TimedSegment) => {
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      }
      const newTime = timeStringToSeconds(segment.start_time);
      audioRef.current.currentTime = newTime;
      setCursorTime(segment.start_time);
    }
  };

  const handleSegmentDoubleClick = (segment: TimedSegment) => {
    if (audioRef.current) {
      audioRef.current.currentTime = timeStringToSeconds(segment.start_time);
      audioRef.current.play();
      setIsPlaying(true);
      setCursorTime(segment.start_time);
    }
  };

  const handleSpeedChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const speed = Number(e.target.value);
    setPlaybackSpeed(speed);
    if (audioRef.current) {
      audioRef.current.playbackRate = speed;
    }
  };

  // ----- セッション（１件分）のバイナリ保存／読込機能 -----
  const handleSaveSession = () => {
    if (!audioData) {
      alert("保存する音声データがありません");
      return;
    }
    const session = {
      audioData,
      description,
      recordingDate,
      transcription: outputText,
      timedTranscript
    };
    const jsonString = JSON.stringify(session);
    const encoder = new TextEncoder();
    const binaryData = encoder.encode(jsonString);
    const blob = new Blob([binaryData], { type: "application/octet-stream" });
    const safeDescription = description.trim() ? description.trim() : "session";
    const safeRecordingDate = recordingDate.trim()
      ? recordingDate.trim().replace(/[:]/g, "-")
      : new Date().toISOString().replace(/[:]/g, "-");
    const filename = `${safeDescription}_${safeRecordingDate}.bin`;
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  const fileInputSessionRef = useRef<HTMLInputElement>(null);
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
          setOutputText(session.transcription || "");
          setTimedTranscript(session.timedTranscript || []);
        } catch (e) {
          alert("セッション読込エラー: " + e);
        }
      }
    };
    reader.readAsArrayBuffer(file);
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

      {/* セッション保存／読込用ボタン */}
      <div className="flex space-x-4 mb-6">
        <button
          onClick={handleSaveSession}
          className="bg-indigo-500 hover:bg-indigo-600 text-white font-bold py-2 px-4 rounded"
        >
          セッション保存
        </button>
        <label>
          <input
            type="file"
            accept=".bin"
            onChange={handleLoadSession}
            ref={fileInputSessionRef}
            className="hidden"
          />
          <span
            onClick={() => fileInputSessionRef.current?.click()}
            className="block bg-indigo-500 hover:bg-indigo-600 text-white font-bold py-2 px-4 rounded cursor-pointer"
          >
            セッション読込
          </span>
        </label>
      </div>

      {/* 説明と録音日の入力欄 */}
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

      {audioData && (
        <audio
          ref={audioRef}
          src={audioData}
          onTimeUpdate={handleTimeUpdate}
        />
      )}

      <button
        onClick={handleSend}
        disabled={isSending}
        className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded"
      >
        {isSending ? "処理中..." : "送信"}
      </button>

      {/* 文字起こし結果の表示 */}
      <div className="mt-6">
        <h2 className="text-xl font-bold mb-2">文字起こし結果</h2>
        <div className="p-2 bg-white text-black rounded" style={{ maxHeight: "300px", overflowY: "auto" }}>
          {timedTranscript.length > 0 ? (
            <div style={{ lineHeight: "1.8em" }}>
              {timedTranscript.map((segment, index) => {
                const segmentStartSec = timeStringToSeconds(segment.start_time);
                const segmentEndSec = timeStringToSeconds(segment.end_time);
                const isActive =
                  currentTime >= segmentStartSec && currentTime < segmentEndSec;
                const style: React.CSSProperties = {
                  cursor: "pointer",
                  backgroundColor: isActive || (cursorTime === segment.start_time)
                    ? "#ffd700"
                    : "transparent",
                  padding: "0 2px",
                  marginRight: "2px"
                };
                return (
                  <span
                    key={index}
                    style={style}
                    onClick={() => handleSegmentClick(segment)}
                    onDoubleClick={() => handleSegmentDoubleClick(segment)}
                  >
                    {showTimestamps && (
                      <span className="mr-1 text-blue-700">
                        [{segment.start_time}]
                      </span>
                    )}
                    {segment.text}
                  </span>
                );
              })}
            </div>
          ) : (
            <textarea value={outputText} readOnly className="w-full p-2 text-black" rows={6} />
          )}
        </div>
      </div>

      {/* ダウンロードとエンコーディング選択 */}
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
  );
};

export default SpeechToTextPage;
