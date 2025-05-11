// frontend/src/component/Whisper/WhisperTranscriptPlayer.tsx
import React, { useState, useRef, useEffect } from "react";

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
  };
  onSaveEdit: (editedSegments: any[]) => void;
}

const WhisperTranscriptPlayer: React.FC<WhisperTranscriptPlayerProps> = ({
  jobData,
  onSaveEdit
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedSegments, setEditedSegments] = useState<Segment[]>([]);
  const [displayTexts, setDisplayTexts] = useState<string[]>([]);
  const [hasEdits, setHasEdits] = useState(false);
  
  const audioRef = useRef<HTMLAudioElement>(null);
  
  // 初期データのロード
  useEffect(() => {
    if (jobData?.segments) {
      // 深いコピーを作成
      const segments = JSON.parse(JSON.stringify(jobData.segments));
      setEditedSegments(segments);
      
      // 表示用テキストを生成
      const texts = segments.map((segment: Segment, index: number) => {
        const prevSpeaker = index > 0 ? segments[index - 1].speaker : null;
        const showSpeakerLabel = segment.speaker !== prevSpeaker;
        
        let currentText = segment.text;
        // currentTextが既に話者タグで始まっているかを確認 (例: "[Speaker01] ...")
        const speakerTagRegex = /^\[(SPEAKER_\d+|Speaker\d+|[^\]]+)\]\s*/;
        const match = currentText.match(speakerTagRegex);
        
        if (match) {
          // テキストに既に話者タグが含まれている場合、一時的に除去
          currentText = currentText.substring(match[0].length);
        }
        
        // スピーカータグを含めたテキスト（話者が変わる場合のみ）
        return showSpeakerLabel 
          ? `[${segment.speaker}] ${currentText}`
          : currentText;
      });
      
      setDisplayTexts(texts);
    }
  }, [jobData]);

  // 再生時間の更新
  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  // メタデータのロード
  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
    }
  };

  // 再生・一時停止の切り替え
  const togglePlayPause = () => {
    if (!audioRef.current) return;
    
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  // シークバーの操作
  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  // 再生速度の変更
  const changePlaybackRate = (rate: number) => {
    if (audioRef.current) {
      audioRef.current.playbackRate = rate;
      setPlaybackRate(rate);
    }
  };

  // セグメントクリック時の処理
  const handleSegmentClick = (start: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = start;
      setCurrentTime(start);
    }
  };

  // セグメントダブルクリック時の処理（再生開始）
  const handleSegmentDoubleClick = (start: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = start;
      setCurrentTime(start);
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  // セグメント編集の確定
  const handleSegmentEdit = (index: number, newText: string) => {
    // 新しいテキストを保存
    const newDisplayTexts = [...displayTexts];
    newDisplayTexts[index] = newText;
    setDisplayTexts(newDisplayTexts);
    
    // テキストからスピーカータグを抽出
    const speakerMatch = newText.match(/^\[(SPEAKER_\d+|[A-Za-z0-9_]+)\]/);
    let speakerTag = editedSegments[index].speaker; // デフォルトは既存のスピーカータグ
    let textContent = newText;
    
    if (speakerMatch) {
      // スピーカータグが見つかった場合は抽出して本文と分離
      speakerTag = speakerMatch[1];
      textContent = newText.substring(speakerMatch[0].length).trim();
    }
    
    // 編集されたセグメント情報を更新
    const newSegments = [...editedSegments];
    newSegments[index] = {
      ...newSegments[index],
      text: textContent,
      speaker: speakerTag
    };
    
    setEditedSegments(newSegments);
    setHasEdits(true);
  };

  // 編集内容の保存
  const saveEdits = () => {
    onSaveEdit(editedSegments);
    setHasEdits(false);
  };

  // 時間を「00:00:00」形式に変換
  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div>
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
        <div className="flex items-center mb-4">
          <button
            onClick={togglePlayPause}
            className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded mr-4"
          >
            {isPlaying ? "一時停止" : "再生"}
          </button>
          
          <select
            value={playbackRate}
            onChange={(e) => changePlaybackRate(parseFloat(e.target.value))}
            className="bg-gray-700 text-white rounded px-2 py-1 mr-4"
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
          
          {isEditMode && hasEdits && (
            <button
              onClick={saveEdits}
              className="ml-4 bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded"
            >
              変更内容を保存
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
      
      {/* 編集モードの説明 */}
      {isEditMode && (
        <div className="bg-blue-800 p-3 rounded mb-4 text-sm">
          <p><strong>編集方法:</strong></p>
          <ul className="list-disc ml-5 mt-1">
            <li>テキストをクリックして編集できます</li>
            <li>話者タグは [SPEAKER_XX] の形式で編集できます (例: [SPEAKER_01], [佐藤], [司会者] など)</li>
            <li>話者タグがない場合は前の話者が継続されます</li>
            <li>変更後は「変更内容を保存」ボタンをクリックしてください</li>
          </ul>
        </div>
      )}
      
      {/* 文字起こし結果 */}
      <div className="bg-white text-black p-4 rounded max-h-[500px] overflow-y-auto">
        {editedSegments.map((segment, index) => {
          // 現在の再生位置に該当するセグメントかどうか
          const isActive = 
            currentTime >= segment.start && 
            currentTime < segment.end;
          
          return (
            <div
              key={index}
              style={{
                backgroundColor: isActive ? "#ffd700" : "#f8f9fa",
                padding: "8px",
                margin: "4px 0",
                borderRadius: "4px",
                cursor: "pointer",
                borderLeft: "3px solid #ccc"
              }}
              onClick={() => handleSegmentClick(segment.start)}
              onDoubleClick={() => handleSegmentDoubleClick(segment.start)}
            >
              {/* 編集モードか通常表示か */}
              {isEditMode ? (
                <div>
                  <span
                    contentEditable
                    suppressContentEditableWarning
                    onBlur={(e) => handleSegmentEdit(index, e.currentTarget.textContent || "")}
                    dangerouslySetInnerHTML={{ __html: displayTexts[index] }}
                    style={{ 
                      display: "block", 
                      minWidth: "50px",
                      padding: "4px",
                      border: "1px solid #ddd",
                      borderRadius: "2px"
                    }}
                  />
                </div>
              ) : (
                <span>
                  {displayTexts[index]}
                </span>
              )}
              
              {/* 時間情報 */}
              <div className="text-xs text-gray-500 mt-1">
                {formatTime(segment.start)} - {formatTime(segment.end)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default WhisperTranscriptPlayer;