import { useState, useCallback, useRef } from 'react';
import { useErrorHandler } from './useErrorHandler';
import { FileData } from '../types/apiTypes';

export interface FileUploadOptions {
  allowedTypes?: string[];
  maxFiles?: number;
  maxSize?: number;
  maxImageSize?: number;
  maxLongEdge?: number;
  extractMetadata?: boolean;
  enableDragDrop?: boolean;
}

export interface FileUploadState {
  files: FileData[];
  isUploading: boolean;
  progress: number;
}

export interface AudioMetadata {
  duration: number;
  fileName: string;
  fileSize: number;
  mimeType: string;
}

/**
 * 統一されたファイルアップロードフック
 * ドラッグ&ドロップ、バリデーション、メタデータ抽出を含む
 */
export const useFileUpload = (options: FileUploadOptions = {}) => {
  const {
    allowedTypes = ['*/*'],
    maxFiles = 10,
    maxSize = 50 * 1024 * 1024, // 50MB
    maxImageSize = 20 * 1024 * 1024, // 20MB
    maxLongEdge = 3008,
    extractMetadata = false,
    enableDragDrop = true,
  } = options;

  const [files, setFiles] = useState<FileData[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragActive, setDragActive] = useState(false);

  const { handleError, clearError } = useErrorHandler();
  const fileInputRef = useRef<HTMLInputElement>(null);

  /**
   * ファイルタイプの検証
   */
  const validateFileType = useCallback((file: File): boolean => {
    if (allowedTypes.includes('*/*')) return true;
    
    return allowedTypes.some(type => {
      if (type.endsWith('/*')) {
        const category = type.replace('/*', '');
        return file.type.startsWith(category + '/');
      }
      if (type.startsWith('.')) {
        return file.name.toLowerCase().endsWith(type.toLowerCase());
      }
      return file.type === type;
    });
  }, [allowedTypes]);

  /**
   * ファイルサイズの検証
   */
  const validateFileSize = useCallback((file: File): boolean => {
    const limit = file.type.startsWith('image/') ? maxImageSize : maxSize;
    return file.size <= limit;
  }, [maxSize, maxImageSize]);

  /**
   * 音声メタデータの抽出
   */
  const extractAudioMetadata = useCallback(async (file: File): Promise<AudioMetadata> => {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const audio = new Audio();
      audio.src = url;

      audio.onloadedmetadata = () => {
        const metadata: AudioMetadata = {
          duration: audio.duration,
          fileName: file.name,
          fileSize: file.size,
          mimeType: file.type,
        };
        URL.revokeObjectURL(url);
        resolve(metadata);
      };

      audio.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error('無効な音声データです'));
      };
    });
  }, []);

  /**
   * 画像のリサイズ処理
   */
  const resizeImage = useCallback(async (
    file: File,
    maxSize: number,
    maxLongEdge: number
  ): Promise<string> => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');

      img.onload = () => {
        const { width, height } = img;
        const aspectRatio = width / height;
        
        let newWidth = width;
        let newHeight = height;

        // 長辺がmaxLongEdgeを超える場合は縮小
        if (Math.max(width, height) > maxLongEdge) {
          if (width > height) {
            newWidth = maxLongEdge;
            newHeight = maxLongEdge / aspectRatio;
          } else {
            newHeight = maxLongEdge;
            newWidth = maxLongEdge * aspectRatio;
          }
        }

        canvas.width = newWidth;
        canvas.height = newHeight;

        if (ctx) {
          ctx.drawImage(img, 0, 0, newWidth, newHeight);
          
          // 品質調整してサイズ制限内に収める
          let quality = 0.9;
          let result = canvas.toDataURL('image/jpeg', quality);
          
          while (result.length > maxSize * 4/3 && quality > 0.1) {
            quality -= 0.1;
            result = canvas.toDataURL('image/jpeg', quality);
          }
          
          resolve(result);
        } else {
          reject(new Error('Canvas context の取得に失敗しました'));
        }
      };

      img.onerror = () => reject(new Error('画像の読み込みに失敗しました'));
      img.src = URL.createObjectURL(file);
    });
  }, []);

  /**
   * ファイルをBase64に変換
   */
  const fileToBase64 = useCallback(async (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target?.result) {
          resolve(event.target.result as string);
        } else {
          reject(new Error('ファイル読み込みエラー'));
        }
      };
      reader.onerror = () => reject(new Error('ファイル読み込みエラー'));
      reader.readAsDataURL(file);
    });
  }, []);

  /**
   * 単一ファイルの処理
   */
  const processFile = useCallback(async (file: File): Promise<FileData> => {
    // バリデーション
    if (!validateFileType(file)) {
      throw new Error(`許可されていないファイルタイプです: ${file.type}`);
    }

    if (!validateFileSize(file)) {
      const limit = file.type.startsWith('image/') ? maxImageSize : maxSize;
      throw new Error(`ファイルサイズが上限（${Math.round(limit / 1024 / 1024)}MB）を超えています`);
    }

    let data: string;
    let metadata: any = {};

    // ファイルタイプに応じた処理
    if (file.type.startsWith('image/')) {
      data = await resizeImage(file, maxImageSize, maxLongEdge);
    } else {
      data = await fileToBase64(file);
    }

    // メタデータ抽出
    if (extractMetadata && file.type.startsWith('audio/')) {
      metadata = await extractAudioMetadata(file);
    }

    return {
      id: `file_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
      name: file.name,
      content: data,
      size: file.size,
      mimeType: file.type,
      preview: file.name,
    };
  }, [validateFileType, validateFileSize, resizeImage, fileToBase64, extractAudioMetadata, extractMetadata, maxImageSize, maxLongEdge]);

  /**
   * 複数ファイルの処理
   */
  const processFiles = useCallback(async (fileList: FileList | File[]): Promise<FileData[]> => {
    const filesArray = Array.from(fileList);
    
    if (files.length + filesArray.length > maxFiles) {
      throw new Error(`ファイル数が上限（${maxFiles}件）を超えています`);
    }

    setIsUploading(true);
    setProgress(0);
    clearError();

    try {
      const results: FileData[] = [];
      
      for (let i = 0; i < filesArray.length; i++) {
        const processedFile = await processFile(filesArray[i]);
        results.push(processedFile);
        setProgress(((i + 1) / filesArray.length) * 100);
      }

      return results;
    } finally {
      setIsUploading(false);
      setProgress(0);
    }
  }, [files.length, maxFiles, processFile, clearError]);

  /**
   * ファイル選択ハンドラー
   */
  const handleFileSelect = useCallback(async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    if (!event.target.files || event.target.files.length === 0) return;

    try {
      const newFiles = await processFiles(event.target.files);
      setFiles(prev => [...prev, ...newFiles]);
    } catch (error) {
      handleError(error, 'ファイル選択');
    }

    // 入力値をリセット（同じファイルを再選択できるようにする）
    event.target.value = '';
  }, [processFiles, handleError]);

  /**
   * ドラッグ&ドロップハンドラー
   */
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (enableDragDrop) {
      setDragActive(true);
    }
  }, [enableDragDrop]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (enableDragDrop) {
      setDragActive(false);
    }
  }, [enableDragDrop]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!enableDragDrop) return;
    
    setDragActive(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    if (droppedFiles.length === 0) return;

    try {
      const newFiles = await processFiles(droppedFiles);
      setFiles(prev => [...prev, ...newFiles]);
    } catch (error) {
      handleError(error, 'ドラッグ&ドロップ');
    }
  }, [enableDragDrop, processFiles, handleError]);

  /**
   * ファイル削除
   */
  const removeFile = useCallback((index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  }, []);

  /**
   * 全ファイルクリア
   */
  const clearFiles = useCallback(() => {
    setFiles([]);
    clearError();
  }, [clearError]);

  /**
   * ファイル選択ダイアログを開く
   */
  const openFileDialog = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  return {
    // State
    files,
    isUploading,
    progress,
    dragActive,

    // Actions
    handleFileSelect,
    removeFile,
    clearFiles,
    openFileDialog,

    // Drag & Drop
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,

    // Utils
    processFiles,
    validateFileType,
    validateFileSize,

    // Refs
    fileInputRef,
  };
};