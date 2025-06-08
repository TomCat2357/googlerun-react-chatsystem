// frontend/src/components/Chat/ErrorModal.tsx
import React from "react";

interface ErrorModalProps {
  message: string;
  onClose: () => void;
}

const ErrorModal: React.FC<ErrorModalProps> = ({ message, onClose }) => {
  // オーバーレイクリック時の処理
  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  // ESCキーでモーダルを閉じる
  React.useEffect(() => {
    const handleEscapeKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscapeKey);
    return () => {
      document.removeEventListener('keydown', handleEscapeKey);
    };
  }, [onClose]);

  // モーダル内のクリックイベントの伝播を停止
  const handleModalClick = (e: React.MouseEvent<HTMLDivElement>) => {
    e.stopPropagation();
  };

  return (
    <div 
      className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-10"
      onClick={handleOverlayClick}
    >
      <div 
        className="bg-white p-6 rounded shadow"
        onClick={handleModalClick}
      >
        <h2 className="text-xl font-semibold mb-4 text-black">エラー</h2>
        <p className="mb-4 text-black whitespace-pre-line">{message}</p>
        <button
          onClick={onClose}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          閉じる
        </button>
      </div>
    </div>
  );
};

export default ErrorModal;