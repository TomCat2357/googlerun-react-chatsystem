// frontend/src/component/Whisper/WhisperTranscriptPlayer.tsx
import React, { useState, useRef, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import { generateRequestId } from '../../utils/requestIdUtils';
import { SpeakerConfig, SpeakerStats } from "../../types/apiTypes";

interface Segment {
  start: number;
  end: number;
  text: string;
  speaker: string;
}

interface WhisperTranscriptPlayerProps {
  jobData: {
    id: string;
    filename: string;
    gcs_audio_url: string;
    segments: Segment[];
    audio_duration_ms?: number; // 音声全体の長さ（ミリ秒）
    audio_size?: number; // 音声全体のサイズ（バイト）
    file_hash?: string; // ファイルハッシュを追加
  };
  onSaveEdit: (editedSegments: any[]) => void;
}

// デフォルト色パレット（話者用）
const DEFAULT_SPEAKER_COLORS = [
  "#3B82F6", // blue-500
  "#EF4444", // red-500
  "#10B981", // emerald-500
  "#F59E0B", // amber-500
  "#8B5CF6", // violet-500
  "#EC4899", // pink-500
  "#06B6D4", // cyan-500
  "#84CC16", // lime-500
  "#F97316", // orange-500
  "#6366F1", // indigo-500
];

const WhisperTranscriptPlayer: React.FC<WhisperTranscriptPlayerProps> = ({
  jobData,
  onSaveEdit
}) => {
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // 既存のstate
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedSegments, setEditedSegments] = useState<Segment[]>([]);
  const [hasEdits, setHasEdits] = useState(false);
  
  // 新しいstate（スピーカー設定関連）
  const [speakerConfig, setSpeakerConfig] = useState<SpeakerConfig>({});
  const [showSpeakerPanel, setShowSpeakerPanel] = useState(false);
  const [speakerStats, setSpeakerStats] = useState<SpeakerStats>({});
  const [hasSpeakerConfigEdits, setHasSpeakerConfigEdits] = useState(false);
  const [selectedSpeakers, setSelectedSpeakers] = useState<Set<string>>(new Set());
  
  const audioRef = useRef<HTMLAudioElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const currentSegmentSourceRef = useRef<AudioBufferSourceNode | null>(null);
  
  // スピーカー一覧を取得
  const uniqueSpeakers = React.useMemo(() => {
    const speakers = new Set<string>();
    editedSegments.forEach(segment => speakers.add(segment.speaker));
    return Array.from(speakers).sort();
  }, [editedSegments]);

  // デフォルトスピーカー設定を生成
  const generateDefaultSpeakerConfig = (speakers: string[]): SpeakerConfig => {
    const config: SpeakerConfig = {};
    speakers.forEach((speaker, index) => {
      config[speaker] = {
        name: speaker,
        color: DEFAULT_SPEAKER_COLORS[index % DEFAULT_SPEAKER_COLORS.length]
      };
    });
    return config;
  };

  // スピーカー統計を計算
  const calculateSpeakerStats = (segments: Segment[]): SpeakerStats => {
    const stats: SpeakerStats = {};
    const totalDuration = segments.reduce((sum, seg) => sum + (seg.end - seg.start), 0);
    
    segments.forEach(segment => {
      const duration = segment.end - segment.start;
      if (!stats[segment.speaker]) {
        stats[segment.speaker] = {
          totalDuration: 0,
          segmentCount: 0,
          percentage: 0
        };
      }
      stats[segment.speaker].totalDuration += duration;
      stats[segment.speaker].segmentCount += 1;
    });
    
    // パーセンテージを計算
    Object.keys(stats).forEach(speaker => {
      stats[speaker].percentage = totalDuration > 0 
        ? (stats[speaker].totalDuration / totalDuration) * 100 
        : 0;
    });
    
    return stats;
  };

  // スピーカー設定をサーバーから取得
  const fetchSpeakerConfig = async () => {
    if (!jobData.file_hash) return;
    
    try {
      const requestId = generateRequestId();
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${jobData.file_hash}/speaker_config`, {
        method: "GET",
        headers: {
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        }
      });

      if (response.ok) {
        const config = await response.json();
        setSpeakerConfig(config);
      } else {
        // 設定が存在しない場合はデフォルト設定を使用
        const defaultConfig = generateDefaultSpeakerConfig(uniqueSpeakers);
        setSpeakerConfig(defaultConfig);
      }
    } catch (error) {
      console.error("スピーカー設定取得エラー:", error);
      const defaultConfig = generateDefaultSpeakerConfig(uniqueSpeakers);
      setSpeakerConfig(defaultConfig);
    }
  };

  // スピーカー設定をサーバーに保存
  const saveSpeakerConfig = async () => {
    if (!jobData.file_hash) return;
    
    try {
      const requestId = generateRequestId();
      const response = await fetch(`${API_BASE_URL}/backend/whisper/jobs/${jobData.file_hash}/speaker_config`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Request-Id": requestId
        },
        body: JSON.stringify({ speaker_config: speakerConfig })
      });

      if (response.ok) {
        alert("スピーカー設定を保存しました");
        setHasSpeakerConfigEdits(false);
      } else {
        throw new Error("スピーカー設定の保存に失敗しました");
      }
    } catch (error) {
      console.error("スピーカー設定保存エラー:", error);
      alert("スピーカー設定の保存に失敗しました");
    }
  };

  // 初期データのロード
  useEffect(() => {
    if (jobData?.segments) {
      const segments = JSON.parse(JSON.stringify(jobData.segments));
      setEditedSegments(segments);
      
      // スピーカー統計を計算
      const stats = calculateSpeakerStats(segments);
      setSpeakerStats(stats);
    }
  }, [jobData]);

  // スピーカー設定の初期化
  useEffect(() => {
    if (uniqueSpeakers.length > 0) {
      fetchSpeakerConfig();
    }
  }, [uniqueSpeakers, jobData.file_hash]);

  // スピーカー設定が空の場合にデフォルト設定を適用
  useEffect(() => {
    if (uniqueSpeakers.length > 0 && Object.keys(speakerConfig).length === 0) {
      const defaultConfig = generateDefaultSpeakerConfig(uniqueSpeakers);
      setSpeakerConfig(defaultConfig);
    }
  }, [uniqueSpeakers, speakerConfig]);

  // AudioContextの初期化
  useEffect(() => {
    audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    
    return () => {
      if (currentSegmentSourceRef.current) {
        currentSegmentSourceRef.current.stop();
        currentSegmentSourceRef.current.disconnect();
      }
      
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  // 既存の音声再生関連の関数...
  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
    }
  };

  const togglePlayPause = () => {
    if (!audioRef.current) return;
    
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  const changePlaybackRate = (rate: number) => {
    if (audioRef.current) {
      audioRef.current.playbackRate = rate;
      setPlaybackRate(rate);
    }
  };

  const handleSegmentClick = (start: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = start;
      setCurrentTime(start);
    }
  };

  const handleSegmentDoubleClick = async (index: number) => {
    if (!audioContextRef.current || !jobData || !jobData.segments[index]) {
      console.error("AudioContextまたはジョブデータが利用できません");
      return;
    }

    const segment = jobData.segments[index];
    const { gcs_audio_url, audio_duration_ms, audio_size } = jobData;

    if (!audio_duration_ms || !audio_size || audio_duration_ms <= 0 || audio_size <= 0) {
      console.error("音声長さまたはサイズのデータが不正です。フォールバック処理を実行します。");
      if (audioRef.current) {
        audioRef.current.currentTime = segment.start;
        setCurrentTime(segment.start);
        audioRef.current.play();
        setIsPlaying(true);
      }
      return;
    }

    if (currentSegmentSourceRef.current) {
      currentSegmentSourceRef.current.stop();
      currentSegmentSourceRef.current.disconnect();
      currentSegmentSourceRef.current = null;
    }
    
    if (audioRef.current && !audioRef.current.paused) {
      audioRef.current.pause();
      setIsPlaying(false);
    }

    const bytesPerSecond = audio_size / (audio_duration_ms / 1000);
    const startByte = Math.floor(segment.start * bytesPerSecond);
    const endByte = Math.min(audio_size - 1, Math.floor(segment.end * bytesPerSecond));

    if (startByte >= endByte) {
      console.warn("計算された開始バイトが終了バイト以上です。セグメント再生をスキップします:", segment);
      return;
    }

    try {
      const response = await fetch(gcs_audio_url, {
        headers: { Range: `bytes=${startByte}-${endByte}` },
      });
      
      if (!response.ok) {
        throw new Error(`HTTP Range Requestが失敗しました: ${response.status}`);
      }
      
      const audioData = await response.arrayBuffer();
      const audioBuffer = await audioContextRef.current.decodeAudioData(audioData);
      
      const source = audioContextRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContextRef.current.destination);
      source.start(0);
      
      currentSegmentSourceRef.current = source;
      setCurrentTime(segment.start);
    } catch (error) {
      console.error("HTTP Range Requestによるセグメント再生中にエラーが発生しました:", error);
      if (audioRef.current) {
        audioRef.current.currentTime = segment.start;
        setCurrentTime(segment.start);
      }
    }
  };

  // セグメント編集の確定
  const handleSegmentEdit = (index: number, newText: string) => {
    const speakerMatch = newText.match(/^\[(SPEAKER_\d+|[A-Za-z0-9_]+)\]/);
    let speakerTag = editedSegments[index].speaker;
    let textContent = newText;
    
    if (speakerMatch) {
      speakerTag = speakerMatch[1];
      textContent = newText.substring(speakerMatch[0].length).trim();
    }
    
    const newSegments = [...editedSegments];
    newSegments[index] = {
      ...newSegments[index],
      text: textContent,
      speaker: speakerTag
    };
    
    setEditedSegments(newSegments);
    setHasEdits(true);
    
    // 統計を再計算
    const stats = calculateSpeakerStats(newSegments);
    setSpeakerStats(stats);
  };

  // 編集内容の保存
  const saveEdits = () => {
    onSaveEdit(editedSegments);
    setHasEdits(false);
  };

  // スピーカー設定の更新
  const updateSpeakerConfig = (speakerId: string, name: string, color: string) => {
    setSpeakerConfig(prev => ({
      ...prev,
      [speakerId]: { name, color }
    }));
    setHasSpeakerConfigEdits(true);
  };

  // スピーカーフィルタの切り替え
  const toggleSpeakerFilter = (speakerId: string) => {
    setSelectedSpeakers(prev => {
      const newSelected = new Set(prev);
      if (newSelected.has(speakerId)) {
        newSelected.delete(speakerId);
      } else {
        newSelected.add(speakerId);
      }
      return newSelected;
    });
  };

  // 時間を「00:00:00」形式に変換
  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // フィルタリングされたセグメント
  const filteredSegments = React.useMemo(() => {
    if (selectedSpeakers.size === 0) return editedSegments;
    return editedSegments.filter(segment => selectedSpeakers.has(segment.speaker));
  }, [editedSegments, selectedSpeakers]);

  // エクスポート機能
  const exportTranscript = (format: 'txt' | 'srt' | 'json') => {
    let content = '';
    const filename = `${jobData.filename}_transcript.${format}`;

    switch (format) {
      case 'txt':
        content = editedSegments.map(segment => {
          const speakerInfo = speakerConfig[segment.speaker] || { name: segment.speaker };
          return `[${speakerInfo.name}] ${segment.text}`;
        }).join('\n\n');
        break;
        
      case 'srt':
        content = editedSegments.map((segment, index) => {
          const speakerInfo = speakerConfig[segment.speaker] || { name: segment.speaker };
          const startTime = formatSRTTime(segment.start);
          const endTime = formatSRTTime(segment.end);
          return `${index + 1}\n${startTime} --> ${endTime}\n[${speakerInfo.name}] ${segment.text}\n`;
        }).join('\n');
        break;
        
      case 'json':
        const exportData = {
          filename: jobData.filename,
          speakerConfig,
          segments: editedSegments.map(segment => ({
            ...segment,
            speakerName: speakerConfig[segment.speaker]?.name || segment.speaker
          }))
        };
        content = JSON.stringify(exportData, null, 2);
        break;
    }

    // ダウンロード
    const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // SRT形式の時間フォーマット
  const formatSRTTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')},${ms.toString().padStart(3, '0')}`;
  };

  // キーボードショートカット
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/Cmd + キーの組み合わせのみ処理
      if (!e.ctrlKey && !e.metaKey) return;
      
      switch (e.key) {
        case ' ': // Ctrl/Cmd + Space で再生/一時停止
          e.preventDefault();
          togglePlayPause();
          break;
        case 's': // Ctrl/Cmd + S で保存
          e.preventDefault();
          if (hasEdits) saveEdits();
          if (hasSpeakerConfigEdits) saveSpeakerConfig();
          break;
        case 'e': // Ctrl/Cmd + E で編集モード切り替え
          e.preventDefault();
          setIsEditMode(!isEditMode);
          break;
        case 'p': // Ctrl/Cmd + P でスピーカーパネル切り替え
          e.preventDefault();
          setShowSpeakerPanel(!showSpeakerPanel);
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isEditMode, showSpeakerPanel, hasEdits, hasSpeakerConfigEdits]);

  return (
    <div className="flex gap-4">
      {/* メインコンテンツエリア */}
      <div className="flex-1">
        <h2 className="text-xl font-bold mb-4">
          {jobData.filename} の文字起こし結果
        </h2>
        
        {/* オーディオ要素 */}
        <audio
          ref={audioRef}
          src={jobData.gcs_audio_url}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
        />
        
        {/* 再生コントロール */}
        <div className="mb-6">
          <div className="flex items-center mb-4 flex-wrap gap-2">
            <button
              onClick={togglePlayPause}
              className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded"
            >
              {isPlaying ? "一時停止" : "再生"}
            </button>
            
            <select
              value={playbackRate}
              onChange={(e) => changePlaybackRate(parseFloat(e.target.value))}
              className="bg-gray-700 text-white rounded px-2 py-1"
            >
              <option value="0.5">0.5x</option>
              <option value="0.75">0.75x</option>
              <option value="1">1.0x</option>
              <option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option>
              <option value="2">2.0x</option>
            </select>
            
            <label className="flex items-center text-gray-300">
              <input
                type="checkbox"
                checked={isEditMode}
                onChange={(e) => setIsEditMode(e.target.checked)}
                className="mr-2"
              />
              編集モード
            </label>
            
            <button
              onClick={() => setShowSpeakerPanel(!showSpeakerPanel)}
              className="bg-purple-500 hover:bg-purple-600 text-white px-3 py-2 rounded"
            >
              スピーカー設定
            </button>

            {/* エクスポートボタン */}
            <div className="relative group">
              <button className="bg-gray-600 hover:bg-gray-700 text-white px-3 py-2 rounded">
                エクスポート
              </button>
              <div className="absolute right-0 mt-1 bg-gray-800 rounded shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-10">
                <button
                  onClick={() => exportTranscript('txt')}
                  className="block w-full text-left px-4 py-2 text-white hover:bg-gray-700 rounded-t"
                >
                  テキスト (.txt)
                </button>
                <button
                  onClick={() => exportTranscript('srt')}
                  className="block w-full text-left px-4 py-2 text-white hover:bg-gray-700"
                >
                  字幕 (.srt)
                </button>
                <button
                  onClick={() => exportTranscript('json')}
                  className="block w-full text-left px-4 py-2 text-white hover:bg-gray-700 rounded-b"
                >
                  JSON (.json)
                </button>
              </div>
            </div>
            
            {isEditMode && hasEdits && (
              <button
                onClick={saveEdits}
                className="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded"
              >
                文字起こしを保存
              </button>
            )}
            
            {hasSpeakerConfigEdits && (
              <button
                onClick={saveSpeakerConfig}
                className="bg-orange-500 hover:bg-orange-600 text-white px-3 py-1 rounded"
              >
                スピーカー設定を保存
              </button>
            )}
          </div>
          
          {/* シークバー */}
          <div className="flex items-center">
            <span className="text-sm mr-2">{formatTime(currentTime)}</span>
            <input
              type="range"
              min="0"
              max={duration || 0}
              step="0.1"
              value={currentTime}
              onChange={handleSeek}
              className="flex-grow"
            />
            <span className="text-sm ml-2">{formatTime(duration)}</span>
          </div>
        </div>
        
        {/* 編集モードの説明とキーボードショートカット */}
        <div className="bg-gray-800 p-3 rounded mb-4 text-sm">
          {isEditMode && (
            <div className="mb-3">
              <p><strong>編集方法:</strong></p>
              <ul className="list-disc ml-5 mt-1">
                <li>テキストをクリックして編集できます</li>
                <li>話者タグは [SPEAKER_XX] の形式で編集できます</li>
                <li>スピーカー設定パネルで話者名と色をカスタマイズできます</li>
                <li>変更後は対応する保存ボタンをクリックしてください</li>
              </ul>
            </div>
          )}
          <div>
            <p><strong>キーボードショートカット:</strong></p>
            <div className="grid grid-cols-2 gap-2 mt-1 text-xs">
              <div><kbd className="bg-gray-700 px-1 rounded">Ctrl+Space</kbd> 再生/一時停止</div>
              <div><kbd className="bg-gray-700 px-1 rounded">Ctrl+E</kbd> 編集モード切り替え</div>
              <div><kbd className="bg-gray-700 px-1 rounded">Ctrl+S</kbd> 保存</div>
              <div><kbd className="bg-gray-700 px-1 rounded">Ctrl+P</kbd> スピーカー設定</div>
            </div>
          </div>
        </div>
        
        {/* 文字起こし結果 */}
        <div className="bg-white text-black p-4 rounded max-h-[500px] overflow-y-auto">
          {filteredSegments.map((segment, originalIndex) => {
            const actualIndex = editedSegments.findIndex(s => s === segment);
            const isActive = currentTime >= segment.start && currentTime < segment.end;
            const speakerInfo = speakerConfig[segment.speaker] || { 
              name: segment.speaker, 
              color: DEFAULT_SPEAKER_COLORS[0] 
            };
            
            return (
              <div
                key={actualIndex}
                style={{
                  backgroundColor: isActive ? "#ffd700" : "#f8f9fa",
                  padding: "8px",
                  margin: "4px 0",
                  borderRadius: "4px",
                  cursor: "pointer",
                  borderLeft: `4px solid ${speakerInfo.color}`
                }}
                onClick={() => handleSegmentClick(segment.start)}
                onDoubleClick={() => handleSegmentDoubleClick(actualIndex)}
              >
                <div className="flex items-start gap-2">
                  {/* スピーカータグ */}
                  <span
                    className="inline-block px-2 py-1 rounded text-xs font-semibold text-white flex-shrink-0"
                    style={{ backgroundColor: speakerInfo.color }}
                  >
                    {speakerInfo.name}
                  </span>
                  
                  {/* テキスト部分 */}
                  <div className="flex-1">
                    {isEditMode ? (
                      <span
                        contentEditable
                        suppressContentEditableWarning
                        onBlur={(e) => handleSegmentEdit(actualIndex, `[${segment.speaker}] ${e.currentTarget.textContent || ""}`)}
                        className="block min-w-[50px] p-1 border border-gray-300 rounded"
                      >
                        {segment.text}
                      </span>
                    ) : (
                      <span>{segment.text}</span>
                    )}
                  </div>
                </div>
                
                {/* 時間情報 */}
                <div className="text-xs text-gray-500 mt-1 ml-2">
                  {formatTime(segment.start)} - {formatTime(segment.end)}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* スピーカー設定パネル */}
      {showSpeakerPanel && (
        <div className="w-80 bg-gray-800 p-4 rounded max-h-[600px] overflow-y-auto">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-bold">スピーカー設定</h3>
            <button
              onClick={() => setShowSpeakerPanel(false)}
              className="text-gray-400 hover:text-white"
            >
              ✕
            </button>
          </div>
          
          {/* スピーカーフィルター */}
          <div className="mb-4">
            <div className="flex justify-between items-center mb-2">
              <h4 className="text-sm font-semibold">フィルター</h4>
              <div className="flex gap-1">
                <button
                  onClick={() => setSelectedSpeakers(new Set())}
                  className="text-xs text-blue-400 hover:text-blue-300"
                >
                  すべて
                </button>
                <span className="text-xs text-gray-400">|</span>
                <button
                  onClick={() => setSelectedSpeakers(new Set(uniqueSpeakers))}
                  className="text-xs text-red-400 hover:text-red-300"
                >
                  なし
                </button>
              </div>
            </div>
            <div className="space-y-1">
              {uniqueSpeakers.map(speakerId => {
                const speakerInfo = speakerConfig[speakerId] || { 
                  name: speakerId, 
                  color: DEFAULT_SPEAKER_COLORS[0] 
                };
                return (
                  <label key={speakerId} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selectedSpeakers.size === 0 || selectedSpeakers.has(speakerId)}
                      onChange={() => toggleSpeakerFilter(speakerId)}
                    />
                    <span
                      className="w-3 h-3 rounded inline-block"
                      style={{ backgroundColor: speakerInfo.color }}
                    />
                    <span className="text-sm flex-1">{speakerInfo.name}</span>
                    <span className="text-xs text-gray-400">
                      {speakerStats[speakerId]?.segmentCount || 0}回
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* スピーカー統計 */}
          <div className="mb-4">
            <h4 className="text-sm font-semibold mb-2">統計</h4>
            <div className="bg-gray-700 rounded p-3">
              <div className="grid grid-cols-2 gap-2 text-xs mb-2">
                <div>総発言時間: {formatTime(Object.values(speakerStats).reduce((sum, s) => sum + s.totalDuration, 0))}</div>
                <div>総発言回数: {Object.values(speakerStats).reduce((sum, s) => sum + s.segmentCount, 0)}回</div>
              </div>
              <div className="space-y-2">
                {Object.entries(speakerStats)
                  .sort(([,a], [,b]) => b.totalDuration - a.totalDuration)
                  .map(([speakerId, stats]) => {
                    const speakerInfo = speakerConfig[speakerId] || { 
                      name: speakerId, 
                      color: DEFAULT_SPEAKER_COLORS[0] 
                    };
                    return (
                      <div key={speakerId} className="text-xs">
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <span
                              className="w-3 h-3 rounded inline-block"
                              style={{ backgroundColor: speakerInfo.color }}
                            />
                            <span className="font-medium">{speakerInfo.name}</span>
                          </div>
                          <span className="text-orange-400">{stats.percentage.toFixed(1)}%</span>
                        </div>
                        <div className="ml-5 text-gray-400">
                          {formatTime(stats.totalDuration)} • {stats.segmentCount}回
                        </div>
                        <div className="ml-5 mt-1">
                          <div className="w-full bg-gray-600 rounded-full h-1">
                            <div 
                              className="h-1 rounded-full"
                              style={{ 
                                width: `${stats.percentage}%`,
                                backgroundColor: speakerInfo.color 
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })
                }
              </div>
            </div>
          </div>

          {/* スピーカー設定編集 */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <h4 className="text-sm font-semibold">カスタマイズ</h4>
              <button
                onClick={() => {
                  const defaultConfig = generateDefaultSpeakerConfig(uniqueSpeakers);
                  setSpeakerConfig(defaultConfig);
                  setHasSpeakerConfigEdits(true);
                }}
                className="text-xs text-yellow-400 hover:text-yellow-300"
              >
                リセット
              </button>
            </div>
            <div className="space-y-3">
              {uniqueSpeakers.map((speakerId, index) => {
                const speakerInfo = speakerConfig[speakerId] || { 
                  name: speakerId, 
                  color: DEFAULT_SPEAKER_COLORS[index % DEFAULT_SPEAKER_COLORS.length] 
                };
                return (
                  <div key={speakerId} className="bg-gray-700 p-2 rounded">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs text-gray-400 w-16">#{index + 1}</span>
                      <span className="text-xs flex-1">{speakerId}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={speakerInfo.color}
                        onChange={(e) => updateSpeakerConfig(speakerId, speakerInfo.name, e.target.value)}
                        className="w-8 h-8 rounded border-0 cursor-pointer"
                        title="色を選択"
                      />
                      <input
                        type="text"
                        value={speakerInfo.name}
                        onChange={(e) => updateSpeakerConfig(speakerId, e.target.value, speakerInfo.color)}
                        className="flex-1 bg-gray-600 text-white px-2 py-1 rounded text-sm"
                        placeholder="スピーカー名"
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            
            {/* 一括設定ツール */}
            <div className="mt-4 pt-3 border-t border-gray-600">
              <h5 className="text-xs font-semibold mb-2 text-gray-300">クイック設定</h5>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => {
                    const newConfig = { ...speakerConfig };
                    uniqueSpeakers.forEach((speakerId, index) => {
                      if (newConfig[speakerId]) {
                        newConfig[speakerId].name = `話者${index + 1}`;
                      }
                    });
                    setSpeakerConfig(newConfig);
                    setHasSpeakerConfigEdits(true);
                  }}
                  className="text-xs bg-blue-600 hover:bg-blue-700 px-2 py-1 rounded"
                >
                  話者1,2,3...
                </button>
                <button
                  onClick={() => {
                    const newConfig = { ...speakerConfig };
                    const roles = ['司会', '参加者A', '参加者B', '参加者C', '参加者D'];
                    uniqueSpeakers.forEach((speakerId, index) => {
                      if (newConfig[speakerId]) {
                        newConfig[speakerId].name = roles[index] || `参加者${String.fromCharCode(65 + index - roles.length + 1)}`;
                      }
                    });
                    setSpeakerConfig(newConfig);
                    setHasSpeakerConfigEdits(true);
                  }}
                  className="text-xs bg-green-600 hover:bg-green-700 px-2 py-1 rounded"
                >
                  司会・参加者
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WhisperTranscriptPlayer;