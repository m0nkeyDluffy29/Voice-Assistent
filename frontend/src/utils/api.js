/**
 * api.js — All fetch calls to the FastAPI backend
 * Phase 5: Desktop UI Layer
 *
 * Single source of truth for all API communication.
 * Base URL points to the Python FastAPI server on port 8000.
 */

const BASE = "http://127.0.0.1:8000";

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export async function checkHealth() {
  const res = await fetch(`${BASE}/health`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Feed — save memories
// ---------------------------------------------------------------------------

/**
 * Save a typed message to memory.
 * @param {string} text
 * @returns {{ saved, id, language, is_opinion, duplicate }}
 */
export async function feedText(text) {
  const res = await fetch(`${BASE}/feed/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, source: "text" }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

/**
 * Upload an audio blob and save as a voice memory.
 * @param {Blob} audioBlob
 * @returns {{ saved, transcribed, language, is_opinion }}
 */
export async function feedVoice(audioBlob) {
  const form = new FormData();
  form.append("audio", audioBlob, "recording.wav");
  const res = await fetch(`${BASE}/feed/voice`, { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

// ---------------------------------------------------------------------------
// Ask — get answers from memory
// ---------------------------------------------------------------------------

/**
 * Ask a text question, get an answer from your memories.
 * @param {string} query
 * @param {string} language  'english' | 'hindi' | 'hinglish'
 * @param {boolean} speak    Whether to speak the answer via TTS
 * @returns {{ answer, language, context_count, had_context, sources }}
 */
export async function askText(query, language = null, speak = false) {
  const res = await fetch(`${BASE}/ask/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, language, speak_answer: speak }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

/**
 * Upload an audio question, get a spoken answer back.
 * @param {Blob} audioBlob
 * @param {boolean} speak
 * @returns {{ transcribed, answer, language, context_count, sources }}
 */
export async function askVoice(audioBlob, speak = true) {
  const form = new FormData();
  form.append("audio", audioBlob, "question.wav");
  form.append("speak_answer", speak);
  const res = await fetch(`${BASE}/ask/voice`, { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

// ---------------------------------------------------------------------------
// Memories
// ---------------------------------------------------------------------------

export async function getRecentMemories(limit = 20, language = null) {
  const params = new URLSearchParams({ limit });
  if (language) params.append("language", language);
  const res = await fetch(`${BASE}/memories/recent?${params}`);
  return res.json();
}

export async function searchMemories(query, topK = 5) {
  const params = new URLSearchParams({ q: query, top_k: topK });
  const res = await fetch(`${BASE}/memories/search?${params}`);
  return res.json();
}

export async function deleteMemory(id) {
  const res = await fetch(`${BASE}/memories/${id}`, { method: "DELETE" });
  return res.json();
}

// ---------------------------------------------------------------------------
// Beliefs
// ---------------------------------------------------------------------------

export async function getBeliefs(limit = 20) {
  const res = await fetch(`${BASE}/beliefs?limit=${limit}`);
  return res.json();
}

export async function rebuildBeliefs() {
  const res = await fetch(`${BASE}/beliefs/rebuild`, { method: "POST" });
  return res.json();
}

// ---------------------------------------------------------------------------
// Summaries
// ---------------------------------------------------------------------------

export async function runSummarise(days = 7, force = false) {
  const res = await fetch(`${BASE}/summarise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ days, force }),
  });
  return res.json();
}

export async function getSummaries() {
  const res = await fetch(`${BASE}/summaries`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

export async function getStats() {
  const res = await fetch(`${BASE}/stats`);
  return res.json();
}

// ---------------------------------------------------------------------------
// WebSocket — streaming ask
// ---------------------------------------------------------------------------

/**
 * Open a WebSocket connection and stream an answer token by token.
 *
 * @param {string}   query
 * @param {string}   language
 * @param {Function} onToken    Called with each word: (word: string) => void
 * @param {Function} onDone     Called when streaming finishes: ({ context_count }) => void
 * @param {Function} onError    Called on error: (message: string) => void
 * @returns {WebSocket}         The WebSocket instance (call .close() to stop)
 */
export function askStreaming(
  query,
  language = "english",
  onToken,
  onDone,
  onError,
) {
  const ws = new WebSocket(`ws://127.0.0.1:8000/ws/ask`);

  ws.onopen = () => {
    ws.send(JSON.stringify({ query, language }));
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "token") {
      onToken?.(msg.content);
    } else if (msg.type === "done") {
      onDone?.(msg);
      ws.close();
    } else if (msg.type === "error") {
      onError?.(msg.message);
      ws.close();
    }
  };

  ws.onerror = () =>
    onError?.("Connection to agent failed. Is the server running?");
  return ws;
}
