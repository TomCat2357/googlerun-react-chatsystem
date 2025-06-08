import React, { useMemo } from "react";

interface Job {
  id: string;
  filename: string;
  created_at: string;
  updated_at?: string;
  status: "queued" | "launched" | "processing" | "completed" | "failed" | "error" | "canceled"; // statusの型定義更新
  progress?: number;
  error_message?: string;
  tags?: string[];
  file_hash: string; // ファイルハッシュを追加
}

interface WhisperJobListProps {
  jobs: Job[];
  onJobSelect: (jobId: string, fileHash: string) => void; 
  onRefresh: () => void;
  onCancel?: (jobId: string, fileHash: string) => void; // キャンセル専用
  onRetry?: (jobId: string, fileHash: string) => void;  // 再キュー専用
  filterStatus: string;
  onFilterChange: (status: string) => void;
  sortOrder: string;
  onSortChange: (order: string) => void;
}

const WhisperJobList: React.FC<WhisperJobListProps> = ({
  jobs,
  onJobSelect,
  onRefresh,
  onCancel,
  onRetry,
  filterStatus,
  onFilterChange,
  sortOrder,
  onSortChange
}) => {
  // フィルタリングされたジョブリスト
  const filteredJobs = useMemo(() => {
    return jobs
      .filter(job => {
        if (filterStatus === "all") return true;
        return job.status === filterStatus;
      })
      .sort((a, b) => {
        // ソートロジック
        if (sortOrder === "date-desc") 
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        if (sortOrder === "date-asc") 
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
        if (sortOrder === "status") {
          // ステータス順（処理中→起動済み→待機中→完了→失敗）
          const statusOrder = {
            "processing": 0,
            "launched": 1, // launched を processing と同じ優先度に
            "queued": 2,
            "completed": 3,
            "failed": 4,
            "error": 5,
            "canceled": 6
          };
          return statusOrder[a.status] - statusOrder[b.status];
        }
        return 0;
      });
  }, [jobs, filterStatus, sortOrder]);

  return (
    <div>
      {/* フィルターとソートコントロール */}
      <div className="flex justify-between items-center mb-4">
        <div className="flex space-x-2">
          <select 
            value={filterStatus} 
            onChange={(e) => onFilterChange(e.target.value)}
            className="bg-gray-700 text-white rounded px-2 py-1"
          >
            <option value="all">すべて</option>
            <option value="queued">待機中</option>
            <option value="launched">起動済</option>
            <option value="processing">処理中</option>
            <option value="completed">完了</option>
            <option value="failed">失敗</option>
            <option value="canceled">キャンセル</option>
          </select>
          
          <select 
            value={sortOrder} 
            onChange={(e) => onSortChange(e.target.value)}
            className="bg-gray-700 text-white rounded px-2 py-1"
          >
            <option value="date-desc">新しい順</option>
            <option value="date-asc">古い順</option>
            <option value="status">状態順</option>
          </select>
        </div>
        
        <button
          onClick={onRefresh}
          className="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded"
        >
          更新
        </button>
      </div>

      {/* ジョブ一覧テーブル */}
      {filteredJobs.length === 0 ? (
        <p className="text-gray-400">該当するジョブがありません</p>
      ) : (
        <div className="bg-gray-800 rounded overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr className="bg-gray-700">
                <th className="px-4 py-2 text-left">ファイル名</th>
                <th className="px-4 py-2 text-left">作成日時</th>
                <th className="px-4 py-2 text-left">ステータス</th>
                <th className="px-4 py-2 text-left">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredJobs.map((job) => (
                <tr key={job.id} className="border-t border-gray-700">
                  <td className="px-4 py-2">
                    {job.filename}
                    {job.tags && job.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {job.tags.map(tag => (
                          <span key={tag} className="bg-blue-900 text-xs px-1 rounded">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="text-xs text-gray-400 mt-1">
                      Hash: {job.file_hash ? job.file_hash.substring(0, 8) + '...' : 'N/A'}
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    {new Date(job.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2">
                    {job.status === "queued" && (
                      <span className="text-blue-400 flex items-center">
                        <span className="mr-2">⏳</span> 待機中
                      </span>
                    )}
                    {job.status === "launched" && (
                      <span className="text-cyan-400 flex items-center">
                        <span className="animate-pulse mr-2">🚀</span> 起動済
                      </span>
                    )}
                    {job.status === "processing" && (
                      <div>
                        <span className="text-yellow-400 flex items-center">
                          <span className="animate-pulse mr-2">🔄</span> 処理中
                        </span>
                        {job.progress !== undefined && job.progress > 0 && (
                          <div className="w-full bg-gray-700 rounded-full h-2 mt-1">
                            <div 
                              className="bg-yellow-400 h-2 rounded-full" 
                              style={{ width: `${job.progress}%` }}
                            ></div>
                          </div>
                        )}
                      </div>
                    )}
                    {job.status === "completed" && (
                      <span className="text-green-400 flex items-center">
                        <span className="mr-2">✅</span> 完了
                      </span>
                    )}
                    {job.status === "canceled" && (
                      <span className="text-gray-400 flex items-center">
                        <span className="mr-2">🚫</span> キャンセル
                      </span>
                    )}
                    {(job.status === "failed" || job.status === "error") && (
                      <span className="text-red-400 flex items-center" title={job.error_message}>
                        <span className="mr-2">❌</span> {job.status === "failed" ? "失敗" : "エラー"}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 flex gap-2">
                    <button
                      onClick={() => onJobSelect(job.id, job.file_hash)}
                      className="px-3 py-1 rounded bg-blue-500 hover:bg-blue-600"
                    >
                      {job.status === "completed" ? "再生・編集" : "詳細"}
                    </button>
                    
                    {/* キュー待ちのジョブにはキャンセルボタンを表示 */}
                    {onCancel && job.status === "queued" && (
                      <button
                        onClick={() => onCancel(job.id, job.file_hash)}
                        className="px-3 py-1 rounded bg-red-600 hover:bg-red-700 text-white"
                      >
                        キャンセル
                      </button>
                    )}
                    
                    {/* 完了/失敗/キャンセル済みのジョブには再キューボタンを表示 */}
                    {onRetry && ["completed", "failed", "canceled"].includes(job.status) && (
                      <button
                        onClick={() => onRetry(job.id, job.file_hash)}
                        className="px-3 py-1 rounded bg-yellow-600 hover:bg-yellow-700 text-white"
                      >
                        再キュー
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default WhisperJobList;