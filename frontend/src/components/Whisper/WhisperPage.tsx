// frontend/src/component/Whisper/WhisperPage.tsx
import React, { useState, useEffect, useRef } from "react";
import { useToken } from "../../hooks/useToken";
import { useAuth } from "../../contexts/AuthContext";
import * as Config from "../../config";
import { generateRequestId } from '../../utils/requestIdUtils';
import WhisperUploader from "./WhisperUploader";
import WhisperJobList from "./WhisperJobList";
import WhisperTranscriptPlayer from "./WhisperTranscriptPlayer";
import WhisperMetadataEditor from "./WhisperMetadataEditor";
import { WhisperUploadRequest, WhisperSegment } from "../../types/apiTypes";

const WhisperPage: React.FC = () => {
  const token = useToken();
  const { currentUser, loading } = useAuth();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // 状態管理
  const [audioData, setAudioData] = useState<string>("");
  const [audioInfo, setAudioInfo] = useState<any>(null);
  const [description, setDescription] = useState<string>("");
  const [recordingDate, setRecordingDate] = useState<string>("");
  const [tags, setTags] = useState<string[]>([]);
  const [language, setLanguage] = useState<string>("ja");
  const [initialPrompt, setInitialPrompt] = useState<string>("");
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [jobs, setJobs] = useState<any[]>([]);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [selectedHash, setSelectedHash] = useState<string | null>(null);
  const [jobData, setJobData] = useState<any>(null);
  const [view, setView] = useState<"upload" | "jobs">("upload");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [sortOrder, setSortOrder] = useState<string>("date-desc");
  const [refreshInterval, setRefreshInterval] = useState<number | null>(null);
  
  // フロントエンドフィルタリング用の追加状態
  const [searchKeyword, setSearchKeyword] = useState<string>("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [availableTags, setAvailableTags] = useState<string[]>([]);

  // インターバル参照用のrefを追加
  const intervalId = useRef<number | null>(null);
  
  // フロントエンドでジョブをフィルタリングする関数
  const filterJobs = (allJobs: any[]) => {
    if (!allJobs || allJobs.length === 0) return [];
    
    return allJobs.filter(job => {
      // ステータスでフィルタリング（WhisperJobListコンポーネントでも行うが、両方で適用して確実にする）
      if (filterStatus !== "all" && job.status !== filterStatus) {
        return false;
      }
      
      // キーワードでフィルタリング
      if (searchKeyword && searchKeyword.trim() !== "") {
        const keyword = searchKeyword.toLowerCase();
        // ファイル名とタグでの検索
        const matchesFilename = job.filename && job.filename.toLowerCase().includes(keyword);
        const matchesTags = job.tags && job.tags.some((tag: string) => tag.toLowerCase().includes(keyword));
        
        if (!matchesFilename && !matchesTags) {
          return false;
        }
      }
      
      // 日付範囲でフィルタリング
      if (dateFrom) {
        const fromDate = new Date(dateFrom);
        const jobDate = new Date(job.createdAt);
        if (jobDate < fromDate) {
          return false;
        }
      }
      
      if (dateTo) {
        const toDate = new Date(dateTo);
        toDate.setHours(23, 59, 59, 999); // その日の終わりにする
        const jobDate = new Date(job.createdAt);
        if (jobDate > toDate) {
          return false;
        }
      }
      
      // 選択されたタグでフィルタリング
      if (selectedTags.length > 0) {
        if (!job.tags) return false;
        
        // すべての選択されたタグを含む必要がある（AND検索）
        const hasAllTags = selectedTags.every(selectedTag => 
          job.tags.some((tag: string) => tag === selectedTag)
        );
        
        if (!hasAllTags) {
          return false;
        }
      }
      
      return true;
    });
  };

  // 初回読み込み時にジョブ一覧を取得
  useEffect(() => {
    // ローディング中の場合は処理を待機
    if (loading) {
      return;
    }
    
    // 認証されたユーザーとトークンが存在する場合のみ処理を実行
    if (currentUser && token) {
      fetchJobs();
      
      // 既存のインターバルをクリア
      if (intervalId.current) {
        window.clearInterval(intervalId.current);
      }
      
      // 自動更新を無効化（手動更新ボタンに置き換え）
      
      // コンポーネントのアンマウント時にインターバルをクリア
      return () => {
        if (intervalId.current) {
          window.clearInterval(intervalId.current);
        }
      };
    }
  }, [currentUser, token, loading, view]); // 認証状態とローディング状態も監視
  
  // view変更時にも更新
  useEffect(() => {
    // 認証状態とトークンをチェックしてからAPIを呼び出し
    if (view === "jobs" && currentUser && token && !loading) {
      fetchJobs();
    }
  }, [view, currentUser, token, loading]);

  // ジョブ一覧を取得
  const fetchJobs = async () => {
    try {
      const requestId = generateRequestId();
      
      // すべてのジョブを取得（フィルタリングはフロントエンドで行う）
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
      const jobsList = data.jobs || [];
      setJobs(jobsList);
      
      // 利用可能なタグのリストを抽出
      const tagsSet = new Set<string>();
      jobsList.forEach((job: any) => {
        if (job.tags && Array.isArray(job.tags)) {
          job.tags.forEach((tag: string) => {
            tagsSet.add(tag);
          });
        }
      });
      
      setAvailableTags(Array.from(tagsSet).sort());
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
    
    // ファイルサイズチェック
    if (audioInfo.fileSize && audioInfo.fileSize > Config.getServerConfig().WHISPER_MAX_BYTES) {
      setErrorMessage(`音声ファイルが大きすぎます（最大${Math.floor(Config.getServerConfig().WHISPER_MAX_BYTES/1024/1024)}MB）`);
      return;
    }
    
    // 音声長さチェック
    if (audioInfo.duration > Config.getServerConfig().WHISPER_MAX_SECONDS) {
      setErrorMessage(`音声の長さが制限を超えています（最大${Math.floor(Config.getServerConfig().WHISPER_MAX_SECONDS/60)}分）`);
      return;
    }

    try {
      setIsUploading(true);
      setErrorMessage("");

      const requestId = generateRequestId();
      const requestData: WhisperUploadRequest = {
        gcsObject: audioData.startsWith("gs://") ? audioData.substring(5) : audioData,
        originalName: audioInfo.fileName,
        description: description,
        recordingDate: recordingDate,
        tags: tags,
        language: language,
        initialPrompt: initialPrompt
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
      
      // レスポンスからjobIdとfileHashを取得
      const jobId = responseData.jobId;
      const fileHash = responseData.fileHash;
      
      // アップロード成功のメッセージを表示
      alert(`音声ファイルがアップロードされました。順番に処理が開始されます。`);
      
      // フォームをクリア
      setAudioData("");
      setAudioInfo(null);
      setDescription("");
      setRecordingDate("");
      setTags([]);
      setLanguage("ja");
      setInitialPrompt("");
      
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
  const fetchJobDetails = async (jobId: string, fileHash: string) => {
    try {
      setErrorMessage("");

      const requestId = generateRequestId();
      // ハッシュ値をパラメータとして使用してFirestoreからジョブ詳細を取得
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${fileHash}`, {
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

      const firestoreData = await response.json();
      
      // ジョブが完了状態の場合のみ、GCSから文字起こし結果を取得
      let segments: any[] = [];
      if (firestoreData.status === "completed") {
        try {
          // まず編集済みファイル（edited_transcript.json）があるかチェック
          const editedTranscriptUrl = `${API_BASE_URL}/backend/whisper/transcript/${fileHash}/edited`;
          const editedResponse = await fetch(editedTranscriptUrl, {
            method: "GET",
            headers: {
              "Authorization": `Bearer ${token}`,
              "X-Request-Id": generateRequestId()
            }
          });

          if (editedResponse.ok) {
            // 編集済みファイルが存在する場合
            segments = await editedResponse.json();
            console.log("編集済み文字起こし結果を読み込みました");
          } else {
            // 編集済みファイルがない場合は、元のcombine.jsonを取得
            const originalTranscriptUrl = `${API_BASE_URL}/backend/whisper/transcript/${fileHash}/original`;
            const originalResponse = await fetch(originalTranscriptUrl, {
              method: "GET",
              headers: {
                "Authorization": `Bearer ${token}`,
                "X-Request-Id": generateRequestId()
              }
            });

            if (originalResponse.ok) {
              segments = await originalResponse.json();
              console.log("元の文字起こし結果を読み込みました");
            } else {
              console.warn("文字起こし結果の取得に失敗しました");
            }
          }
        } catch (segmentError) {
          console.error("文字起こし結果の取得中にエラー:", segmentError);
          // segmentsは空配列のまま
        }
      }

      // FirestoreデータとGCSのsegmentsデータを結合
      const combinedJobData = {
        ...firestoreData,
        segments: segments,
        fileHash: fileHash // fileHashを明示的に追加
      };

      setJobData(combinedJobData);
      setSelectedJob(jobId);
      setSelectedHash(fileHash);
    } catch (error) {
      console.error("ジョブ詳細取得エラー:", error);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  // 編集内容を保存
  const saveEditedTranscript = async (editedSegments: WhisperSegment[]) => {
    if (!selectedJob || !selectedHash) return;
    
    try {
      setErrorMessage("");
      const requestId = generateRequestId();
      
      // ハッシュ値ベースのエンドポイントに変更
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${selectedHash}/edit`, {
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
  const cancelJob = async (jobId: string, fileHash: string) => {
    if (!confirm("このジョブをキャンセルしますか？")) {
      return;
    }
    
    try {
      setErrorMessage("");
      const requestId = generateRequestId();
      
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${fileHash}/cancel`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const errorDetail = errorData?.detail || `ジョブのキャンセルに失敗しました (${response.status})`;
        throw new Error(errorDetail);
      }

      alert("ジョブがキャンセルされました");
      fetchJobs();
      
    } catch (error) {
      console.error("キャンセルエラー:", error);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };
  
  // ジョブの再キュー
  const retryJob = async (jobId: string, fileHash: string) => {
    if (!confirm("このジョブを再度キューに入れますか？")) {
      return;
    }
    
    try {
      setErrorMessage("");
      const requestId = generateRequestId();
      
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${fileHash}/retry`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const errorDetail = errorData?.detail || `ジョブの再キューに失敗しました (${response.status})`;
        throw new Error(errorDetail);
      }

      alert("ジョブが再度キューに入れられました");
      fetchJobs();
      
    } catch (error) {
      console.error("再キューエラー:", error);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  // 認証状態チェック - ローディング中や未認証時の表示
  if (loading) {
    return (
      <div className="p-4 overflow-y-auto bg-dark-primary text-white min-h-screen">
        <h1 className="text-3xl font-bold mb-4">Whisper 音声文字起こし（バッチ処理）</h1>
        <div className="flex items-center justify-center py-8">
          <div className="text-gray-400">認証状態を確認中...</div>
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className="p-4 overflow-y-auto bg-dark-primary text-white min-h-screen">
        <h1 className="text-3xl font-bold mb-4">Whisper 音声文字起こし（バッチ処理）</h1>
        <div className="flex items-center justify-center py-8">
          <div className="text-red-400">この機能を使用するにはログインが必要です。</div>
        </div>
      </div>
    );
  }

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
            onLanguageChange={setLanguage}
            onInitialPromptChange={setInitialPrompt}
          />

          <WhisperMetadataEditor
            description={description}
            recordingDate={recordingDate}
            language={language}
            initialPrompt={initialPrompt}
            isSending={isUploading}
            onDescriptionChange={setDescription}
            onRecordingDateChange={setRecordingDate}
            onLanguageChange={setLanguage}
            onInitialPromptChange={setInitialPrompt}
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
                onClick={() => {
                  setSelectedJob(null);
                  setSelectedHash(null);
                }}
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
            <>
              {/* 追加フィルター UI */}
              <div className="mb-4 bg-gray-800 p-4 rounded">
                <h2 className="text-xl mb-2">詳細フィルター</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* キーワード検索 */}
                  <div>
                    <label className="block text-sm font-medium mb-1">キーワード検索</label>
                    <input
                      type="text"
                      value={searchKeyword}
                      onChange={(e) => setSearchKeyword(e.target.value)}
                      placeholder="ファイル名で検索..."
                      className="w-full bg-gray-700 rounded px-3 py-2 text-white"
                    />
                  </div>
                  
                  {/* 日付範囲フィルター */}
                  <div>
                    <label className="block text-sm font-medium mb-1">開始日</label>
                    <input
                      type="date"
                      value={dateFrom}
                      onChange={(e) => setDateFrom(e.target.value)}
                      className="w-full bg-gray-700 rounded px-3 py-2 text-white"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium mb-1">終了日</label>
                    <input
                      type="date"
                      value={dateTo}
                      onChange={(e) => setDateTo(e.target.value)}
                      className="w-full bg-gray-700 rounded px-3 py-2 text-white"
                    />
                  </div>
                  
                  {/* タグフィルター */}
                  <div>
                    <label className="block text-sm font-medium mb-1">タグ</label>
                    {availableTags.length > 0 ? (
                      <select
                        multiple
                        value={selectedTags}
                        onChange={(e) => {
                          const options = Array.from(e.target.selectedOptions, option => option.value);
                          setSelectedTags(options);
                        }}
                        className="w-full bg-gray-700 rounded px-3 py-2 text-white h-24"
                      >
                        {availableTags.map(tag => (
                          <option key={tag} value={tag}>{tag}</option>
                        ))}
                      </select>
                    ) : (
                      <p className="text-gray-500 text-sm">利用可能なタグがありません</p>
                    )}
                  </div>
                  
                  {/* リセットボタン */}
                  <div className="flex items-end">
                    <button
                      onClick={() => {
                        setSearchKeyword("");
                        setSelectedTags([]);
                        setDateFrom("");
                        setDateTo("");
                      }}
                      className="bg-gray-600 hover:bg-gray-700 text-white px-3 py-2 rounded"
                    >
                      フィルターをリセット
                    </button>
                  </div>
                </div>
              </div>
              
              {/* ジョブ一覧 */}
              <WhisperJobList
                jobs={filterJobs(jobs)}
                onJobSelect={(jobId, fileHash) => fetchJobDetails(jobId, fileHash)}
                onRefresh={fetchJobs}
                onCancel={(jobId, fileHash) => cancelJob(jobId, fileHash)}
                onRetry={(jobId, fileHash) => retryJob(jobId, fileHash)}
                filterStatus={filterStatus}
                onFilterChange={setFilterStatus}
                sortOrder={sortOrder}
                onSortChange={setSortOrder}
              />
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default WhisperPage;