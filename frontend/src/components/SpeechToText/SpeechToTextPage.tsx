// frontend/src/components/SpeechToText/SpeechToTextPage.tsx

import React, { useState, useRef, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import Encoding from "encoding-japanese";
import { sendChunkedRequest } from "../../utils/ChunkedUpload";
import TranscriptDisplay from "./TranscriptDisplay"; // 新規コンポーネントをインポート

interface AudioInfo {
  duration: number;
  fileName?: string;
  fileSize?: number | null;
  mimeType?: string;
}

export interface TimedSegment {
  start_time: string; // "HH:MM:SS"
  end_time: string;   // "HH:MM:SS"
  text: string;
}

const timeStringToSeconds = (timeStr: string): number => {
  const parts = timeStr.split(":").map(Number);
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
};

const secondsToTimeString = (seconds: number): string => {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  return `${hrs.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

interface EditableSegmentProps {
  initialText: string;
  index: number;
  onFinalize: (
    e: React.FocusEvent<HTMLSpanElement> | React.CompositionEvent<HTMLSpanElement>,
    index: number
  ) => void;
  onClick: () => void;
  onDoubleClick: () => void;
  style: React.CSSProperties;
}

const EditableSegment: React.FC<EditableSegmentProps> = ({
  initialText,
  index,
  onFinalize,
  onClick,
  onDoubleClick,
  style,
}) => {
  const spanRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (spanRef.current) {
      spanRef.current.innerText = initialText;
    }
  }, [initialText]);

  return (
    <span
      ref={spanRef}
      contentEditable
      suppressContentEditableWarning
      style={style}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
        }
      }}
      onBlur={(e) => onFinalize(e, index)}
      onCompositionEnd={(e) => onFinalize(e, index)}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
    />
  );
};

const SpeechToTextPage = () => {
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // 音声データ関連
  const [uploadMode, setUploadMode] = useState<"file" | "base64">("file");
  const [fileBase64Data, setFileBase64Data] = useState("");
  const [pastedBase64Data, setPastedBase64Data] = useState("");
  const audioData = fileBase64Data || pastedBase64Data;
  const preview = audioData.substring(0, 30);

  const [audioInfo, setAudioInfo] = useState<AudioInfo | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  // メタ情報
  const [description, setDescription] = useState("");
  const [recordingDate, setRecordingDate] = useState("");

  // 文字起こし結果関連
  const [serverTimedTranscript, setServerTimedTranscript] = useState<TimedSegment[]>([]);
  const [serverTranscript, setServerTranscript] = useState("");
  const [editedTranscriptSegments, setEditedTranscriptSegments] = useState<string[]>([]);

  // 再生コントロール
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [sliderValue, setSliderValue] = useState(0);

  // UI制御
  const [cursorTime, setCursorTime] = useState<string | null>(null);
  const [showTimestamps, setShowTimestamps] = useState(false);
  const [isSending, setIsSending] = useState(false);

  // 修正モード
  const [isEditMode, setIsEditMode] = useState(false);

  const formatDate = (timestamp: number): string => {
    const date = new Date(timestamp);
    const year = date.getFullYear();
    const month = ("0" + (date.getMonth() + 1)).slice(-2);
    const day = ("0" + date.getDate()).slice(-2);
    return `${year}/${month}/${day}`;
  };

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

    setFileBase64Data(fileData);
    setPastedBase64Data("");
    setServerTimedTranscript([]);
    setServerTranscript("");
    setEditedTranscriptSegments([]);
    setCursorTime(null);

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
    setServerTimedTranscript([]);
    setServerTranscript("");
    setEditedTranscriptSegments([]);
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

  // 修正：音声データ送信時は共通のチャンクアップロード関数を利用し、手動のセグメント分割は行わない
  const handleSend = async () => {
    if (!audioData) {
      alert("送信するデータがありません");
      return;
    }
    if (audioInfo && audioInfo.duration > Config.SPEECH_MAX_SECONDS) {
      alert(`音声ファイルが長すぎます。${Math.floor(Config.SPEECH_MAX_SECONDS / 60)}分以内のファイルのみ送信可能です。分割してからアップロードしてください。`);
      return;
    }
    setIsSending(true);
    try {
      const payload = { audio_data: audioData };
      const response = await sendChunkedRequest(payload, token, `${API_BASE_URL}/backend/speech2text`);
      if (response.ok) {
        const data = await response.json();
        if (!data.error) {
          setServerTranscript(data.transcription ? data.transcription.trim() : "");
          setServerTimedTranscript(data.timed_transcription || []);
          if (editedTranscriptSegments.length === 0 && data.timed_transcription && data.timed_transcription.length > 0) {
            const newSegments = data.timed_transcription.map((seg: TimedSegment) => seg.text.trim() || " ");
            setEditedTranscriptSegments(newSegments);
          }
        } else {
          console.error("Speech2Text error:", data.error);
        }
      } else {
        console.error("サーバーエラー");
      }
    } catch (error) {
      console.error(error);
    }
    setIsSending(false);
  };

  const handleClearBoth = () => {
    setFileBase64Data("");
    setPastedBase64Data("");
    setAudioInfo(null);
    setDescription("");
    setRecordingDate("");
    setServerTimedTranscript([]);
    setServerTranscript("");
    setEditedTranscriptSegments([]);
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
      serverTimedTranscript,
      serverTranscript,
      editedTranscriptSegments,
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

  const fileInputSessionRef = useRef<HTMLInputElement>(null);
  const openSessionFileDialog = () => {
    if (!fileInputSessionRef.current) return;
    fileInputSessionRef.current.value = "";
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
            const audio = new Audio();
            audio.src = session.audioData;
            audio.onloadedmetadata = () => {
              setAudioInfo({
                duration: audio.duration,
                fileName: session.description || "Session Audio",
                fileSize: null,
                mimeType: audio.src.substring(5, audio.src.indexOf(";")),
              });
              setSliderValue(0);
            };
          }
          setDescription(session.description || "");
          setRecordingDate(session.recordingDate || "");
          if (session.serverTranscript) {
            setServerTranscript(session.serverTranscript);
          }
          if (session.serverTimedTranscript) {
            setServerTimedTranscript(session.serverTimedTranscript);
          }
          if (session.editedTranscriptSegments) {
            setEditedTranscriptSegments(session.editedTranscriptSegments);
          }
          setCursorTime(null);
        } catch (e) {
          alert("セッション読込エラー: " + e);
        }
      }
    };
    reader.readAsArrayBuffer(file);
  };

  const getJoinedText = (): string => {
    if (isEditMode) {
      return editedTranscriptSegments.map(seg => seg.trim()).join("");
    } else {
      return serverTranscript.trim();
    }
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

  const handleSegmentFinalize = (
    e: React.FocusEvent<HTMLSpanElement> | React.CompositionEvent<HTMLSpanElement>,
    index: number
  ) => {
    if (!isEditMode) return;
    let newText = e.currentTarget.innerText;
    if (!newText.trim()) {
      newText = " ";
    }
    const newSegments = [...editedTranscriptSegments];
    newSegments[index] = newText;
    setEditedTranscriptSegments(newSegments);
  };

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
      <h1 className="text-3xl font-bold mb-4">音声文字起こし</h1>

      <div className="flex justify-between items-center mb-6">
        <div className="flex space-x-4">
          <button
            onClick={handleSaveSession}
            className="bg-indigo-500 hover:bg-indigo-600 text-white font-bold py-2 px-4 rounded"
          >
            セッション保存
          </button>
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
        <button
          onClick={handleClearBoth}
          className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
        >
          クリア
        </button>
      </div>

      <div className="mb-6">
        <h2 className="text-xl font-bold mb-2">音声データのアップロード</h2>
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
            /> ファイル選択
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
            /> Base64貼り付け
          </label>
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
            アップロードされたデータの先頭: <span className="text-green-300">{preview}</span>
          </p>
        </div>

        {audioInfo && (
          <div className="mb-4">
            <p className="text-sm">
              音声情報: {audioInfo.fileName && `ファイル名: ${audioInfo.fileName}, `}
              {audioInfo.duration !== undefined && `再生時間: ${audioInfo.duration.toFixed(2)}秒, `}
              {audioInfo.fileSize !== null && audioInfo.fileSize !== undefined && `ファイルサイズ: ${(audioInfo.fileSize / 1024).toFixed(1)}KB, `}
              {audioInfo.mimeType && `MIMEタイプ: ${audioInfo.mimeType}`}
            </p>
          </div>
        )}
      </div>

      <div className="border border-gray-400 rounded p-4 mb-6 flex flex-col justify-end" style={{ minHeight: "150px" }}>
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
            placeholder="YYYY/MM/dd"
            className="w-full p-2 text-black"
          />
        </div>
        <button
          onClick={handleSend}
          disabled={isSending}
          className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded"
        >
          {isSending ? "処理中..." : "送信"}
        </button>
      </div>

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
            <label className="ml-4 text-gray-200">
              <input
                type="checkbox"
                checked={showTimestamps}
                onChange={() => setShowTimestamps(!showTimestamps)}
              /> タイムスタンプ表示
            </label>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-16 text-right">{secondsToTimeString(sliderValue)}</span>
            <input
              type="range"
              min={0}
              max={audioInfo.duration.toFixed(2)}
              step={1}
              value={sliderValue}
              onChange={handleSliderChange}
              className="flex-1"
            />
            <span className="w-16">{audioInfo.duration ? secondsToTimeString(audioInfo.duration) : "00:00:00"}</span>
          </div>
        </div>
      )}

      {audioData && (
        <audio ref={audioRef} src={audioData} onTimeUpdate={handleTimeUpdate} />
      )}

      <div className="mt-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            <h2 className="text-xl font-bold mr-4">文字起こし結果</h2>
            <label className="flex items-center text-gray-200">
              <input
                type="checkbox"
                checked={isEditMode}
                onChange={(e) => setIsEditMode(e.target.checked)}
                className="mr-2"
              />
              修正モード
            </label>
          </div>
          <div className="flex items-center space-x-4">
            <button
              onClick={handleDownload}
              className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded"
            >
              ダウンロード
            </button>
            <button
              onClick={handleCopyToClipboard}
              className={`font-bold py-2 px-4 rounded transition-colors duration-300 ${
                copied ? "bg-white text-black" : "bg-gray-500 hover:bg-gray-600 text-white"
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
                /> UTF-8
              </label>
              <label className="text-gray-200">
                <input
                  type="radio"
                  name="encoding"
                  value="shift-jis"
                  checked={selectedEncoding === "shift-jis"}
                  onChange={() => setSelectedEncoding("shift-jis")}
                /> Shift-JIS
              </label>
            </div>
          </div>
        </div>
        {/* ここはTranscriptDisplayコンポーネントに切り出しました */}
        {serverTimedTranscript.length > 0 && (
          <TranscriptDisplay 
            segments={serverTimedTranscript}
            isEditMode={isEditMode}
            editedTranscriptSegments={editedTranscriptSegments}
            onSegmentFinalize={handleSegmentFinalize}
            onSegmentClick={handleSegmentClick}
            onSegmentDoubleClick={handleSegmentDoubleClick}
            currentTime={currentTime}
            cursorTime={cursorTime}
            showTimestamps={showTimestamps}
          />
        )}
      </div>
    </div>
  );
};

export default SpeechToTextPage;
