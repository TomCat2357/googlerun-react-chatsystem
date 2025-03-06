// frontend/src/components/Chat/FilePreview.tsx
import React from "react";
import { FileData } from "../../utils/fileUtils";

interface FilePreviewProps {
  files: FileData[];
  onRemoveFile: (fileId: string) => void;
  onViewFile: (content: string, mimeType: string) => void;
}

const FilePreview: React.FC<FilePreviewProps> = ({
  files,
  onRemoveFile,
  onViewFile
}) => {
  // ファイルタイプに応じたアイコン表示
  const getFileIcon = (mimeType: string) => {
    if (mimeType.startsWith('image/')) return "🖼️";
    if (mimeType.startsWith('audio/')) return "🔊";
    if (mimeType === 'text/csv') return "📊";
    if (mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') return "📝";
    if (mimeType === 'application/pdf') return "📄";
    return "📎";
  };

  return (
    <div className="flex flex-wrap mb-4 gap-2">
      {files.map((file) => (
        <div key={file.id} className="relative inline-block">
          {file.mimeType.startsWith('image/') ? (
            <img
              src={file.content}
              alt={file.name}
              className="w-16 h-16 object-cover rounded border cursor-pointer"
              onClick={() => file.content && onViewFile(file.content, file.mimeType)}
            />
          ) : (
            <div
              className="w-16 h-16 bg-gray-700 flex flex-col items-center justify-center rounded border cursor-pointer"
              onClick={() => file.content && onViewFile(file.content, file.mimeType)}
            >
              <div>{getFileIcon(file.mimeType)}</div>
              <div className="text-xs truncate w-full text-center px-1">
                {file.name.length > 8
                  ? file.name.substring(0, 8) + "..."
                  : file.name}
              </div>
            </div>
          )}
          <button
            className="absolute top-0 right-0 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center"
            onClick={() => onRemoveFile(file.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
};

export default FilePreview;