/**
 * VoiceButton.jsx — Push-to-talk microphone button
 * Phase 5: Desktop UI Layer
 *
 * Hold to record, release to send.
 * Shows animated pulse ring while recording.
 */

import { useEffect } from "react";
import useVoiceRecorder from "../hooks/useVoiceRecorder";

export default function VoiceButton({
  onAudioReady,
  disabled = false,
  size = "md",
}) {
  const { isRecording, startRecording, stopRecording, audioBlob, error } =
    useVoiceRecorder();

  // When recording stops and blob is ready, forward it up
  useEffect(() => {
    if (audioBlob) onAudioReady?.(audioBlob);
  }, [audioBlob]);

  const sizeClasses =
    {
      sm: "w-10 h-10 text-lg",
      md: "w-14 h-14 text-2xl",
      lg: "w-20 h-20 text-3xl",
    }[size] || "w-14 h-14 text-2xl";

  return (
    <div className="relative flex items-center justify-center">
      {/* Pulse ring while recording */}
      {isRecording && (
        <span
          className="absolute inline-flex rounded-full bg-red-400 opacity-75 animate-ping"
          style={{ width: "calc(100% + 16px)", height: "calc(100% + 16px)" }}
        />
      )}
      <button
        onMouseDown={startRecording}
        onMouseUp={stopRecording}
        onTouchStart={startRecording}
        onTouchEnd={stopRecording}
        disabled={disabled}
        title={isRecording ? "Release to send" : "Hold to record"}
        className={`
          relative rounded-full flex items-center justify-center
          transition-all duration-150 select-none
          ${sizeClasses}
          ${
            isRecording
              ? "bg-red-500 text-white shadow-lg scale-110"
              : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-md"
          }
          ${disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}
        `}
      >
        {isRecording ? "⏹" : "🎤"}
      </button>
      {error && (
        <p className="absolute -bottom-6 text-xs text-red-400 whitespace-nowrap">
          {error}
        </p>
      )}
    </div>
  );
}
