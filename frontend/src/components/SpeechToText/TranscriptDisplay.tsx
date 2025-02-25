// frontend/src/components/SpeechToText/TranscriptDisplay.tsx

import React from "react";

export interface TimedSegment {
  start_time: string;
  end_time: string;
  text: string;
}

interface TranscriptDisplayProps {
  segments: TimedSegment[];
  isEditMode: boolean;
  editedTranscriptSegments: string[];
  onSegmentFinalize: (
    e:
      | React.FocusEvent<HTMLSpanElement>
      | React.CompositionEvent<HTMLSpanElement>,
    index: number
  ) => void;
  onSegmentClick: (segment: TimedSegment) => void;
  onSegmentDoubleClick: (segment: TimedSegment) => void;
  currentTime: number;
  cursorTime: string | null;
  showTimestamps: boolean;
}

const timeStringToSeconds = (timeStr: string): number => {
  const parts = timeStr.split(":").map(Number);
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
};

const secondsToTimeString = (seconds: number): string => {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  return `${hrs.toString().padStart(2, "0")}:${mins
    .toString()
    .padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

interface EditableSegmentProps {
  initialText: string;
  index: number;
  onFinalize: (
    e:
      | React.FocusEvent<HTMLSpanElement>
      | React.CompositionEvent<HTMLSpanElement>,
    index: number
  ) => void;
  onClick: () => void;
  onDoubleClick: () => void;
  style: React.CSSProperties;
}

const EditableSegment: React.FC<EditableSegmentProps> = ({
  initialText,
  index,
  onFinalize,
  onClick,
  onDoubleClick,
  style,
}) => {
  const spanRef = React.useRef<HTMLSpanElement>(null);

  React.useEffect(() => {
    if (spanRef.current) {
      spanRef.current.innerText = initialText;
    }
  }, [initialText]);

  return (
    <span
      ref={spanRef}
      contentEditable
      suppressContentEditableWarning
      style={style}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
        }
      }}
      onBlur={(e) => onFinalize(e, index)}
      onCompositionEnd={(e) => onFinalize(e, index)}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
    />
  );
};

const TranscriptDisplay: React.FC<TranscriptDisplayProps> = ({
  segments,
  isEditMode,
  editedTranscriptSegments,
  onSegmentFinalize,
  onSegmentClick,
  onSegmentDoubleClick,
  currentTime,
  cursorTime,
  showTimestamps,
}) => {
  return (
    <div
      className="p-2 bg-white text-black rounded"
      style={{ lineHeight: "1.8em", maxHeight: "300px", overflowY: "auto" }}
    >
      {(() => {
        const thresholdMinutes = 1;
        let nextThresholdSec = thresholdMinutes * 60;
        return segments.map((segment, index) => {
          const segmentStartSec = timeStringToSeconds(segment.start_time);
          const segmentEndSec = timeStringToSeconds(segment.end_time);
          const isActive =
            currentTime >= segmentStartSec && currentTime < segmentEndSec;
          const markerElements = [];
          if (showTimestamps) {
            while (segmentStartSec >= nextThresholdSec) {
              markerElements.push(
                <span
                  key={`marker-${index}-${nextThresholdSec}`}
                  className="mr-1 text-blue-700"
                >
                  {`{${secondsToTimeString(nextThresholdSec)}}`}
                </span>
              );
              nextThresholdSec += thresholdMinutes * 60;
            }
          }
          const activeColor = isEditMode ? "#32CD32" : "#ffd700";
          const inactiveColor = isEditMode ? "#B0E57C" : "#fff8b3";
          const highlightStyle: React.CSSProperties = {
            backgroundColor:
              isActive || cursorTime === segment.start_time
                ? activeColor
                : inactiveColor,
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
                <EditableSegment
                  index={index}
                  initialText={editedTranscriptSegments[index] ?? segment.text}
                  onFinalize={onSegmentFinalize}
                  onClick={() => onSegmentClick(segment)}
                  onDoubleClick={() => onSegmentDoubleClick(segment)}
                  style={highlightStyle}
                />
              ) : (
                <span
                  style={highlightStyle}
                  onClick={() => onSegmentClick(segment)}
                  onDoubleClick={() => onSegmentDoubleClick(segment)}
                >
                  {segment.text}
                </span>
              )}
            </React.Fragment>
          );
        });
      })()}
    </div>
  );
};

export default TranscriptDisplay;
