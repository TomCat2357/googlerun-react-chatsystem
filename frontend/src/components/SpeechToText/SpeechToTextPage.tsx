// frontend/src/components/SpeechToText/SpeechToTextPage.tsx
import React, { useState, useRef, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import { sendChunkedRequest } from "../../utils/ChunkedUpload";
import AudioUploader, { AudioInfo } from "./AudioUploader";
import MetadataEditor from "./MetadataEditor";
import AudioTranscriptPlayer, { TimedSegment } from "./AudioTranscriptPlayer";
import TranscriptExporter from "./TranscriptExporter";


const SpeechToTextPage = () => {

  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // 音声データ関連
  const [audioData, setAudioData] = useState("");
  const [audioInfo, setAudioInfo] = useState<AudioInfo | null>(null);

  // メタ情報
  const [description, setDescription] = useState("");
  const [recordingDate, setRecordingDate] = useState("");

  // 文字起こし結果関連
  const [serverTimedTranscript, setServerTimedTranscript] = useState<TimedSegment[]>([]);
  const [serverTranscript, setServerTranscript] = useState("");
  const [isEditMode, setIsEditMode] = useState(false);
  // 追加: 編集内容の状態
  const [editedTranscriptSegments, setEditedTranscriptSegments] = useState<string[]>([]);

  // UI制御
  const [isSending, setIsSending] = useState(false);

  // ファイル参照
  const fileInputSessionRef = useRef<HTMLInputElement>(null);

  // トランスクリプションが変更されたときに編集セグメントも初期化
  useEffect(() => {
    if (serverTimedTranscript.length > 0 && editedTranscriptSegments.length === 0) {
      const newSegments = serverTimedTranscript.map(
        (seg) => seg.text.trim() || " "
      );
      setEditedTranscriptSegments(newSegments);
    }
  }, [serverTimedTranscript, editedTranscriptSegments.length]);

  // テキストの結合テキストを取得する関数
  const getTranscriptText = (): string => {
    if (isEditMode && editedTranscriptSegments.length > 0) {
      // 修正モードの内容を返す
      return editedTranscriptSegments.map((seg) => seg.trim()).join("");
    } else {
      // 通常モードの内容を返す
      return serverTranscript.trim();
    }
  };

  // セッション保存・読み込み
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
      editedTranscriptSegments, // 編集内容も保存
    };
    
    const jsonString = JSON.stringify(session);
    const encoder = new TextEncoder();
    const binaryData = encoder.encode(jsonString);
    const blob = new Blob([binaryData], { type: "application/octet-stream" });

    let safeDescription = description.trim() ? description.trim() : "session";
    let safeRecordingDate = recordingDate.trim()
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
            setAudioData(session.audioData);
            const audio = new Audio();
            audio.src = session.audioData;
            audio.onloadedmetadata = () => {
              setAudioInfo({
                duration: audio.duration,
                fileName: session.description || "Session Audio",
                fileSize: null,
                mimeType: audio.src.substring(5, audio.src.indexOf(";")),
              });
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
        } catch (e) {
          alert("セッション読込エラー: " + e);
        }
      }
    };
    reader.readAsArrayBuffer(file);
  };

  // 全体のクリア
  const handleClearBoth = () => {
    setAudioData("");
    setAudioInfo(null);
    setDescription("");
    setRecordingDate("");
    setServerTimedTranscript([]);
    setServerTranscript("");
    setEditedTranscriptSegments([]);
    setIsEditMode(false);
  };

  // 音声送信処理
  const handleSend = async () => {
    if (!audioData) {
      alert("送信するデータがありません");
      return;
    }
    
    if (audioInfo && audioInfo.duration > Config.getServerConfig().SPEECH_MAX_SECONDS) {
      alert(
        `音声ファイルが長すぎます。${Math.floor(
          Config.getServerConfig().SPEECH_MAX_SECONDS / 60
        )}分以内のファイルのみ送信可能です。分割してからアップロードしてください。`
      );
      return;
    }
    
    setIsSending(true);
    try {
      // audioDataにはbase64形式の音声データが含まれている
      // Base64のヘッダー部分（data:audio/...;base64,）を除去
      let base64Data = audioData;
      if (base64Data.startsWith('data:')) {
        base64Data = base64Data.split(',')[1];
      }
      
      const payload = { audio_data: base64Data };
      const response = await sendChunkedRequest(
        payload,
        token,
        `${API_BASE_URL}/backend/speech2text`
      );
      
      if (response.ok) {
        const data = await response.json();
        if (!data.error) {
          setServerTranscript(
            data.transcription ? data.transcription.trim() : ""
          );
          setServerTimedTranscript(data.timed_transcription || []);
          // 新しい文字起こし結果を受け取ったら編集セグメントをリセット
          setEditedTranscriptSegments([]);
          setIsEditMode(false);
        } else {
          console.error("Speech2Text error:", data.error);
          alert("文字起こしエラー: " + data.error);
        }
      } else {
        console.error("サーバーエラー:", response.status);
        alert("サーバーエラー: " + response.status);
      }
    } catch (error) {
      console.error("送信エラー:", error);
      alert("送信中にエラーが発生しました: " + (error instanceof Error ? error.message : String(error)));
    } finally {
      setIsSending(false);
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

      {/* アップローダーコンポーネント */}
      <AudioUploader
        onAudioDataChange={setAudioData}
        onAudioInfoChange={setAudioInfo}
        onDescriptionChange={setDescription}
        onRecordingDateChange={setRecordingDate}
      />

      {/* 音声情報の表示 */}
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

      {/* メタデータ編集コンポーネント */}
      <MetadataEditor
        description={description}
        recordingDate={recordingDate}
        isSending={isSending}
        onDescriptionChange={setDescription}
        onRecordingDateChange={setRecordingDate}
        onSend={handleSend}
      />

      {/* オーディオプレーヤーと文字起こし表示コンポーネント */}
      {audioInfo && (
        <AudioTranscriptPlayer
          audioData={audioData}
          audioInfo={audioInfo}
          serverTimedTranscript={serverTimedTranscript}
          serverTranscript={serverTranscript}
          isEditMode={isEditMode}
          onEditModeChange={setIsEditMode}
          editedTranscriptSegments={editedTranscriptSegments}
          onEditedTranscriptChange={setEditedTranscriptSegments}
        />
      )}

      {/* エクスポート機能 */}
      {serverTimedTranscript.length > 0 && (
        <div className="mt-4">
          <TranscriptExporter getTranscriptText={getTranscriptText} />
        </div>
      )}
    </div>
  );
};

export default SpeechToTextPage;