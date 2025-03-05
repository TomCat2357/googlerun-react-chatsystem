/**
 * fileUtils.ts
 * チャットアプリで使用するファイル処理ユーティリティ
 */

import * as XLSX from 'xlsx';
import mammoth from 'mammoth';
import * as pdfjsLib from 'pdfjs-dist';

// PDFJSの初期化
if (typeof window !== 'undefined' && pdfjsLib) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.js`;
}

// ファイル情報の型定義
export interface FileData {
  id: string;
  name: string;
  content: string; // base64 or text content
  preview?: string; // プレビュー表示用（テキストの場合は冒頭部分など）
  size: number; // 元のファイルサイズ（バイト）
  mimeType: string; // ファイルのMIMEタイプ
}

/**
 * ファイルをFileData形式に処理する
 */
export async function processFile(file: File, maxImageSize: number, maxLongEdge: number, acceptedTypes: string[]): Promise<FileData | FileData[]> {
  const fileExtension = file.name.split('.').pop()?.toLowerCase() || '';
  const fileId = `file_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

  // PDFの処理方法を選択
  if (file.type === 'application/pdf' || fileExtension === 'pdf') {
    // テキストボタンからのアップロード（.txtなどと一緒にPDFが指定されている場合）
    if (acceptedTypes.includes('.pdf') && (acceptedTypes.includes('.txt') || acceptedTypes.includes('.docx') || acceptedTypes.includes('.csv'))) {
      return await processPdfAsText(file, fileId);
    } else {
      // 画像ボタンからのアップロード
      return await processPdfAsImage(file, fileId, maxImageSize, maxLongEdge);
    }
  }

  // ファイルの処理
  if (file.type.startsWith('image/')) {
    return processImageFile(file, fileId, maxImageSize, maxLongEdge);
  } else if (file.type.startsWith('audio/')) {
    return processAudioFile(file, fileId);
  } else if (fileExtension === 'csv' || file.type === 'text/csv') {
    return await processCsvFile(file, fileId);
  } else if (fileExtension === 'docx' || file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
    return await processDocxFile(file, fileId);
  } else {
    return await processTextFile(file, fileId);
  }
}

/**
 * 画像ファイルの処理
 */
async function processImageFile(file: File, fileId: string, maxImageSize: number, maxLongEdge: number): Promise<FileData> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      if (event.target?.result) {
        const dataUrl = event.target.result as string;
        const image = new Image();

        image.onload = () => {
          let { naturalWidth: width, naturalHeight: height } = image;
          const longEdge = Math.max(width, height);
          let scale = 1;

          if (longEdge > maxLongEdge) {
            scale = maxLongEdge / longEdge;
            width = Math.floor(width * scale);
            height = Math.floor(height * scale);
          }

          const canvas = document.createElement('canvas');
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext('2d');

          if (!ctx) {
            reject(new Error('キャンバスの取得に失敗しました'));
            return;
          }

          ctx.drawImage(image, 0, 0, width, height);

          let quality = 0.85;
          const minQuality = 0.3;

          const processCanvas = () => {
            const newDataUrl = canvas.toDataURL('image/jpeg', quality);
            const arr = newDataUrl.split(',');
            const byteString = atob(arr[1]);
            const buffer = new ArrayBuffer(byteString.length);
            const intArray = new Uint8Array(buffer);

            for (let i = 0; i < byteString.length; i++) {
              intArray[i] = byteString.charCodeAt(i);
            }

            const blob = new Blob([buffer], { type: 'image/jpeg' });

            if (blob.size > maxImageSize && quality > minQuality) {
              quality -= 0.1;
              processCanvas();
            } else {
              resolve({
                id: fileId,
                name: file.name,
                content: newDataUrl,
                size: file.size,
                mimeType: 'image/jpeg'
              });
            }
          };

          processCanvas();
        };

        image.onerror = () => {
          reject(new Error('画像読み込みエラー'));
        };

        image.src = dataUrl;
      } else {
        reject(new Error('ファイル読み込みエラー'));
      }
    };

    reader.onerror = () => {
      reject(new Error('ファイル読み込みエラー'));
    };

    reader.readAsDataURL(file);
  });
}

/**
 * 音声ファイルの処理
 */
async function processAudioFile(file: File, fileId: string): Promise<FileData> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        if (event.target?.result) {
          const dataUrl = event.target.result as string;
          // MIMEタイプの取得と保存
          const mimeType = file.type || 'audio/mpeg';

          // 音声ファイル用のプレビュー作成
          const audio = new Audio();
          audio.src = dataUrl;

          // オーディオファイルのメタデータをロード
          audio.onloadedmetadata = () => {
            console.log(`音声ファイル読み込み成功: ${file.name}, 長さ: ${audio.duration}秒`);

            resolve({
              id: fileId,
              name: file.name,
              content: dataUrl,
              preview: `🔊 音声ファイル (${Math.round(audio.duration)}秒)`,
              size: file.size,
              mimeType: mimeType
            });
          };

          // エラー処理
          audio.onerror = (e) => {
            console.error('音声ファイル読み込みエラー:', e);
            // エラーが発生しても処理を継続する
            resolve({
              id: fileId,
              name: file.name,
              content: dataUrl,
              preview: '🔊 音声ファイル',
              size: file.size,
              mimeType: mimeType
            });
          };
        } else {
          reject(new Error('ファイル読み込みエラー'));
        }
      } catch (error) {
        console.error('音声ファイル処理エラー:', error);
        reject(error);
      }
    };
    reader.onerror = () => {
      reject(new Error('ファイル読み込みエラー'));
    };
    reader.readAsDataURL(file);  // データURLとして読み込み
  });
}

