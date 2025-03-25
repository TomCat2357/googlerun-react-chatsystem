// frontend/src/component/Whisper/WhisperUploader.tsx
import React from "react";
import AudioUploader, { AudioInfo } from "../SpeechToText/AudioUploader";

interface WhisperUploaderProps {
  onAudioDataChange: (audioData: string) => void;
  onAudioInfoChange: (audioInfo: AudioInfo | null) => void;
  onDescriptionChange: (description: string) => void;
  onRecordingDateChange: (date: string) => void;
}

const WhisperUploader: React.FC<WhisperUploaderProps> = (props) => {
  // AudioUploaderを再利用
  return (
    <div>
      <p className="mb-4">
        ※アップロードした音声はバッチ処理で文字起こしされます。処理完了後、メールで通知されます。
      </p>
      <AudioUploader {...props} />
    </div>
  );
};

export default WhisperUploader;