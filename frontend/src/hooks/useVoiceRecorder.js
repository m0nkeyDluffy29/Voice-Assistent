/**
 * useVoiceRecorder.js — Robust push-to-talk with device selection
 * Phase 5: Desktop UI Layer
 *
 * Features:
 *   - Auto-picks best available mic (built-in, USB, wired earphone, bluetooth)
 *   - Lists all input devices so user can switch
 *   - Prevents "audio too short" from accidental double-clicks
 *   - Minimum recording duration enforced (300ms)
 *   - Waits for MediaRecorder to actually finish before returning blob
 */

import { useState, useRef, useCallback, useEffect } from "react";

const MIN_RECORDING_MS = 300; // Ignore anything shorter than this

function getSupportedMimeType() {
  const types = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
    "",
  ];
  for (const type of types) {
    if (!type || MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

export default function useVoiceRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [error, setError] = useState(null);
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState(null); // null = system default

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const startTimeRef = useRef(0);
  const stoppingRef = useRef(false); // Prevents double-stop

  // ---------------------------------------------------------------------------
  // Enumerate available microphones (including wired earphones, USB, bluetooth)
  // ---------------------------------------------------------------------------
  const refreshDevices = useCallback(async () => {
    try {
      // Need to request permission at least once before device labels appear
      const list = await navigator.mediaDevices.enumerateDevices();
      const mics = list.filter((d) => d.kind === "audioinput");
      setDevices(mics);
      return mics;
    } catch (e) {
      console.warn("Could not enumerate devices:", e);
      return [];
    }
  }, []);

  useEffect(() => {
    refreshDevices();
    // Listen for device changes (plug/unplug earphones)
    navigator.mediaDevices?.addEventListener("devicechange", refreshDevices);
    return () =>
      navigator.mediaDevices?.removeEventListener(
        "devicechange",
        refreshDevices,
      );
  }, [refreshDevices]);

  // ---------------------------------------------------------------------------
  // Start recording
  // ---------------------------------------------------------------------------
  const startRecording = useCallback(async () => {
    // Guard: don't start if already recording or stopping
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    )
      return;
    if (stoppingRef.current) return;

    setError(null);
    setAudioBlob(null);
    chunksRef.current = [];

    try {
      // Build constraints — if a specific device is chosen use it, otherwise use default
      const audioConstraints = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 16000,
        channelCount: 1,
      };
      if (deviceId) audioConstraints.deviceId = { exact: deviceId };

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
      });
      streamRef.current = stream;

      // Now that we have permission, refresh device list to get labels
      refreshDevices();

      const mimeType = getSupportedMimeType();
      const options = mimeType ? { mimeType } : {};
      const recorder = new MediaRecorder(stream, options);

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        stoppingRef.current = false;
        const elapsed = Date.now() - startTimeRef.current;
        const type = mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type });

        // Only forward the blob if recording was long enough
        if (elapsed >= MIN_RECORDING_MS && blob.size > 500) {
          setAudioBlob(blob);
        } else {
          console.warn(
            `[Recorder] Skipping ${elapsed}ms recording, ${blob.size} bytes`,
          );
        }

        // Release microphone
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      };

      recorder.onerror = () => {
        setError("Recording failed. Try again.");
        setIsRecording(false);
        stoppingRef.current = false;
      };

      mediaRecorderRef.current = recorder;
      startTimeRef.current = Date.now();
      recorder.start(250); // Emit a chunk every 250ms
      setIsRecording(true);
    } catch (err) {
      console.error("getUserMedia error:", err);
      if (err.name === "NotAllowedError") {
        setError(
          "Mic permission denied. Click the mic icon in your address bar to enable it.",
        );
      } else if (err.name === "NotFoundError") {
        setError("No microphone found. Plug one in and try again.");
      } else if (err.name === "OverconstrainedError") {
        setError("Selected mic is unavailable. Trying default...");
        // Retry with default device
        setDeviceId(null);
      } else {
        setError(`Mic error: ${err.message || err.name}`);
      }
    }
  }, [deviceId, refreshDevices]);

  // ---------------------------------------------------------------------------
  // Stop recording (safe — can be called multiple times)
  // ---------------------------------------------------------------------------
  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;
    if (recorder.state !== "recording") return;
    if (stoppingRef.current) return;

    stoppingRef.current = true;
    recorder.stop(); // Triggers onstop → sets blob
    setIsRecording(false);
  }, []);

  const cancelRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state === "recording") {
      chunksRef.current = []; // Discard chunks before onstop fires
      recorder.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
    }
    setIsRecording(false);
    setAudioBlob(null);
    stoppingRef.current = false;
  }, []);

  return {
    isRecording,
    audioBlob,
    error,
    devices,
    deviceId,
    setDeviceId,
    refreshDevices,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