/**
 * PDFをページ画像として処理（複数ページ対応）
 */
async function processPdfAsImage(file: File, fileId: string, maxImageSize: number, maxLongEdge: number): Promise<FileData[]> {
  try {
    // ファイルをArrayBufferに読み込む
    const arrayBuffer = await file.arrayBuffer();

    // PDFを読み込む
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

    // ページ数を取得
    const pageCount = pdf.numPages;
    const results: FileData[] = [];

    // 各ページを処理
    for (let i = 1; i <= pageCount; i++) {
      const page = await pdf.getPage(i);

      // ビューポートを設定
      const viewport = page.getViewport({ scale: 1.0 });

      // スケール調整
      let scale = 1.0;
      const longEdge = Math.max(viewport.width, viewport.height);
      if (longEdge > maxLongEdge) {
        scale = maxLongEdge / longEdge;
      }

      const scaledViewport = page.getViewport({ scale });

      // キャンバスを作成
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d');
      canvas.width = scaledViewport.width;
      canvas.height = scaledViewport.height;

      if (!context) {
        throw new Error('キャンバスの作成に失敗しました');
      }

      // PDFをレンダリング
      await page.render({
        canvasContext: context,
        viewport: scaledViewport
      }).promise;

      // 画像を取得
      let quality = 0.8;
      let imageData = canvas.toDataURL('image/jpeg', quality);

      // サイズチェック
      while (imageData.length > maxImageSize && quality > 0.3) {
        quality -= 0.1;
        imageData = canvas.toDataURL('image/jpeg', quality);
      }

      results.push({
        id: `${fileId}_page${i}`,
        name: `${file.name} (ページ ${i}/${pageCount})`,
        content: imageData,
        preview: `PDF ページ ${i}/${pageCount}`,
        size: Math.floor(file.size / pageCount), // 概算
        mimeType: 'image/jpeg'
      });
    }

    return results;
  } catch (error) {
    console.error('PDF処理エラー:', error);
    throw new Error('PDF処理に失敗しました');
  }
}

/**
 * PDFからテキストを抽出
 */
async function processPdfAsText(file: File, fileId: string): Promise<FileData> {
  try {
    // ファイルをArrayBufferに読み込む
    const arrayBuffer = await file.arrayBuffer();

    // PDFを読み込む
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

    // ページ数を取得
    const pageCount = pdf.numPages;
    let fullText = '';

    // 全ページからテキスト抽出
    for (let i = 1; i <= pageCount; i++) {
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      const pageText = textContent.items.map((item: any) => item.str).join(' ');
      fullText += `--- ページ ${i} ---\n${pageText}\n\n`;
    }

    // プレビュー用のテキスト
    const preview = fullText.substring(0, 200) + (fullText.length > 200 ? '...' : '');

    return {
      id: fileId,
      name: file.name,
      content: fullText,
      preview: preview,
      size: file.size,
      mimeType: 'application/pdf'
    };
  } catch (error) {
    console.error('PDFテキスト抽出エラー:', error);
    throw new Error('PDFからのテキスト抽出に失敗しました');
  }
}

/**
 * CSVファイルの処理
 */
async function processCsvFile(file: File, fileId: string): Promise<FileData> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = async (event) => {
      try {
        if (event.target?.result) {
          const content = event.target.result as string;

          // XLSXでCSVを解析してプレビュー作成
          const workbook = XLSX.read(content, { type: 'string' });
          const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
          const jsonData = XLSX.utils.sheet_to_json(firstSheet, { header: 1 });

          // プレビュー用に最初の数行を表示
          const previewRows = jsonData.slice(0, 3);
          const preview = previewRows
            .map(row => (row as any[]).join(', '))
            .join('\n') + (jsonData.length > 3 ? '\n...' : '');

          resolve({
            id: fileId,
            name: file.name,
            content: content,
            preview: preview,
            size: file.size,
            mimeType: 'text/csv'
          });
        } else {
          reject(new Error('ファイル読み込みエラー'));
        }
      } catch (error) {
        reject(error);
      }
    };
    reader.onerror = () => {
      reject(new Error('ファイル読み込みエラー'));
    };
    reader.readAsText(file);
  });
}

/**
 * DOCXファイルの処理
 */
async function processDocxFile(file: File, fileId: string): Promise<FileData> {
  try {
    const arrayBuffer = await file.arrayBuffer();
    const result = await mammoth.extractRawText({ arrayBuffer });
    const text = result.value;

    // プレビュー用に最初の数百文字を表示
    const preview = text.substring(0, 200) + (text.length > 200 ? '...' : '');

    return {
      id: fileId,
      name: file.name,
      content: text,
      preview: preview,
      size: file.size,
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    };
  } catch (error) {
    console.error('DOCX処理エラー:', error);
    throw new Error('DOCXファイルの処理に失敗しました');
  }
}

/**
 * テキストファイルの処理
 */
async function processTextFile(file: File, fileId: string): Promise<FileData> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      if (event.target?.result) {
        const content = event.target.result as string;
        const preview = content.substring(0, 200) + (content.length > 200 ? '...' : '');

        resolve({
          id: fileId,
          name: file.name,
          content: content,
          preview: preview,
          size: file.size,
          mimeType: 'text/plain'
        });
      } else {
        reject(new Error('ファイル読み込みエラー'));
      }
    };
    reader.onerror = () => {
      reject(new Error('ファイル読み込みエラー'));
    };
    reader.readAsText(file);
  });
}

/**
 * ファイルデータをAPIリクエスト用に変換
 */
export function convertFileDataForApi(files: FileData[]): any {
  const apiData: any = {
    files: files
  };

  return apiData;
}