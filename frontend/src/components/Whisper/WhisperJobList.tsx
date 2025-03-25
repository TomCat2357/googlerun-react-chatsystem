// frontend/src/component/Whisper/WhisperJobList.tsx
import React from "react";

interface Job {
  id: string;
  filename: string;
  created_at: string;
  status: "processing" | "completed" | "failed";
  error_message?: string;
}

interface WhisperJobListProps {
  jobs: Job[];
  onJobSelect: (jobId: string) => void;
  onRefresh: () => void;
}

const WhisperJobList: React.FC<WhisperJobListProps> = ({ jobs, onJobSelect, onRefresh }) => {
  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">処理ジョブ一覧</h2>
        <button
          onClick={onRefresh}
          className="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded"
        >
          更新
        </button>
      </div>

      {jobs.length === 0 ? (
        <p className="text-gray-400">ジョブがありません</p>
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
              {jobs.map((job) => (
                <tr key={job.id} className="border-t border-gray-700">
                  <td className="px-4 py-2">{job.filename}</td>
                  <td className="px-4 py-2">
                    {new Date(job.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2">
                    {job.status === "processing" && (
                      <span className="text-yellow-400 flex items-center">
                        <span className="animate-pulse mr-2">⟳</span> 処理中
                      </span>
                    )}
                    {job.status === "completed" && (
                      <span className="text-green-400">完了</span>
                    )}
                    {job.status === "failed" && (
                      <span className="text-red-400" title={job.error_message}>
                        失敗
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => onJobSelect(job.id)}
                      disabled={job.status === "processing"}
                      className={`px-3 py-1 rounded ${
                        job.status === "processing"
                          ? "bg-gray-500 cursor-not-allowed"
                          : "bg-blue-500 hover:bg-blue-600"
                      }`}
                    >
                      {job.status === "completed" ? "再生・編集" : "詳細"}
                    </button>
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