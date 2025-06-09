import React, { useState } from 'react';
import { useToken } from '../../hooks/useToken';
import * as Config from '../../config';
import { generateRequestId } from '../../utils/requestIdUtils';
import axios from 'axios';
import { toast } from 'react-toastify';

interface WhisperTranscriptActionsProps {
  jobId: string;
  fileHash: string;
  onTranslationComplete?: (translatedSegments: any[]) => void;
  onSummaryComplete?: (summary: string) => void;
}

const WhisperTranscriptActions: React.FC<WhisperTranscriptActionsProps> = ({
  jobId,
  fileHash,
  onTranslationComplete,
  onSummaryComplete
}) => {
  const token = useToken();
  const [isTranslating, setIsTranslating] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [targetLanguage, setTargetLanguage] = useState('en');
  const [summaryType, setSummaryType] = useState('brief');
  const [maxSummaryLength, setMaxSummaryLength] = useState(300);

  const handleTranslate = async () => {
    if (!token.getToken) {
      toast.error('認証が必要です');
      return;
    }

    setIsTranslating(true);
    try {
      const authToken = await token.getToken();
      const requestId = generateRequestId();

      const response = await axios.post(
        `${Config.API_BASE_URL}/whisper/translate`,
        {
          job_id: jobId,
          file_hash: fileHash,
          target_language: targetLanguage,
          request_id: requestId
        },
        {
          headers: {
            'Authorization': `Bearer ${authToken}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.data.success) {
        toast.success('翻訳が完了しました');
        if (onTranslationComplete) {
          onTranslationComplete(response.data.translated_segments);
        }
      }
    } catch (error: any) {
      console.error('翻訳エラー:', error);
      const errorMessage = error.response?.data?.detail || '翻訳中にエラーが発生しました';
      toast.error(errorMessage);
    } finally {
      setIsTranslating(false);
    }
  };

  const handleSummarize = async () => {
    if (!token.getToken) {
      toast.error('認証が必要です');
      return;
    }

    setIsSummarizing(true);
    try {
      const authToken = await token.getToken();
      const requestId = generateRequestId();

      const response = await axios.post(
        `${Config.API_BASE_URL}/whisper/summarize`,
        {
          job_id: jobId,
          file_hash: fileHash,
          summary_type: summaryType,
          max_length: maxSummaryLength,
          request_id: requestId
        },
        {
          headers: {
            'Authorization': `Bearer ${authToken}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.data.success) {
        toast.success('要約が完了しました');
        if (onSummaryComplete) {
          onSummaryComplete(response.data.summary);
        }
      }
    } catch (error: any) {
      console.error('要約エラー:', error);
      const errorMessage = error.response?.data?.detail || '要約中にエラーが発生しました';
      toast.error(errorMessage);
    } finally {
      setIsSummarizing(false);
    }
  };

  return (
    <div className="bg-white p-6 rounded-lg shadow-md">
      <h3 className="text-lg font-semibold mb-4">高度な処理</h3>
      
      {/* 翻訳セクション */}
      <div className="mb-6">
        <h4 className="text-md font-medium mb-2">翻訳</h4>
        <div className="flex flex-col sm:flex-row gap-2 mb-3">
          <select
            value={targetLanguage}
            onChange={(e) => setTargetLanguage(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="en">英語</option>
            <option value="ja">日本語</option>
            <option value="ko">韓国語</option>
            <option value="zh">中国語</option>
            <option value="es">スペイン語</option>
            <option value="fr">フランス語</option>
            <option value="de">ドイツ語</option>
          </select>
          <button
            onClick={handleTranslate}
            disabled={isTranslating}
            className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {isTranslating ? '翻訳中...' : '翻訳する'}
          </button>
        </div>
      </div>

      {/* 要約セクション */}
      <div className="mb-6">
        <h4 className="text-md font-medium mb-2">要約</h4>
        <div className="flex flex-col gap-2 mb-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <select
              value={summaryType}
              onChange={(e) => setSummaryType(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="brief">簡潔要約</option>
              <option value="detailed">詳細要約</option>
              <option value="bullet_points">箇条書き</option>
            </select>
            <input
              type="number"
              value={maxSummaryLength}
              onChange={(e) => setMaxSummaryLength(parseInt(e.target.value) || 300)}
              min={50}
              max={1000}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="最大文字数"
            />
          </div>
          <button
            onClick={handleSummarize}
            disabled={isSummarizing}
            className="px-4 py-2 bg-green-500 text-white rounded-md hover:bg-green-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {isSummarizing ? '要約中...' : '要約する'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default WhisperTranscriptActions;