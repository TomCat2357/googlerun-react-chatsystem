// frontend/src/components/Chat/FileViewerModal.tsx
import React from "react";

interface FileViewerModalProps {
  content: string;
  mimeType: string;
  onClose: () => void;
}

const FileViewerModal: React.FC<FileViewerModalProps> = ({
  content,
  mimeType,
  onClose
}) => {
  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-75 z-50"
      onClick={onClose}
    >
      <div className="relative max-w-4xl max-h-[90vh] overflow-auto bg-gray-800 rounded-lg p-4">
        <button
          className="absolute top-2 right-2 text-white text-2xl font-bold"
          onClick={onClose}
        >
          ×
        </button>

        {mimeType.startsWith('image/') ? (
          <img
            src={content}
            alt="Enlarged content"
            className="max-h-[80vh]"
            onClick={(e) => e.stopPropagation()}
          />
        ) : mimeType.startsWith('audio/') ? (
          <audio
            src={content}
            controls
            autoPlay
            className="w-full"
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <div
            className="bg-white text-black p-4 rounded max-h-[80vh] overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <pre className="whitespace-pre-wrap">
              {content}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};

export default FileViewerModal;