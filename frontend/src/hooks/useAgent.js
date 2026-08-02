/**
 * useAgent.js — Central state and logic hook for the agent
 * Phase 5: Desktop UI Layer
 *
 * Manages:
 *   - Feed mode (saving thoughts)
 *   - Ask mode (getting answers via WebSocket streaming)
 *   - Voice recording for both modes
 *   - Stats, beliefs, memories panel data
 */

import { useState, useCallback, useRef } from "react";
import {
  feedText,
  feedVoice,
  askText,
  askStreaming,
  getRecentMemories,
  searchMemories,
  getBeliefs,
  getStats,
} from "../utils/api";

export default function useAgent() {
  // ── Mode ──────────────────────────────────────────────────────────────────
  const [mode, setMode] = useState("feed"); // 'feed' | 'ask'

  // ── Feed state ────────────────────────────────────────────────────────────
  const [feedInput, setFeedInput] = useState("");
  const [feedMessages, setFeedMessages] = useState([]); // list of saved messages shown in UI
  const [feedLoading, setFeedLoading] = useState(false);

  // ── Ask state ─────────────────────────────────────────────────────────────
  const [askInput, setAskInput] = useState("");
  const [askMessages, setAskMessages] = useState([]); // conversation history
  const [askLoading, setAskLoading] = useState(false);
  const [streamText, setStreamText] = useState(""); // partial streamed answer
  const wsRef = useRef(null);

  // ── Shared state ──────────────────────────────────────────────────────────
  const [stats, setStats] = useState(null);
  const [beliefs, setBeliefs] = useState([]);
  const [memories, setMemories] = useState([]);
  const [error, setError] = useState(null);
  const [voiceOutput, setVoiceOutput] = useState(true);

  // ---------------------------------------------------------------------------
  // Feed actions
  // ---------------------------------------------------------------------------

  const submitFeedText = useCallback(async (text) => {
    if (!text.trim()) return;
    setFeedLoading(true);
    setError(null);
    try {
      const result = await feedText(text);
      const msg = {
        id: result.id,
        text,
        language: result.language,
        is_opinion: result.is_opinion,
        saved: result.saved,
        timestamp: new Date().toISOString(),
        type: "feed",
      };
      setFeedMessages((prev) => [msg, ...prev]);
      setFeedInput("");
      return result;
    } catch (err) {
      setError(err.message);
    } finally {
      setFeedLoading(false);
    }
  }, []);

  const submitFeedVoice = useCallback(async (audioBlob) => {
    if (!audioBlob) return;
    setFeedLoading(true);
    setError(null);
    try {
      const result = await feedVoice(audioBlob);
      if (result.saved) {
        const msg = {
          id: result.id,
          text: result.transcribed,
          language: result.language,
          is_opinion: result.is_opinion,
          saved: true,
          timestamp: new Date().toISOString(),
          type: "feed-voice",
        };
        setFeedMessages((prev) => [msg, ...prev]);
      }
      return result;
    } catch (err) {
      setError(err.message);
    } finally {
      setFeedLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Ask actions — streaming via WebSocket
  // ---------------------------------------------------------------------------

  const submitAsk = useCallback(async (query, language = "english") => {
    if (!query.trim()) return;
    setAskLoading(true);
    setError(null);
    setStreamText("");

    // Add user message immediately
    const userMsg = {
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
    };
    setAskMessages((prev) => [...prev, userMsg]);
    setAskInput("");

    // Placeholder for streaming answer
    const agentMsgId = Date.now();
    setAskMessages((prev) => [
      ...prev,
      {
        role: "agent",
        content: "",
        id: agentMsgId,
        streaming: true,
        context_count: 0,
      },
    ]);

    let accumulated = "";

    wsRef.current = askStreaming(
      query,
      language,
      // onToken
      (word) => {
        accumulated += word;
        setAskMessages((prev) =>
          prev.map((m) =>
            m.id === agentMsgId ? { ...m, content: accumulated } : m,
          ),
        );
      },
      // onDone
      ({ context_count, had_context }) => {
        setAskMessages((prev) =>
          prev.map((m) =>
            m.id === agentMsgId
              ? {
                  ...m,
                  streaming: false,
                  content: accumulated,
                  context_count,
                  had_context,
                }
              : m,
          ),
        );
        setAskLoading(false);
        setStreamText("");
      },
      // onError
      (message) => {
        setError(message);
        setAskMessages((prev) =>
          prev.map((m) =>
            m.id === agentMsgId
              ? { ...m, streaming: false, content: "Error: " + message }
              : m,
          ),
        );
        setAskLoading(false);
      },
    );
  }, []);

  const clearAskHistory = useCallback(() => {
    if (wsRef.current) wsRef.current.close();
    setAskMessages([]);
    setStreamText("");
  }, []);

  // ---------------------------------------------------------------------------
  // Data loaders
  // ---------------------------------------------------------------------------

  const loadStats = useCallback(async () => {
    try {
      const data = await getStats();
      setStats(data);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const loadBeliefs = useCallback(async () => {
    try {
      const data = await getBeliefs(20);
      setBeliefs(data.beliefs || []);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const loadMemories = useCallback(async (limit = 20) => {
    try {
      const data = await getRecentMemories(limit);
      setMemories(data.messages || []);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const searchMemory = useCallback(async (query) => {
    try {
      const data = await searchMemories(query, 8);
      return data.results || [];
    } catch (err) {
      setError(err.message);
      return [];
    }
  }, []);

  return {
    // Mode
    mode,
    setMode,
    // Feed
    feedInput,
    setFeedInput,
    feedMessages,
    feedLoading,
    submitFeedText,
    submitFeedVoice,
    // Ask
    askInput,
    setAskInput,
    askMessages,
    askLoading,
    streamText,
    submitAsk,
    clearAskHistory,
    // Shared
    stats,
    beliefs,
    memories,
    loadStats,
    loadBeliefs,
    loadMemories,
    searchMemory,
    voiceOutput,
    setVoiceOutput,
    error,
    setError,
  };
}
