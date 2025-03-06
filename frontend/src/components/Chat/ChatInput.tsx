// frontend/src/components/Chat/ChatInput.tsx
import React, { ChangeEvent } from "react";
import { FileData, processFile } from "../../utils/fileUtils";

interface ChatInputProps {
  input: string;
  setInput: (input: string) => void;
  isProcessing: boolean;
  selectedFiles: FileData[];
  setSelectedFiles: (files: FileData[]) => void;
  addFiles: (files: FileData[]) => void;
  sendMessage: () => void;
  stopGeneration: () => void;
  setErrorMessage: (message: string) => void;
  maxLimits: {
    MAX_IMAGES: number;
    MAX_AUDIO_FILES: number;
    MAX_TEXT_FILES: number;
    MAX_IMAGE_SIZE: number;
    MAX_LONG_EDGE: number;
  };
}

const ChatInput: React.FC<ChatInputProps> = ({
  input,
  setInput,
  isProcessing,
  selectedFiles,
  setSelectedFiles,
  addFiles,
  sendMessage,
  stopGeneration,
  setErrorMessage,
  maxLimits
}) => {
  const { MAX_IMAGES, MAX_AUDIO_FILES, MAX_TEXT_FILES, MAX_IMAGE_SIZE, MAX_LONG_EDGE } = maxLimits;

  // ファイルタイプ別の数をカウント
  const countFilesByType = (files: FileData[]) => {
    const counts = {
      image: 0,
      audio: 0,
      text: 0
    };
    
    files.forEach(file => {
      if (file.mimeType.startsWith('image/')) {
        counts.image++;
      } else if (file.mimeType.startsWith('audio/')) {
        counts.audio++;
      } else {
        counts.text++;
      }
    });
    
    return counts;
  };

  // ドラッグアンドドロップ処理
  const handleDragOver = (e: React.DragEvent<HTMLTextAreaElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = async (e: React.DragEvent<HTMLTextAreaElement>) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!e.dataTransfer.files || e.dataTransfer.files.length === 0 || isProcessing) {
      return;
    }
    
    const files = Array.from(e.dataTransfer.files);
    
    // 現在のファイル数をカウント
    const currentCounts = countFilesByType(selectedFiles);
    
    // ドロップされたファイルの種類と数を確認
    const audioFiles = files.filter(file => file.type.startsWith('audio/'));
    
    // 音声ファイルの上限チェック
    if (audioFiles.length + currentCounts.audio > MAX_AUDIO_FILES) {
      setErrorMessage(`音声ファイルは1メッセージにつき最大${MAX_AUDIO_FILES}件まで添付できます`);
      return;
    }
    
    try {
      // ファイル処理
      const filePromises = files.map(file => {
        const fileExtension = file.name.split('.').pop()?.toLowerCase() || '';
        
        // PDFファイルはドラッグ&ドロップの場合は常にテキストとして処理
        if (fileExtension === 'pdf' || file.type === 'application/pdf') {
          return processFile(file, MAX_IMAGE_SIZE, MAX_LONG_EDGE, ['.txt', '.pdf']);
        }
        
        // その他のファイルは拡張子に基づいて処理
        if (file.type.startsWith('image/')) {
          return processFile(file, MAX_IMAGE_SIZE, MAX_LONG_EDGE, ['image/*']);
        } else if (file.type.startsWith('audio/')) {
          return processFile(file, MAX_IMAGE_SIZE, MAX_LONG_EDGE, ['audio/*']);
        } else {
          return processFile(file, MAX_IMAGE_SIZE, MAX_LONG_EDGE, ['.txt', '.docx', '.csv']);
        }
      });
      
      const processedResults = await Promise.all(filePromises);
      
      // 結果を1次元配列に平坦化
      let newFiles: FileData[] = [];
      processedResults.forEach(result => {
        if (Array.isArray(result)) {
          newFiles.push(...result);
        } else {
          newFiles.push(result);
        }
      });
      
      // 処理されたファイルのカウント
      const newCounts = countFilesByType(newFiles);
      
      // 各ファイルタイプごとに上限チェック
      const totalImageCount = currentCounts.image + newCounts.image;
      const totalAudioCount = currentCounts.audio + newCounts.audio;
      const totalTextCount = currentCounts.text + newCounts.text;
      
      let filteredFiles: FileData[] = [];
      let errorMessages: string[] = [];
      
      // 画像ファイルの上限チェック
      if (totalImageCount > MAX_IMAGES) {
        const remainingImageSlots = Math.max(0, MAX_IMAGES - currentCounts.image);
        const imageFiles = newFiles.filter(file => file.mimeType.startsWith('image/'));
        filteredFiles = [...filteredFiles, ...imageFiles.slice(0, remainingImageSlots)];
        errorMessages.push(`画像ファイルは最大${MAX_IMAGES}件まで（${remainingImageSlots}件追加可能）`);
      } else {
        filteredFiles = [...filteredFiles, ...newFiles.filter(file => file.mimeType.startsWith('image/'))];
      }
      
      // 音声ファイルの上限チェック
      if (totalAudioCount > MAX_AUDIO_FILES) {
        const remainingAudioSlots = Math.max(0, MAX_AUDIO_FILES - currentCounts.audio);
        const audioFiles = newFiles.filter(file => file.mimeType.startsWith('audio/'));
        filteredFiles = [...filteredFiles, ...audioFiles.slice(0, remainingAudioSlots)];
        errorMessages.push(`音声ファイルは最大${MAX_AUDIO_FILES}件まで（${remainingAudioSlots}件追加可能）`);
      } else {
        filteredFiles = [...filteredFiles, ...newFiles.filter(file => file.mimeType.startsWith('audio/'))];
      }
      
      // テキストファイルの上限チェック
      if (totalTextCount > MAX_TEXT_FILES) {
        const remainingTextSlots = Math.max(0, MAX_TEXT_FILES - currentCounts.text);
        const textFiles = newFiles.filter(file => !file.mimeType.startsWith('image/') && !file.mimeType.startsWith('audio/'));
        filteredFiles = [...filteredFiles, ...textFiles.slice(0, remainingTextSlots)];
        errorMessages.push(`テキストファイルは最大${MAX_TEXT_FILES}件まで（${remainingTextSlots}件追加可能）`);
      } else {
        filteredFiles = [...filteredFiles, ...newFiles.filter(file => !file.mimeType.startsWith('image/') && !file.mimeType.startsWith('audio/'))];
      }
      
      // エラーメッセージがあれば表示
      if (errorMessages.length > 0) {
        setErrorMessage(errorMessages.join('\n'));
      }
      
      addFiles(filteredFiles);
    } catch (error) {
      console.error('ファイルのドロップ処理エラー:', error);
      setErrorMessage('ファイルの処理中にエラーが発生しました');
    }
  };

  // ファイルアップロードハンドラー
  const handleFileUpload = async (
    e: ChangeEvent<HTMLInputElement>,
    fileTypes: string[]
  ) => {
    console.log(
      `[handleFileUpload] ${fileTypes.join("/")} ファイル選択イベント発生`
    );
    if (!e.target.files) return;

    const files = Array.from(e.target.files);
    
    // 現在のファイル数をカウント
    const currentCounts = countFilesByType(selectedFiles);
    
    // ファイルタイプの判定
    const isImageUpload = fileTypes.includes("image/*");
    const isAudioUpload = fileTypes.includes("audio/*");
    const isTextUpload = fileTypes.some(type => ['.txt', '.docx', '.csv', '.pdf'].includes(type));
    
    // 上限チェック
    if (isAudioUpload) {
      // 音声ファイルの上限チェック
      const audioFiles = files.filter(file => file.type.startsWith('audio/'));
      
      if (audioFiles.length + currentCounts.audio > MAX_AUDIO_FILES) {
        setErrorMessage(`音声ファイルは1メッセージにつき最大${MAX_AUDIO_FILES}件まで添付できます`);
        e.target.value = ''; // 選択をリセット
        return;
      }
      
      // 複数の音声ファイルが選択されていた場合
      if (audioFiles.length > MAX_AUDIO_FILES) {
        setErrorMessage(`音声ファイルは1メッセージにつき最大${MAX_AUDIO_FILES}件まで添付できます`);
        e.target.value = ''; // 選択をリセット
        return;
      }
    }
    
    if (isImageUpload && currentCounts.image >= MAX_IMAGES) {
      setErrorMessage(`画像ファイルは最大${MAX_IMAGES}件まで添付できます`);
      e.target.value = ''; // 選択をリセット
      return;
    }
    
    if (isTextUpload && currentCounts.text >= MAX_TEXT_FILES) {
      setErrorMessage(`テキストファイルは最大${MAX_TEXT_FILES}件まで添付できます`);
      e.target.value = ''; // 選択をリセット
      return;
    }

    try {
      // PDFを画像として処理するかどうか判断
      const isPdfAsImage =
        fileTypes.includes("image/*") && fileTypes.includes("application/pdf");
      const hasPdf = files.some((file) => file.type === "application/pdf");

      // ファイル処理
      const fileDataPromises = files.map((file) =>
        processFile(file, MAX_IMAGE_SIZE, MAX_LONG_EDGE, fileTypes)
      );

      const processedResults = await Promise.all(fileDataPromises);

      // 結果を1次元配列に平坦化
      let newFiles: FileData[] = [];
      processedResults.forEach((result) => {
        if (Array.isArray(result)) {
          newFiles.push(...result);
        } else {
          newFiles.push(result);
        }
      });

      // 処理されたファイルのカウント
      const newCounts = countFilesByType(newFiles);
      
      // 各ファイルタイプごとに上限チェック
      const totalImageCount = currentCounts.image + newCounts.image;
      const totalAudioCount = currentCounts.audio + newCounts.audio;
      const totalTextCount = currentCounts.text + newCounts.text;
      
      let filteredFiles: FileData[] = [];
      let errorMessages: string[] = [];
      
      // 画像ファイルの上限チェック（画像アップロードの場合）
      if (isImageUpload) {
        if (totalImageCount > MAX_IMAGES) {
          const remainingImageSlots = Math.max(0, MAX_IMAGES - currentCounts.image);
          
          // PDFファイルからのアップロードで画像として処理する場合
          if (hasPdf && isPdfAsImage) {
            const pdfImageFiles = newFiles.filter(file => file.mimeType.startsWith('image/'));
            const pdfPageCount = pdfImageFiles.length;
            filteredFiles = [...filteredFiles, ...pdfImageFiles.slice(0, remainingImageSlots)];
            
            errorMessages.push(
              `PDFの合計ページ数(${pdfPageCount}ページ)が追加可能な上限(${remainingImageSlots}ページ)を超えています。最初の${remainingImageSlots}ページのみが追加されました。`
            );
          } else {
            const imageFiles = newFiles.filter(file => file.mimeType.startsWith('image/'));
            filteredFiles = [...filteredFiles, ...imageFiles.slice(0, remainingImageSlots)];
            errorMessages.push(`画像ファイルは最大${MAX_IMAGES}件まで（あと${remainingImageSlots}件追加可能）`);
          }
        } else {
          filteredFiles = [...filteredFiles, ...newFiles.filter(file => file.mimeType.startsWith('image/'))];
        }
      }
      
      // 音声ファイルの上限チェック（音声アップロードの場合）
      if (isAudioUpload) {
        if (totalAudioCount > MAX_AUDIO_FILES) {
          const remainingAudioSlots = Math.max(0, MAX_AUDIO_FILES - currentCounts.audio);
          const audioFiles = newFiles.filter(file => file.mimeType.startsWith('audio/'));
          filteredFiles = [...filteredFiles, ...audioFiles.slice(0, remainingAudioSlots)];
          errorMessages.push(`音声ファイルは最大${MAX_AUDIO_FILES}件まで（あと${remainingAudioSlots}件追加可能）`);
        } else {
          filteredFiles = [...filteredFiles, ...newFiles.filter(file => file.mimeType.startsWith('audio/'))];
        }
      }
      
      // テキストファイルの上限チェック（テキストアップロードの場合）
      if (isTextUpload) {
        if (totalTextCount > MAX_TEXT_FILES) {
          const remainingTextSlots = Math.max(0, MAX_TEXT_FILES - currentCounts.text);
          const textFiles = newFiles.filter(file => !file.mimeType.startsWith('image/') && !file.mimeType.startsWith('audio/'));
          filteredFiles = [...filteredFiles, ...textFiles.slice(0, remainingTextSlots)];
          errorMessages.push(`テキストファイルは最大${MAX_TEXT_FILES}件まで（あと${remainingTextSlots}件追加可能）`);
        } else {
          filteredFiles = [...filteredFiles, ...newFiles.filter(file => !file.mimeType.startsWith('image/') && !file.mimeType.startsWith('audio/'))];
        }
      }
      
      // エラーメッセージがあれば表示
      if (errorMessages.length > 0) {
        setErrorMessage(errorMessages.join('\n'));
      }

      console.log(`[handleFileUpload] ファイル処理完了:`, filteredFiles);

      addFiles(filteredFiles);
    } catch (error) {
      console.error(`[handleFileUpload] ファイルアップロードエラー:`, error);
      setErrorMessage("ファイルの処理中にエラーが発生しました");
    }

    // ファイル選択をリセット（同じファイルを連続で選択できるように）
    e.target.value = "";
  };

  // キー押下による送信
  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex space-x-2">
      {/* テキスト入力エリア */}
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyPress={handleKeyPress}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className="flex-1 p-2 bg-gray-900 border border-gray-700 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-100"
        placeholder="メッセージを入力..."
        rows={4}
        disabled={isProcessing}
      />
      
      {/* ファイルアップロードボタンと送信ボタンを縦に並べる */}
      <div className="flex flex-col space-y-2 w-16">
        {/* 画像ボタン */}
        <label className="flex items-center justify-center px-2 py-2 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded-lg cursor-pointer">
          <span>🖼️</span>
          <input
            type="file"
            accept="image/*,.pdf"
            multiple
            className="hidden"
            onChange={(e) => handleFileUpload(e, ["image/*", "application/pdf"])}
            disabled={isProcessing}
          />
        </label>

        {/* 音声ボタン */}
        <label className="flex items-center justify-center px-2 py-2 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded-lg cursor-pointer">
          <span>🔊</span>
          <input
            type="file"
            accept="audio/*"
            multiple
            className="hidden"
            onChange={(e) => handleFileUpload(e, ["audio/*"])}
            disabled={isProcessing}
          />
        </label>

        {/* テキストボタン */}
        <label className="flex items-center justify-center px-2 py-2 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded-lg cursor-pointer">
          <span>📄</span>
          <input
            type="file"
            accept=".txt,.docx,.csv,.pdf"
            multiple
            className="hidden"
            onChange={(e) => handleFileUpload(e, [".txt", ".docx", ".csv", ".pdf"])}
            disabled={isProcessing}
          />
        </label>

        {/* 送信ボタン */}
        <button
          onClick={isProcessing ? stopGeneration : sendMessage}
          className={`px-2 py-2 rounded-lg ${
            isProcessing
              ? "bg-red-900 hover:bg-red-800"
              : "bg-blue-900 hover:bg-blue-800"
          } text-gray-100 transition-colors`}
        >
          {isProcessing ? "停止" : "送信"}
        </button>
      </div>
    </div>
  );
};

export default ChatInput;