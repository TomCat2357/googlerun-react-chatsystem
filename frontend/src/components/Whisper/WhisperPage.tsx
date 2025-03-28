// frontend/src/component/Whisper/WhisperPage.tsx
import React, { useState, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import { generateRequestId } from '../../utils/requestIdUtils';
import WhisperUploader from "./WhisperUploader";
import WhisperJobList from "./WhisperJobList";
import WhisperTranscriptPlayer from "./WhisperTranscriptPlayer";
import WhisperMetadataEditor from "./WhisperMetadataEditor";

interface Segment {
  start: number;
  end: number;
  text: string;
  speaker: string;
}

const WhisperPage: React.FC = () => {
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // 状態管理
  const [audioData, setAudioData] = useState<string>("");
  const [audioInfo, setAudioInfo] = useState<any>(null);
  const [description, setDescription] = useState<string>("");
  const [recordingDate, setRecordingDate] = useState<string>("");
  const [tags, setTags] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [jobs, setJobs] = useState<any[]>([]);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [jobData, setJobData] = useState<any>(null);
  const [view, setView] = useState<"upload" | "jobs">("upload");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [sortOrder, setSortOrder] = useState<string>("date-desc");
  const [refreshInterval, setRefreshInterval] = useState<number | null>(null);

  // 初回読み込み時にジョブ一覧を取得
  useEffect(() => {
    if (token) {
      fetchJobs();
      
      // 30秒ごとに自動更新する設定
      const interval = window.setInterval(() => {
        if (view === "jobs" && !selectedJob) {
          fetchJobs();
        }
      }, 30000); // 30秒ごと
      
      setRefreshInterval(interval);
      
      // コンポーネントのアンマウント時にインターバルをクリア
      return () => {
        if (refreshInterval) {
          window.clearInterval(refreshInterval);
        }
      };
    }
  }, [token]);
  
  // view変更時にも更新
  useEffect(() => {
    if (view === "jobs") {
      fetchJobs();
    }
  }, [view]);

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
      setErrorMessage("アップロードする音声ファイルを選択してください");
      return;
    }

    if (!audioInfo || !audioInfo.fileName) {
      setErrorMessage("音声データの情報が不完全です");
      return;
    }

    try {
      setIsUploading(true);
      setErrorMessage("");

      const requestId = generateRequestId();
      const requestData = {
        audio_data: audioData,
        filename: audioInfo.fileName,
        description: description,
        recording_date: recordingDate,
        tags: tags
      };

      const response = await fetch(`${API_BASE_URL}/backend/whisper`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        },
        body: JSON.stringify(requestData)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || `アップロードに失敗しました (${response.status})`);
      }

      const responseData = await response.json();
      
      // アップロード成功のメッセージを表示
      alert(`音声ファイルがアップロードされました。順番に処理が開始されます。`);
      
      // フォームをクリア
      setAudioData("");
      setAudioInfo(null);
      setDescription("");
      setRecordingDate("");
      setTags([]);
      
      // ジョブ一覧画面に切り替え
      setView("jobs");
      fetchJobs();
      
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
  const saveEditedTranscript = async (editedSegments: Segment[]) => {
    if (!selectedJob) return;
    
    try {
      setErrorMessage("");
      const requestId = generateRequestId();
      
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${selectedJob}/edit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        },
        body: JSON.stringify({ segments: editedSegments })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || `編集内容の保存に失敗しました (${response.status})`);
      }

      const data = await response.json();
      alert("編集内容を保存しました");
      
      // ジョブデータを更新
      setJobData({
        ...jobData,
        segments: editedSegments
      });
      
    } catch (error) {
      console.error("編集保存エラー:", error);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  // ジョブのキャンセル
  const cancelJob = async (jobId: string) => {
    if (!confirm("このジョブをキャンセルしますか？")) {
      return;
    }
    
    try {
      setErrorMessage("");
      const requestId = generateRequestId();
      
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${jobId}/cancel`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || `ジョブのキャンセルに失敗しました (${response.status})`);
      }

      alert("ジョブがキャンセルされました");
      fetchJobs();
      
    } catch (error) {
      console.error("キャンセルエラー:", error);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <div className="p-4 overflow-y-auto bg-dark-primary text-white min-h-screen">
      <h1 className="text-3xl font-bold mb-4">Whisper 音声文字起こし（バッチ処理）</h1>

      {/* エラーメッセージ */}
      {errorMessage && (
        <div className="mb-4 p-3 bg-red-700 text-white rounded flex justify-between items-center">
          <p>{errorMessage}</p>
          <button 
            onClick={() => setErrorMessage("")}
            className="text-white hover:text-gray-200"
          >
            ✕
          </button>
        </div>
      )}

      {/* 処理フロー説明（オプション） */}
      <div className="mb-4 p-3 bg-gray-800 rounded text-sm">
        <p><strong>処理フロー:</strong> 音声ファイルをアップロード → 自動的に処理キューに登録 → 順番に処理 → 処理完了後にメール通知</p>
      </div>

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
            onTagsChange={setTags}
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
              onDelete={cancelJob}
              filterStatus={filterStatus}
              onFilterChange={setFilterStatus}
              sortOrder={sortOrder}
              onSortChange={setSortOrder}
            />
          )}
        </div>
      )}
    </div>
  );
};

export default WhisperPage;