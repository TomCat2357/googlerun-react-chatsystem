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

/**
 * 編集モード時のセグメントコンポーネント  
 * 初回マウント時に初期値を設定し、その後はユーザーの編集状態（DOM側）を維持する。
 */
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

  // 初回マウント時に初期値を設定（以降はDOM上の値を編集中に保持）
  useEffect(() => {
    if (spanRef.current) {
      spanRef.current.innerText = initialText;
    }
    // 初回のみ実行
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // ---------- 音声データ関連 ----------
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

  // ---------- 文字起こし結果関連 ----------
  const [serverTimedTranscript, setServerTimedTranscript] = useState<TimedSegment[]>([]);
  const [serverTranscript, setServerTranscript] = useState("");
  /**
   * 修正モードで編集されたテキストを保持する配列。
   * インデックスは `serverTimedTranscript` に対応。
   */
  const [editedTranscriptSegments, setEditedTranscriptSegments] = useState<string[]>([]);

  // ---------- 再生コントロール ----------
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [sliderValue, setSliderValue] = useState(0);

  // ---------- UI制御 ----------
  const [cursorTime, setCursorTime] = useState<string | null>(null);
  const [showTimestamps, setShowTimestamps] = useState(false);
  const [isSending, setIsSending] = useState(false);
  // 複数チャンク送信時の進捗
  const [progress, setProgress] = useState<{ current: number; total: number }>({ current: 0, total: 0 });

  // ---------- 修正モード ----------
  const [isEditMode, setIsEditMode] = useState(false);

  // ===========================================================
  //  ファイル選択 / Base64 貼り付け
  // ===========================================================
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

    // UIリセット
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

  // ===========================================================
  //  再生コントロール
  // ===========================================================
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

  // ===========================================================
  //  文字起こし送信処理（チャンク分割対応 + タイムスタンプ補正）
  // ===========================================================
  const handleSend = async () => {
    if (!audioData) {
      alert("送信するデータがありません");
      return;
    }
    setIsSending(true);

    let transcriptionAccumulator = "";
    let timedTranscriptionAccumulator: TimedSegment[] = [];

    const rawChunkSize = Config.SPEECH_CHUNK_SIZE || 524288000; // 500MBデフォルト
    // 25KB(=25600バイト)の倍数に調整
    const chunkSize = Math.floor(rawChunkSize / 25600) * 25600;

    let header = "";
    let base64Content = audioData;
    if (audioData.startsWith("data:")) {
      const parts = audioData.split(",");
      header = parts[0] + ",";
      base64Content = parts[1];
    }
    const binaryStr = atob(base64Content);
    const totalBytes = binaryStr.length;
    const totalChunks = Math.ceil(totalBytes / chunkSize);
    setProgress({ current: 0, total: totalChunks });

    // タイムスタンプを連続させるためのオフセット（秒）
    let chunkTimeOffsetSec = 0;

    // チャンクが1個しかない場合（SPEECH_CHUNK_SIZE以下）
    if (totalChunks <= 1) {
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
          if (!data.error) {
            if (data.transcription) {
              transcriptionAccumulator = data.transcription.trim();
            }
            if (data.timed_transcription) {
              timedTranscriptionAccumulator = data.timed_transcription;
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
    } else {
      // 複数チャンクに分割
      for (let i = 0; i < totalChunks; i++) {
        const start = i * chunkSize;
        const end = Math.min(start + chunkSize, totalBytes);
        const chunkBinary = binaryStr.slice(start, end);
        const chunkBase64 = btoa(chunkBinary);
        const chunkDataUrl = header + chunkBase64;

        // 進捗表示用
        setProgress({ current: i + 1, total: totalChunks });

        try {
          const response = await fetch(`${API_BASE_URL}/backend/speech2text`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ audio_data: chunkDataUrl }),
          });
          if (response.ok) {
            const data = await response.json();
            if (!data.error) {
              if (data.transcription) {
                transcriptionAccumulator += data.transcription.trim() + "\n";
              }
              if (data.timed_transcription) {
                // 取得したタイムスタンプをチャンクオフセット分ずらす
                for (let j = 0; j < data.timed_transcription.length; j++) {
                  const w = data.timed_transcription[j];
                  const stSec = timeStringToSeconds(w.start_time) + chunkTimeOffsetSec;
                  const edSec = timeStringToSeconds(w.end_time) + chunkTimeOffsetSec;
                  w.start_time = secondsToTimeString(stSec);
                  w.end_time = secondsToTimeString(edSec);
                }
                timedTranscriptionAccumulator = timedTranscriptionAccumulator.concat(
                  data.timed_transcription
                );

                // 今回のチャンクの最後のタイムスタンプを元に次チャンクのオフセットを更新
                const last = data.timed_transcription[data.timed_transcription.length - 1];
                chunkTimeOffsetSec = timeStringToSeconds(last.end_time);
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
      }
    }

    setServerTranscript(transcriptionAccumulator.trim());
    setServerTimedTranscript(timedTranscriptionAccumulator);

    // まだ編集配列が空であれば初期化
    if (editedTranscriptSegments.length === 0 && timedTranscriptionAccumulator.length > 0) {
      const newSegments = timedTranscriptionAccumulator.map(seg => seg.text.trim() || " ");
      setEditedTranscriptSegments(newSegments);
    }

    setIsSending(false);
  };

  // ===========================================================
  //  セッションの保存／読込
  // ===========================================================
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

  // ===========================================================
  //  テキストダウンロード & クリップボードコピー
  // ===========================================================
  const getJoinedText = (): string => {
    if (isEditMode) {
      return editedTranscriptSegments.map(seg => seg.trim()).join(" ");
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

  // ===========================================================
  //  「入力途中の文字列」は即座に state へ反映せず、確定時のみ反映
  // ===========================================================
  /**
   * フォーカスが外れた or Composition が終了したタイミングで
   * DOMのテキストを読み取り、editedTranscriptSegments に反映。
   */
  const handleSegmentFinalize = (
    e: React.FocusEvent<HTMLSpanElement> | React.CompositionEvent<HTMLSpanElement>,
    index: number
  ) => {
    // 修正モードでなければ何もしない
    if (!isEditMode) return;

    let newText = e.currentTarget.innerText;
    if (!newText.trim()) {
      newText = " ";
    }
    const newSegments = [...editedTranscriptSegments];
    newSegments[index] = newText;
    setEditedTranscriptSegments(newSegments);
  };

  // ===========================================================
  //  文字起こしテキスト中の再生コントロール
  // ===========================================================
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

      {/* セッション保存／読込とクリアボタン */}
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

      {/* 音声データのアップロード */}
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

      {/* サイドバー：説明・録音日と送信ボタン */}
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
          {isSending && progress.total > 1
            ? `処理中(${progress.current}/${progress.total})`
            : isSending
            ? "処理中..."
            : "送信"}
        </button>
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

            {/* タイムスタンプ表示ボタン */}
            <label className="ml-4 text-gray-200">
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

      {/* 文字起こし結果ヘッダー */}
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

          {/* ダウンロード & コピー & エンコーディング選択 */}
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
                copied
                  ? "bg-white text-black"
                  : "bg-gray-500 hover:bg-gray-600 text-white"
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
        </div>

        {/* 文字起こしテキスト本体 */}
        {serverTimedTranscript.length > 0 && (
          <div
            className="p-2 bg-white text-black rounded"
            style={{ lineHeight: "1.8em", maxHeight: "300px", overflowY: "auto" }}
          >
            {(() => {
              // ここで閾値（例：5分）を設定
              const thresholdMinutes = 1; // 例：5分
              let nextThresholdSec = thresholdMinutes * 60; // 次に挿入するタイムスタンプの秒数

              return serverTimedTranscript.map((segment, index) => {
                const segmentStartSec = timeStringToSeconds(segment.start_time);
                const segmentEndSec = timeStringToSeconds(segment.end_time);
                const isActive =
                  currentTime >= segmentStartSec && currentTime < segmentEndSec;

                // タイムスタンプマーカーの挿入（指定分数を超えた最初のチャンクにマーカーを付与）
                const markerElements = [];
                if (showTimestamps) {
                  // もし1セグメントが複数の閾値をまたぐ場合にも対応
                  while (segmentStartSec >= nextThresholdSec) {
                    markerElements.push(
                      <span
                        key={`marker-${index}-${nextThresholdSec}`}
                        className="mr-1 text-blue-700"
                      >
                        {`{${secondsToTimeString(nextThresholdSec)}}`}
                      </span>
                    );
                    nextThresholdSec += thresholdMinutes * 60;
                  }
                }

                // 修正モード/非修正モードに応じたハイライト色設定
                const activeColor = isEditMode ? "#32CD32" : "#ffd700";
                const inactiveColor = isEditMode ? "#B0E57C" : "#fff8b3";
                const highlightStyle: React.CSSProperties = {
                  backgroundColor:
                    isActive || (cursorTime === segment.start_time)
                      ? activeColor
                      : inactiveColor,
                  marginRight: "4px",
                  padding: "2px 4px",
                  borderRadius: "4px",
                  cursor: "pointer",
                  display: "inline-block",
                  whiteSpace: "pre",
                };

                return (
                  <React.Fragment key={index}>
                    {markerElements}
                    {isEditMode ? (
                      <EditableSegment
                        index={index}
                        initialText={editedTranscriptSegments[index] ?? segment.text}
                        onFinalize={handleSegmentFinalize}
                        onClick={() => handleSegmentClick(segment)}
                        onDoubleClick={() => handleSegmentDoubleClick(segment)}
                        style={highlightStyle}
                      />
                    ) : (
                      <span
                        style={highlightStyle}
                        onClick={() => handleSegmentClick(segment)}
                        onDoubleClick={() => handleSegmentDoubleClick(segment)}
                      >
                        {segment.text}
                      </span>
                    )}
                  </React.Fragment>
                );
              });
            })()}
          </div>
        )}
      </div>
    </div>
  );
};

export default SpeechToTextPage;
