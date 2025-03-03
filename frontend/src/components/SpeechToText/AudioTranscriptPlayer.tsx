// frontend/src/components/SpeechToText/AudioTranscriptPlayer.tsx
import React, { useRef, useState } from "react";
import { AudioInfo } from "./AudioUploader";

export interface TimedSegment {
  start_time: string;
  end_time: string;
  text: string;
}

interface AudioTranscriptPlayerProps {
  audioData: string;
  audioInfo: AudioInfo | null;
  serverTimedTranscript: TimedSegment[];
  serverTranscript: string;  // この行を削除しないでください
  isEditMode: boolean;
  onEditModeChange: (isEdit: boolean) => void;
  editedTranscriptSegments: string[];
  onEditedTranscriptChange: (segments: string[]) => void;
}

const timeStringToSeconds = (timeStr: string): number => {
  const parts = timeStr.split(":").map(Number);
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
};

const secondsToTimeString = (seconds: number): string => {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  return `${hrs.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

const AudioTranscriptPlayer: React.FC<AudioTranscriptPlayerProps> = ({
  audioData,
  audioInfo,
  serverTimedTranscript,
  serverTranscript: _serverTranscript, // この行を追加
  isEditMode,
  onEditModeChange,
  editedTranscriptSegments,
  onEditedTranscriptChange
}) => {
  // Player state
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [sliderValue, setSliderValue] = useState(0);
  const [cursorTime, setCursorTime] = useState<string | null>(null);
  const [showTimestamps, setShowTimestamps] = useState(false);
  
  // 追加: 現在の選択範囲と位置を保存するための変数
  const [selectionInfo, setSelectionInfo] = useState<{
    element: HTMLElement | null;
    start: number;
    end: number;
  }>({ element: null, start: 0, end: 0 });
  
  const audioRef = useRef<HTMLAudioElement>(null);

  const handlePlayPause = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      if (cursorTime) {
        audioRef.current.currentTime = timeStringToSeconds(cursorTime);
      }
      audioRef.current.play().catch(err => console.error("再生エラー:", err));
      setIsPlaying(true);
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      const current = audioRef.current.currentTime;
      setCurrentTime(current);
      setSliderValue(current);
      if (isPlaying) {
        setCursorTime(secondsToTimeString(current));
      }
    }
  };

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = Number(e.target.value);
    setSliderValue(newValue);
    if (audioRef.current) {
      audioRef.current.currentTime = newValue;
    }
    setCurrentTime(newValue);
    setCursorTime(secondsToTimeString(newValue));
  };

  const handleSegmentClick = (segment: TimedSegment) => {
    if (audioRef.current) {
      const stSec = timeStringToSeconds(segment.start_time);
      audioRef.current.currentTime = stSec;
      setSliderValue(stSec);
      setCurrentTime(stSec);
      setCursorTime(segment.start_time);
    }
  };

  const handleSegmentDoubleClick = (segment: TimedSegment) => {
    if (audioRef.current) {
      const stSec = timeStringToSeconds(segment.start_time);
      audioRef.current.currentTime = stSec;
      setSliderValue(stSec);
      setCurrentTime(stSec);
      audioRef.current.play().catch(err => console.error("再生エラー:", err));
      setIsPlaying(true);
      setCursorTime(segment.start_time);
    }
  };

  const handleSegmentFinalize = (
    e: React.FocusEvent<HTMLSpanElement> | React.CompositionEvent<HTMLSpanElement>,
    index: number
  ) => {
    if (!isEditMode) return;
    
    const element = e.currentTarget;
    let newText = element.innerText;
    if (!newText.trim()) {
      newText = " ";
    }
    
    // 現在のカーソル位置を保存
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) {
      const range = selection.getRangeAt(0);
      if (element.contains(range.startContainer)) {
        setSelectionInfo({
          element,
          start: range.startOffset,
          end: range.endOffset
        });
      }
    }
    
    const newSegments = [...editedTranscriptSegments];
    newSegments[index] = newText;
    onEditedTranscriptChange(newSegments);
    
    // カーソル位置を復元する処理をタイマーで遅延実行
    setTimeout(() => {
      if (selectionInfo.element === element) {
        try {
          const selection = window.getSelection();
          if (selection) {
            selection.removeAllRanges();
            const range = document.createRange();
            
            // テキストノードを取得
            let textNode = element.firstChild;
            if (!textNode) {
              // テキストノードがない場合は作成
              textNode = document.createTextNode(newText);
              element.appendChild(textNode);
            }
            
            // 安全にオフセットを設定（テキスト長を超えないように）
            const maxOffset = textNode.textContent?.length || 0;
            const safeStart = Math.min(selectionInfo.start, maxOffset);
            const safeEnd = Math.min(selectionInfo.end, maxOffset);
            
            range.setStart(textNode, safeStart);
            range.setEnd(textNode, safeEnd);
            selection.addRange(range);
          }
        } catch (err) {
          console.error("カーソル位置復元エラー:", err);
        }
      }
    }, 0);
  };

  return (
    <>
      {audioInfo && (
        <div className="mb-6">
          <div className="flex items-center mb-4">
            <button
              onClick={handlePlayPause}
              className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded mr-4"
            >
              {isPlaying ? "一時停止" : "再生"}
            </button>
            <select
              value={playbackSpeed}
              onChange={(e) => {
                const speed = Number(e.target.value);
                setPlaybackSpeed(speed);
                if (audioRef.current) {
                  audioRef.current.playbackRate = speed;
                }
              }}
              className="p-2 text-black"
            >
              <option value={0.5}>0.5x</option>
              <option value={1}>1x</option>
              <option value={1.5}>1.5x</option>
              <option value={2}>2x</option>
            </select>
            <label className="ml-4 text-gray-200">
              <input
                type="checkbox"
                checked={showTimestamps}
                onChange={() => setShowTimestamps(!showTimestamps)}
              />{" "}
              タイムスタンプ表示
            </label>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-16 text-right">
              {secondsToTimeString(sliderValue)}
            </span>
            <input
              type="range"
              min={0}
              max={audioInfo.duration.toFixed(2)}
              step={1}
              value={sliderValue}
              onChange={handleSliderChange}
              className="flex-1"
            />
            <span className="w-16">
              {audioInfo.duration
                ? secondsToTimeString(audioInfo.duration)
                : "00:00:00"}
            </span>
          </div>
        </div>
      )}

      {audioData && (
        <audio ref={audioRef} src={audioData} onTimeUpdate={handleTimeUpdate} />
      )}

      <div className="mt-6">
        <div className="flex items-center mb-4">
          <h2 className="text-xl font-bold mr-4">文字起こし結果</h2>
          <label className="flex items-center text-gray-200">
            <input
              type="checkbox"
              checked={isEditMode}
              onChange={(e) => onEditModeChange(e.target.checked)}
              className="mr-2"
            />
            修正モード
          </label>
        </div>

        {/* Transcript Display */}
        {serverTimedTranscript.length > 0 && (
          <div
            className="p-2 bg-white text-black rounded"
            style={{ lineHeight: "1.8em", maxHeight: "300px", overflowY: "auto" }}
          >
            {(() => {
              const thresholdMinutes = 1;
              let nextThresholdSec = thresholdMinutes * 60;
              
              return serverTimedTranscript.map((segment, index) => {
                const segmentStartSec = timeStringToSeconds(segment.start_time);
                const segmentEndSec = timeStringToSeconds(segment.end_time);
                const isActive = currentTime >= segmentStartSec && currentTime < segmentEndSec;
                
                const markerElements = [];
                if (showTimestamps) {
                  while (segmentStartSec >= nextThresholdSec) {
                    markerElements.push(
                      <span key={`marker-${index}-${nextThresholdSec}`} className="mr-1 text-blue-700">
                        {`{${secondsToTimeString(nextThresholdSec)}}`}
                      </span>
                    );
                    nextThresholdSec += thresholdMinutes * 60;
                  }
                }
                
                const activeColor = isEditMode ? "#32CD32" : "#ffd700";
                const inactiveColor = isEditMode ? "#B0E57C" : "#fff8b3";
                
                const highlightStyle: React.CSSProperties = {
                  backgroundColor: isActive || cursorTime === segment.start_time ? activeColor : inactiveColor,
                  marginRight: "4px",
                  padding: "2px 4px",
                  borderRadius: "4px",
                  cursor: "pointer",
                  display: "inline-block",
                  whiteSpace: "pre",
                };
                
                return (
                  <React.Fragment key={index}>
                    {markerElements}
                    {isEditMode ? (
                      <span
                        contentEditable
                        suppressContentEditableWarning
                        style={highlightStyle}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                          }
                        }}
                        // 選択範囲の変更を検出するイベントを追加
                        onSelect={(e) => {
                          const selection = window.getSelection();
                          if (selection && selection.rangeCount > 0) {
                            const range = selection.getRangeAt(0);
                            if (e.currentTarget.contains(range.startContainer)) {
                              setSelectionInfo({
                                element: e.currentTarget,
                                start: range.startOffset,
                                end: range.endOffset
                              });
                            }
                          }
                        }}
                        onBlur={(e) => handleSegmentFinalize(e, index)}
                        onCompositionEnd={(e) => handleSegmentFinalize(e, index)}
                        onClick={() => handleSegmentClick(segment)}
                        onDoubleClick={() => handleSegmentDoubleClick(segment)}
                        dangerouslySetInnerHTML={{
                          __html: editedTranscriptSegments[index] || segment.text
                        }}
                      />
                    ) : (
                      <span
                        style={highlightStyle}
                        onClick={() => handleSegmentClick(segment)}
                        onDoubleClick={() => handleSegmentDoubleClick(segment)}
                      >
                        {segment.text}
                      </span>
                    )}
                  </React.Fragment>
                );
              });
            })()}
          </div>
        )}
      </div>
    </>
  );
};

export default AudioTranscriptPlayer;