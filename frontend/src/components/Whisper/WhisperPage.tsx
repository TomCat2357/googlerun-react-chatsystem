// frontend/src/component/Whisper/WhisperPage.tsx
import React, { useState, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import { generateRequestId } from '../../utils/requestIdUtils';
import WhisperUploader from "./WhisperUploader";
import WhisperJobList from "./WhisperJobList";
import WhisperTranscriptPlayer from "./WhisperTranscriptPlayer";
import WhisperMetadataEditor from "./WhisperMetadataEditor";

const WhisperPage: React.FC = () => {
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // 状態管理
  const [audioData, setAudioData] = useState<string>("");
  const [audioInfo, setAudioInfo] = useState<any>(null);
  const [description, setDescription] = useState<string>("");
  const [recordingDate, setRecordingDate] = useState<string>("");
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [jobs, setJobs] = useState<any[]>([]);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [jobData, setJobData] = useState<any>(null);
  const [view, setView] = useState<"upload" | "jobs">("upload");

  // 初回読み込み時にジョブ一覧を取得
  useEffect(() => {
    if (token) {
      fetchJobs();
    }
  }, [token]);

  // ジョブ一覧を取得
  const fetchJobs = async () => {
    try {
      const requestId = generateRequestId();
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        }
      });

      if (!response.ok) {
        throw new Error(`ジョブ一覧の取得に失敗しました (${response.status})`);
      }

      const data = await response.json();
      setJobs(data.jobs || []);
    } catch (error) {
      console.error("ジョブ一覧取得エラー:", error);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  // 音声アップロード処理
  const handleUpload = async () => {
    if (!audioData) {
      setErrorMessage("アップロードする音声データがありません");
      return;
    }

    setIsUploading(true);
    setErrorMessage("");

    try {
      // Base64の先頭部分を処理
      let base64Data = audioData;
      if (base64Data.startsWith('data:')) {
        base64Data = base64Data.split(',')[1];
      }

      const requestId = generateRequestId();
      const response = await fetch(`${API_BASE_URL}/backend/whisper`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        },
        body: JSON.stringify({
          audio_data: base64Data,
          filename: audioInfo?.fileName || "recorded_audio.wav",
          description: description,
          recording_date: recordingDate
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || `アップロードに失敗しました (${response.status})`);
      }

      const responseData = await response.json();

      // アップロード成功
      alert("音声ファイルのアップロードが完了しました。処理が終わり次第メールで通知されます。");

      // 状態をリセット
      setAudioData("");
      setAudioInfo(null);
      setDescription("");
      setRecordingDate("");

      // ジョブ一覧を更新して表示
      await fetchJobs();
      setView("jobs");
    } catch (error) {
      console.error("アップロードエラー:", error);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setIsUploading(false);
    }
  };

  // ジョブ詳細を取得
  const fetchJobDetails = async (jobId: string) => {
    try {
      setErrorMessage("");

      const requestId = generateRequestId();
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${jobId}`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        }
      });

      if (!response.ok) {
        throw new Error(`ジョブ詳細の取得に失敗しました (${response.status})`);
      }

      const data = await response.json();
      setJobData(data);
      setSelectedJob(jobId);
    } catch (error) {
      console.error("ジョブ詳細取得エラー:", error);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  // 編集内容を保存
  // 編集内容を保存
  const saveEditedTranscript = async (editedSegments: Segment[]) => {
    if (!selectedJob) return;

    try {
      const requestId = generateRequestId();
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${selectedJob}/edit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        },
        body: JSON.stringify({
          segments: editedSegments.map(seg => ({
            start: seg.start,
            end: seg.end,
            text: seg.text,
            speaker: seg.speaker
          }))
        })
      });

      if (!response.ok) {
        throw new Error(`編集内容の保存に失敗しました (${response.status})`);
      }

      alert("編集内容を保存しました");
      // 最新の内容を再取得
      await fetchJobDetails(selectedJob);
    } catch (error) {
      console.error("編集保存エラー:", error);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };
  return (
    <div className="p-4 overflow-y-auto bg-dark-primary text-white min-h-screen">
      <h1 className="text-3xl font-bold mb-4">Whisper 音声文字起こし（バッチ処理）</h1>

      {/* エラーメッセージ */}
      {errorMessage && (
        <div className="mb-4 p-3 bg-red-700 text-white rounded">
          <p>{errorMessage}</p>
        </div>
      )}

      {/* タブ切り替え */}
      <div className="flex mb-6 border-b border-gray-600">
        <button
          className={`px-4 py-2 mr-2 ${view === "upload" ? "bg-blue-600 text-white rounded-t" : "text-gray-300"}`}
          onClick={() => setView("upload")}
        >
          音声アップロード
        </button>
        <button
          className={`px-4 py-2 ${view === "jobs" ? "bg-blue-600 text-white rounded-t" : "text-gray-300"}`}
          onClick={() => {
            setView("jobs");
            fetchJobs();
          }}
        >
          処理結果一覧
        </button>
      </div>

      {/* 音声アップロード画面 */}
      {view === "upload" && (
        <div>
          <WhisperUploader
            onAudioDataChange={setAudioData}
            onAudioInfoChange={setAudioInfo}
            onDescriptionChange={setDescription}
            onRecordingDateChange={setRecordingDate}
          />

          <WhisperMetadataEditor
            description={description}
            recordingDate={recordingDate}
            isSending={isUploading}
            onDescriptionChange={setDescription}
            onRecordingDateChange={setRecordingDate}
            onSend={handleUpload}
          />
        </div>
      )}

      {/* ジョブ一覧と結果表示画面 */}
      {view === "jobs" && (
        <div>
          {selectedJob ? (
            // ジョブ詳細・再生画面
            <div>
              <button
                onClick={() => setSelectedJob(null)}
                className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded mb-4"
              >
                ← 一覧に戻る
              </button>

              {jobData && (
                <WhisperTranscriptPlayer
                  jobData={jobData}
                  onSaveEdit={saveEditedTranscript}
                />
              )}
            </div>
          ) : (
            // ジョブ一覧
            <WhisperJobList
              jobs={jobs}
              onJobSelect={fetchJobDetails}
              onRefresh={fetchJobs}
            />
          )}
        </div>
      )}
    </div>
  );
};

export default WhisperPage;