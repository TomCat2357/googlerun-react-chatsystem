import React, { useState } from 'react';
import { Download, FileText, FileSpreadsheet, Video } from 'lucide-react';

interface Segment {
  start: number;
  end: number;
  text: string;
  speaker: string;
}

interface WhisperExporterProps {
  segments: Segment[];
  filename: string;
  summary?: string;
  translations?: Record<string, any>;
}

const WhisperExporter: React.FC<WhisperExporterProps> = ({
  segments,
  filename,
  summary,
  translations
}) => {
  const [exportFormat, setExportFormat] = useState<'txt' | 'srt' | 'vtt' | 'csv' | 'json'>('txt');
  const [includeSpeakers, setIncludeSpeakers] = useState(true);
  const [includeTimestamps, setIncludeTimestamps] = useState(true);

  const formatTime = (seconds: number, format: 'srt' | 'vtt' | 'standard' = 'standard'): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);

    if (format === 'srt') {
      return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')},${ms.toString().padStart(3, '0')}`;
    } else if (format === 'vtt') {
      return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
    }
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const generateContent = (): string => {
    switch (exportFormat) {
      case 'txt':
        return segments.map(segment => {
          let line = '';
          if (includeTimestamps) {
            line += `[${formatTime(segment.start)} - ${formatTime(segment.end)}] `;
          }
          if (includeSpeakers && segment.speaker) {
            line += `${segment.speaker}: `;
          }
          line += segment.text;
          return line;
        }).join('\n\n');

      case 'srt':
        return segments.map((segment, index) => {
          return [
            index + 1,
            `${formatTime(segment.start, 'srt')} --> ${formatTime(segment.end, 'srt')}`,
            includeSpeakers && segment.speaker ? `${segment.speaker}: ${segment.text}` : segment.text,
            ''
          ].join('\n');
        }).join('\n');

      case 'vtt':
        let vttContent = 'WEBVTT\n\n';
        vttContent += segments.map(segment => {
          return [
            `${formatTime(segment.start, 'vtt')} --> ${formatTime(segment.end, 'vtt')}`,
            includeSpeakers && segment.speaker ? `${segment.speaker}: ${segment.text}` : segment.text,
            ''
          ].join('\n');
        }).join('\n');
        return vttContent;

      case 'csv':
        const csvHeader = ['Start Time', 'End Time', 'Speaker', 'Text'].join(',');
        const csvRows = segments.map(segment => {
          return [
            segment.start,
            segment.end,
            segment.speaker || '',
            `"${segment.text.replace(/"/g, '""')}"`  // CSVエスケープ
          ].join(',');
        });
        return [csvHeader, ...csvRows].join('\n');

      case 'json':
        const exportData = {
          filename,
          exported_at: new Date().toISOString(),
          segments,
          summary,
          translations,
          metadata: {
            total_segments: segments.length,
            total_duration: Math.max(...segments.map(s => s.end)),
            speakers: [...new Set(segments.map(s => s.speaker).filter(Boolean))]
          }
        };
        return JSON.stringify(exportData, null, 2);

      default:
        return '';
    }
  };

  const downloadFile = () => {
    const content = generateContent();
    const blob = new Blob([content], {
      type: exportFormat === 'json' ? 'application/json' : 'text/plain;charset=utf-8'
    });
    
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename.replace(/\.[^/.]+$/, '')}.${exportFormat}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const getFormatIcon = () => {
    switch (exportFormat) {
      case 'csv':
        return <FileSpreadsheet className="w-4 h-4" />;
      case 'json':
        return <FileText className="w-4 h-4" />;
      case 'srt':
      case 'vtt':
        return <Video className="w-4 h-4" />;
      default:
        return <FileText className="w-4 h-4" />;
    }
  };

  return (
    <div className="bg-white p-6 rounded-lg shadow-md">
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <Download className="w-5 h-5" />
        エクスポート
      </h3>
      
      <div className="space-y-4">
        {/* フォーマット選択 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            エクスポート形式
          </label>
          <select
            value={exportFormat}
            onChange={(e) => setExportFormat(e.target.value as any)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="txt">テキストファイル (.txt)</option>
            <option value="srt">字幕ファイル (.srt)</option>
            <option value="vtt">WebVTT (.vtt)</option>
            <option value="csv">CSVファイル (.csv)</option>
            <option value="json">JSONファイル (.json)</option>
          </select>
        </div>

        {/* オプション */}
        <div className="space-y-2">
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={includeSpeakers}
              onChange={(e) => setIncludeSpeakers(e.target.checked)}
              className="mr-2"
            />
            話者情報を含める
          </label>
          
          {exportFormat !== 'srt' && exportFormat !== 'vtt' && (
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={includeTimestamps}
                onChange={(e) => setIncludeTimestamps(e.target.checked)}
                className="mr-2"
              />
              タイムスタンプを含める
            </label>
          )}
        </div>

        {/* プレビュー */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            プレビュー
          </label>
          <textarea
            value={generateContent().substring(0, 500) + (generateContent().length > 500 ? '...' : '')}
            readOnly
            rows={6}
            className="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-50 text-sm font-mono"
          />
        </div>

        {/* ダウンロードボタン */}
        <button
          onClick={downloadFile}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors"
        >
          {getFormatIcon()}
          ダウンロード (.{exportFormat})
        </button>
      </div>
    </div>
  );
};

export default WhisperExporter;