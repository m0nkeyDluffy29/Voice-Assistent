/**
 * App.jsx — Full-Screen Particle Globe + Conversational AI
 * Personal AI Agent — Phase 5
 *
 * - Globe fills entire screen using screen diagonal
 * - Click/tap anywhere to record
 * - Waveform when recording, pulsing globe when thinking
 * - Full navbar always visible at top with all features
 * - Conversation bubbles float at bottom
 */

import { useState, useEffect, useRef, useCallback } from "react";
import useVoiceRecorder from "./hooks/useVoiceRecorder";
import {
  checkHealth,
  getStats,
  getBeliefs,
  getRecentMemories,
  searchMemories,
  runSummarise,
  rebuildBeliefs,
} from "./utils/api";

const STATE = {
  IDLE: "idle",
  LISTENING: "listening",
  THINKING: "thinking",
  SPEAKING: "speaking",
};

// ---------------------------------------------------------------------------
// Globe canvas
// ---------------------------------------------------------------------------
function useGlobe(canvasRef, appState) {
  const stateRef = useRef(appState);
  useEffect(() => {
    stateRef.current = appState;
  }, [appState]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const N = 600;
    const t = { v: 0 };

    const P = Array.from({ length: N }, (_, i) => ({
      theta: Math.random() * Math.PI * 2,
      phi: Math.acos(2 * Math.random() - 1),
      rFrac: 0.72 + Math.random() * 0.28,
      speed: 0.001 + Math.random() * 0.0025,
      size: 1.1 + Math.random() * 2.3,
      phase: Math.random() * Math.PI * 2,
      hue: 225 + Math.random() * 75,
      alpha: 0.32 + Math.random() * 0.58,
      col: i % 28,
      row: Math.floor(i / 28),
    }));
    const totalRows = Math.ceil(N / 28);

    function resize() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    let raf;
    function draw() {
      const W = canvas.width;
      const H = canvas.height;
      const cx = W / 2;
      const cy = H / 2;
      const s = stateRef.current;
      const diag = Math.hypot(W, H) / 2;
      t.v += 0.016;
      const tv = t.v;

      ctx.clearRect(0, 0, W, H);

      // Background glow
      const glowHue = {
        [STATE.IDLE]: "250,45%,11%",
        [STATE.LISTENING]: "340,55%,13%",
        [STATE.THINKING]: "200,55%,11%",
        [STATE.SPEAKING]: "270,55%,12%",
      }[s];
      const glowSize =
        diag *
        {
          [STATE.IDLE]: 0.95,
          [STATE.LISTENING]: 1.1,
          [STATE.THINKING]: 0.85,
          [STATE.SPEAKING]: 1.0,
        }[s];
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowSize);
      g.addColorStop(0, `hsla(${glowHue},0.75)`);
      g.addColorStop(0.6, `hsla(${glowHue},0.25)`);
      g.addColorStop(1, "transparent");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);

      const isWave = s === STATE.LISTENING || s === STATE.SPEAKING;
      const spd = {
        [STATE.IDLE]: 1,
        [STATE.LISTENING]: 2.8,
        [STATE.THINKING]: 0.35,
        [STATE.SPEAKING]: 1.7,
      }[s];

      for (let i = 0; i < N; i++) {
        const p = P[i];
        p.theta += p.speed * spd;

        if (isWave) {
          const amp = s === STATE.SPEAKING ? 0.055 : 0.075;
          const freq = s === STATE.SPEAKING ? 2.2 : 3.2;
          const bh =
            H * 0.04 +
            Math.abs(Math.sin(tv * freq + p.col * 0.42 + p.phase)) * H * amp;
          const x =
            cx - W * 0.47 + (p.col / 27) * W * 0.94 + (Math.random() - 0.5) * 4;
          const y = cy + bh - (p.row / totalRows) * bh * 2.3;
          const hue =
            s === STATE.LISTENING
              ? 330 + Math.sin(tv * 1.4 + p.col * 0.35) * 30
              : 265 + Math.sin(tv * 1.1 + p.col * 0.28) * 40;
          ctx.beginPath();
          ctx.arc(x, y, Math.max(0.4, p.size * 1.05), 0, Math.PI * 2);
          ctx.fillStyle = `hsla(${hue},88%,66%,${0.65 + Math.random() * 0.28})`;
          ctx.fill();
        } else {
          const baseR = p.rFrac * diag;
          const pulse =
            s === STATE.THINKING
              ? Math.sin(tv * 2.2 + p.phase) * diag * 0.06
              : Math.sin(tv * 0.5 + p.phase) * diag * 0.022;
          const r = baseR + pulse;
          const sinP = Math.sin(p.phi);
          const cosP = Math.cos(p.phi);
          const px = cx + r * sinP * Math.cos(p.theta);
          const py = cy + r * cosP * (H / W);
          const pz = r * sinP * Math.sin(p.theta);
          const depth = (pz + baseR) / (baseR * 2);
          const sz = p.size * (0.3 + depth * 0.85);
          const al = p.alpha * (0.2 + depth * 0.8);
          const hue =
            p.hue +
            Math.sin(tv * 0.45 + p.phase) * (s === STATE.THINKING ? 65 : 22);

          ctx.beginPath();
          ctx.arc(px, py, Math.max(0.28, sz), 0, Math.PI * 2);
          ctx.fillStyle = `hsla(${hue},${s === STATE.THINKING ? 92 : 70}%,${s === STATE.THINKING ? 72 : 62}%,${al})`;
          ctx.fill();

          // Connection lines
          if (i % 4 === 0) {
            const linkD = diag * 0.038;
            for (let j = i + 1; j < Math.min(i + 9, N); j++) {
              const q = P[j];
              const qbR = q.rFrac * diag;
              const qx = cx + qbR * Math.sin(q.phi) * Math.cos(q.theta);
              const qy = cy + qbR * Math.cos(q.phi) * (H / W);
              const d = Math.hypot(px - qx, py - qy);
              if (d < linkD) {
                ctx.beginPath();
                ctx.moveTo(px, py);
                ctx.lineTo(qx, qy);
                ctx.strokeStyle = `hsla(255,65%,70%,${(1 - d / linkD) * 0.09})`;
                ctx.lineWidth = 0.35;
                ctx.stroke();
              }
            }
          }
        }
      }

      // Center ring
      if (s !== STATE.IDLE) {
        const rCol = {
          [STATE.LISTENING]: "220,75,95",
          [STATE.THINKING]: "70,175,220",
          [STATE.SPEAKING]: "150,95,255",
        }[s];
        const rRad = diag * 0.022 + Math.sin(tv * 3.5) * diag * 0.004;
        ctx.beginPath();
        ctx.arc(cx, cy, rRad, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${rCol},${0.45 + Math.sin(tv * 4) * 0.2})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      raf = requestAnimationFrame(draw);
    }
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);
}

// ---------------------------------------------------------------------------
// Conversation bubble
// ---------------------------------------------------------------------------
function Bubble({ msg }) {
  const isAgent = msg.role === "agent";
  return (
    <div
      style={{
        display: "flex",
        flexDirection: isAgent ? "row" : "row-reverse",
        alignItems: "flex-end",
        gap: 8,
        maxWidth: "72%",
        alignSelf: isAgent ? "flex-start" : "flex-end",
        animation: "fadeUp 0.35s ease",
      }}
    >
      {isAgent && (
        <div
          style={{
            width: 26,
            height: 26,
            borderRadius: "50%",
            background: "rgba(124,111,255,0.2)",
            border: "1px solid rgba(124,111,255,0.35)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            flexShrink: 0,
          }}
        >
          🧠
        </div>
      )}
      <div
        style={{
          background: isAgent
            ? "rgba(124,111,255,0.1)"
            : "rgba(255,255,255,0.06)",
          border: `1px solid ${isAgent ? "rgba(124,111,255,0.22)" : "rgba(255,255,255,0.09)"}`,
          borderRadius: isAgent ? "4px 16px 16px 16px" : "16px 4px 16px 16px",
          padding: "9px 14px",
          fontSize: 13,
          lineHeight: 1.6,
          color: "rgba(222,222,242,0.92)",
          letterSpacing: "0.01em",
        }}
      >
        {msg.text || (msg.streaming ? "" : "...")}
        {msg.streaming && (
          <span
            style={{
              display: "inline-block",
              width: 5,
              height: 12,
              background: "rgba(160,130,255,0.7)",
              marginLeft: 3,
              animation: "blink 0.8s step-end infinite",
              verticalAlign: "middle",
            }}
          />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Side panel
// ---------------------------------------------------------------------------
function SidePanel({ panel, onClose }) {
  const [data, setData] = useState(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!panel) return;
    setData(null);
    setLoading(true);
    const loaders = {
      memories: () => getRecentMemories(25),
      beliefs: () => getBeliefs(20),
      stats: () => getStats(),
    };
    loaders[panel]?.()
      .then(setData)
      .finally(() => setLoading(false));
  }, [panel]);

  if (!panel) return null;

  async function doSearch(e) {
    e.preventDefault();
    if (!search.trim()) return;
    setLoading(true);
    searchMemories(search, 8)
      .then((r) => setData(r))
      .finally(() => setLoading(false));
  }

  return (
    <div
      style={{
        position: "fixed",
        right: 0,
        top: 0,
        bottom: 0,
        width: 300,
        zIndex: 40,
        background: "rgba(5,5,16,0.92)",
        backdropFilter: "blur(28px)",
        borderLeft: "1px solid rgba(255,255,255,0.07)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "18px 18px 14px",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
        }}
      >
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "rgba(180,180,220,0.6)",
          }}
        >
          {panel}
        </span>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "rgba(180,180,220,0.4)",
            fontSize: 18,
            cursor: "pointer",
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </div>

      {panel === "memories" && (
        <form
          onSubmit={doSearch}
          style={{
            display: "flex",
            gap: 6,
            padding: "12px 14px",
            borderBottom: "1px solid rgba(255,255,255,0.05)",
          }}
        >
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search memories..."
            style={{
              flex: 1,
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.1)",
              color: "#e8e8f0",
              fontSize: 12,
              padding: "7px 12px",
              borderRadius: 20,
              outline: "none",
              fontFamily: "inherit",
            }}
          />
          <button
            type="submit"
            style={{
              background: "rgba(124,111,255,0.25)",
              border: "1px solid rgba(124,111,255,0.4)",
              color: "#a78bfa",
              fontSize: 12,
              padding: "7px 12px",
              borderRadius: 20,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            Go
          </button>
        </form>
      )}

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px 14px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {loading && (
          <p
            style={{
              fontSize: 12,
              color: "rgba(180,180,210,0.35)",
              textAlign: "center",
              paddingTop: 20,
            }}
          >
            Loading...
          </p>
        )}

        {/* Memories */}
        {panel === "memories" &&
          !loading &&
          (() => {
            const list = data?.messages || data?.results || [];
            return list.length === 0 ? (
              <p style={{ fontSize: 12, color: "rgba(180,180,210,0.3)" }}>
                No memories yet.
              </p>
            ) : (
              list.map((m, i) => (
                <div
                  key={m.id || i}
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.06)",
                    borderRadius: 10,
                    padding: "10px 12px",
                  }}
                >
                  <div style={{ display: "flex", gap: 4, marginBottom: 5 }}>
                    <span
                      style={{
                        fontSize: 9,
                        letterSpacing: "0.07em",
                        textTransform: "uppercase",
                        padding: "2px 6px",
                        borderRadius: 8,
                        background: "rgba(124,111,255,0.14)",
                        color: "rgba(167,139,250,0.85)",
                        border: "1px solid rgba(124,111,255,0.18)",
                      }}
                    >
                      {{ english: "EN", hindi: "HI", hinglish: "HI+EN" }[
                        m.language || m.metadata?.language
                      ] || "?"}
                    </span>
                    {(m.is_opinion || m.metadata?.is_opinion) && (
                      <span
                        style={{
                          fontSize: 9,
                          padding: "2px 6px",
                          borderRadius: 8,
                          background: "rgba(160,90,220,0.12)",
                          color: "rgba(190,140,240,0.85)",
                          border: "1px solid rgba(160,90,220,0.2)",
                        }}
                      >
                        belief
                      </span>
                    )}
                    {m.relevance_score && (
                      <span
                        style={{
                          fontSize: 9,
                          marginLeft: "auto",
                          color: "rgba(140,180,255,0.6)",
                        }}
                      >
                        {Math.round(m.relevance_score * 100)}%
                      </span>
                    )}
                  </div>
                  <p
                    style={{
                      fontSize: 12,
                      color: "rgba(200,200,220,0.75)",
                      lineHeight: 1.5,
                      display: "-webkit-box",
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {m.text}
                  </p>
                  <p
                    style={{
                      fontSize: 10,
                      color: "rgba(140,140,180,0.3)",
                      marginTop: 5,
                    }}
                  >
                    {(m.timestamp || m.metadata?.timestamp || "").slice(0, 10)}
                  </p>
                </div>
              ))
            );
          })()}

        {/* Beliefs */}
        {panel === "beliefs" &&
          !loading &&
          (() => {
            const list = data?.beliefs || [];
            return list.length === 0 ? (
              <p style={{ fontSize: 12, color: "rgba(180,180,210,0.3)" }}>
                No beliefs indexed yet. Use the rebuild button.
              </p>
            ) : (
              list.map((b, i) => (
                <div
                  key={b.id || i}
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.06)",
                    borderRadius: 10,
                    padding: "10px 12px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginBottom: 5,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 10,
                        color: "rgba(167,139,250,0.8)",
                        fontWeight: 600,
                        textTransform: "capitalize",
                      }}
                    >
                      {b.topic}
                    </span>
                    <span
                      style={{ fontSize: 10, color: "rgba(140,140,180,0.4)" }}
                    >
                      {Math.round(b.confidence * 100)}% conf
                    </span>
                  </div>
                  <p
                    style={{
                      fontSize: 12,
                      color: "rgba(200,200,220,0.75)",
                      lineHeight: 1.5,
                    }}
                  >
                    {b.belief_text}
                  </p>
                  <p
                    style={{
                      fontSize: 10,
                      color: "rgba(140,140,180,0.3)",
                      marginTop: 4,
                    }}
                  >
                    mentioned {b.mention_count}×
                  </p>
                </div>
              ))
            );
          })()}

        {/* Stats */}
        {panel === "stats" &&
          !loading &&
          data &&
          (() => {
            const s = data.sqlite || {};
            const c = data.chroma || {};
            const cards = [
              ["Messages", s.total_messages],
              ["Opinions", s.total_opinions],
              ["Sessions", s.total_sessions],
              ["Beliefs", data.beliefs],
              ["Vectors", c.total_memories_embedded],
              ["Summaries", c.total_summaries],
            ];
            return (
              <>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 8,
                  }}
                >
                  {cards.map(([label, val]) => (
                    <div
                      key={label}
                      style={{
                        background: "rgba(255,255,255,0.04)",
                        border: "1px solid rgba(255,255,255,0.07)",
                        borderRadius: 10,
                        padding: "12px 14px",
                      }}
                    >
                      <p
                        style={{
                          fontSize: 10,
                          color: "rgba(160,160,200,0.5)",
                          marginBottom: 4,
                          textTransform: "uppercase",
                          letterSpacing: "0.06em",
                        }}
                      >
                        {label}
                      </p>
                      <p
                        style={{
                          fontSize: 22,
                          fontWeight: 600,
                          color: "rgba(210,210,240,0.9)",
                        }}
                      >
                        {val ?? "—"}
                      </p>
                    </div>
                  ))}
                </div>
                {s.by_language && (
                  <div
                    style={{
                      background: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,255,255,0.06)",
                      borderRadius: 10,
                      padding: "12px 14px",
                      marginTop: 4,
                    }}
                  >
                    <p
                      style={{
                        fontSize: 10,
                        color: "rgba(160,160,200,0.4)",
                        marginBottom: 8,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                      }}
                    >
                      Languages
                    </p>
                    {Object.entries(s.by_language).map(([lang, count]) => (
                      <div
                        key={lang}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          fontSize: 12,
                          marginBottom: 4,
                        }}
                      >
                        <span
                          style={{
                            color: "rgba(180,180,220,0.6)",
                            textTransform: "capitalize",
                          }}
                        >
                          {lang}
                        </span>
                        <span style={{ color: "rgba(200,200,240,0.85)" }}>
                          {count}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            );
          })()}
      </div>

      {/* Action buttons */}
      {panel === "beliefs" && (
        <div
          style={{
            padding: "12px 14px",
            borderTop: "1px solid rgba(255,255,255,0.07)",
          }}
        >
          <button
            onClick={() => {
              setLoading(true);
              rebuildBeliefs()
                .then(setData)
                .finally(() => setLoading(false));
            }}
            style={{
              width: "100%",
              background: "rgba(124,111,255,0.2)",
              border: "1px solid rgba(124,111,255,0.4)",
              color: "#a78bfa",
              fontSize: 12,
              padding: "9px",
              borderRadius: 10,
              cursor: "pointer",
              fontFamily: "inherit",
              letterSpacing: "0.04em",
            }}
          >
            Rebuild Belief Index
          </button>
        </div>
      )}
      {panel === "stats" && (
        <div
          style={{
            padding: "12px 14px",
            borderTop: "1px solid rgba(255,255,255,0.07)",
          }}
        >
          <button
            onClick={() => {
              setLoading(true);
              runSummarise(7, false)
                .then(() => getStats().then(setData))
                .finally(() => setLoading(false));
            }}
            style={{
              width: "100%",
              background: "rgba(80,160,120,0.15)",
              border: "1px solid rgba(80,200,140,0.3)",
              color: "rgba(120,220,160,0.85)",
              fontSize: 12,
              padding: "9px",
              borderRadius: 10,
              cursor: "pointer",
              fontFamily: "inherit",
              letterSpacing: "0.04em",
            }}
          >
            Generate Weekly Summary
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------
const STATE_COLOR = {
  [STATE.IDLE]: "#7c6fff",
  [STATE.LISTENING]: "#e05070",
  [STATE.THINKING]: "#40b0e0",
  [STATE.SPEAKING]: "#b060ff",
};
const STATE_HINT = {
  [STATE.IDLE]: "tap anywhere · or start convo",
  [STATE.LISTENING]: "listening...",
  [STATE.THINKING]: "thinking...",
  [STATE.SPEAKING]: "speaking...",
};

export default function App() {
  const canvasRef = useRef(null);
  const convRef = useRef(null);
  const appStateRef = useRef(STATE.IDLE);

  const [appState, setAppStateS] = useState(STATE.IDLE);
  const [messages, setMessages] = useState([]);
  const [mode, setMode] = useState("ask");
  const [panel, setPanel] = useState(null);
  const [serverOk, setServerOk] = useState(null);
  const [langPref, setLangPref] = useState("english");
  const [agentName, setAgentName] = useState(
    () => localStorage.getItem("agentName") || "Flux",
  );
  const [showNameSetup, setShowNameSetup] = useState(
    !localStorage.getItem("agentName"),
  );
  const [conversationActive, setConvActive] = useState(false);
  const conversationActiveRef = useRef(false);
  const silenceTimerRef = useRef(null);
  const speechDetectedRef = useRef(false);
  const audioAnalyserRef = useRef(null);
  const analyserRafRef = useRef(null);

  function setAppState(s) {
    setAppStateS(s);
    appStateRef.current = s;
  }

  // Persist agent name
  useEffect(() => {
    if (agentName) localStorage.setItem("agentName", agentName);
  }, [agentName]);

  // Voice recorder (destructured early so toggleConversation can use it)
  const {
    isRecording,
    startRecording,
    stopRecording,
    audioBlob,
    error: micError,
    devices,
    deviceId,
    setDeviceId,
  } = useVoiceRecorder();

  // Toggle continuous conversation mode
  async function toggleConversation() {
    const willActivate = !conversationActive;
    setConvActive(willActivate);
    conversationActiveRef.current = willActivate;

    if (willActivate) {
      // Fetch a personalised greeting and speak it
      try {
        const res = await fetch(
          `http://127.0.0.1:8000/converse/greeting?name=${encodeURIComponent(agentName)}&language=${langPref}`,
        );
        const data = await res.json();
        setAppState(STATE.SPEAKING);
        speakBrowser(data.greeting, langPref);
        // After greeting finishes, speakBrowser onend auto-starts recording
      } catch (e) {
        // Fallback: just start listening
        if (!isRecording && appState === STATE.IDLE) startRecording();
      }
    } else {
      if (isRecording) stopRecording();
      window.speechSynthesis?.cancel();
      setAppState(STATE.IDLE);
    }
  }

  // Auto-stop after silence (Voice Activity Detection)
  useEffect(() => {
    if (!isRecording || !conversationActiveRef.current) return;

    // Set up audio analyser to detect silence
    let stream = null;
    let analyser = null;
    let audioCtx = null;
    let raf = null;

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const src = audioCtx.createMediaStreamSource(stream);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 512;
        src.connect(analyser);
        audioAnalyserRef.current = analyser;

        const data = new Uint8Array(analyser.frequencyBinCount);
        let silenceStart = null;
        const SILENCE_THRESHOLD = 12; // Volume level below = silence
        const SILENCE_DURATION = 1200; // 1.2s of silence = end of sentence

        function checkVolume() {
          if (!conversationActiveRef.current || !isRecording) return;
          analyser.getByteFrequencyData(data);
          const avg = data.reduce((a, b) => a + b, 0) / data.length;

          if (avg > SILENCE_THRESHOLD) {
            // Speech detected
            speechDetectedRef.current = true;
            silenceStart = null;
          } else if (speechDetectedRef.current) {
            // Was speaking, now silent
            if (silenceStart === null) silenceStart = Date.now();
            else if (Date.now() - silenceStart > SILENCE_DURATION) {
              // 1.2s of silence after speech → user finished sentence
              stopRecording();
              return;
            }
          }
          raf = requestAnimationFrame(checkVolume);
        }
        checkVolume();
      } catch (e) {
        console.warn("VAD setup failed:", e);
      }
    })();

    return () => {
      if (raf) cancelAnimationFrame(raf);
      if (audioCtx) audioCtx.close();
      if (stream) stream.getTracks().forEach((t) => t.stop());
      speechDetectedRef.current = false;
    };
  }, [isRecording]);

  useGlobe(canvasRef, appState);

  useEffect(() => {
    checkHealth()
      .then(() => setServerOk(true))
      .catch(() => setServerOk(false));
  }, []);

  useEffect(() => {
    if (convRef.current)
      convRef.current.scrollTop = convRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (isRecording) setAppState(STATE.LISTENING);
  }, [isRecording]);

  useEffect(() => {
    if (!audioBlob) return;
    handleVoiceBlob(audioBlob);
  }, [audioBlob]);

  // Server-side TTS — bypasses Brave/Chrome speech blocking
  // Fetches audio bytes from /tts endpoint and plays via <audio> element
  const audioElRef = useRef(null);

  async function speakBrowser(text, language) {
    console.log(`[TTS] Speaking: "${text}" in ${language}`);
    if (!text || !text.trim()) return;

    // Stop any currently playing audio
    if (audioElRef.current) {
      audioElRef.current.pause();
      audioElRef.current = null;
    }

    setAppState(STATE.SPEAKING);

    try {
      // Request WAV bytes from server
      const res = await fetch("http://127.0.0.1:8000/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language }),
      });

      if (!res.ok) {
        console.error("[TTS] Server error:", res.status);
        setAppState(STATE.IDLE);
        return;
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioElRef.current = audio;

      audio.onplay = () => {
        console.log("[TTS] Audio started");
      };

      audio.onended = () => {
        console.log("[TTS] Audio finished");
        URL.revokeObjectURL(url);
        audioElRef.current = null;
        if (mode === "ask" && conversationActiveRef.current) {
          setAppState(STATE.IDLE);
          setTimeout(() => {
            if (conversationActiveRef.current && !isRecording) startRecording();
          }, 400);
        } else {
          setAppState(STATE.IDLE);
        }
      };

      audio.onerror = (e) => {
        console.error("[TTS] Audio playback error:", e);
        URL.revokeObjectURL(url);
        setAppState(STATE.IDLE);
      };

      // Play — this works even with Brave fingerprint protection
      await audio.play();
    } catch (err) {
      console.error("[TTS] Fetch error:", err);
      setAppState(STATE.IDLE);
    }
  }

  async function handleVoiceBlob(blob) {
    setAppState(STATE.THINKING);
    try {
      const form = new FormData();
      form.append("audio", blob, "recording.webm");
      const langHint = langPref !== "hinglish" ? langPref : null;

      // ── JARVIS-style single endpoint call ──────────────────────────────
      // /converse does: transcribe + save + retrieve + answer in one round trip
      // Frontend then speaks the answer via browser TTS (instant, no server TTS lag)
      const url =
        mode === "ask"
          ? langHint
            ? `http://127.0.0.1:8000/converse?language_hint=${langHint}`
            : `http://127.0.0.1:8000/converse`
          : langHint
            ? `http://127.0.0.1:8000/feed/voice?language_hint=${langHint}`
            : `http://127.0.0.1:8000/feed/voice`;

      const res = await fetch(url, { method: "POST", body: form });
      const result = await res.json();

      if (!result.transcribed) {
        addMsg({
          role: "agent",
          text: result.error || result.answer || "Couldn't hear that.",
        });
        setAppState(STATE.IDLE);
        // Retry listen if in conversation mode
        if (mode === "ask" && conversationActiveRef.current) {
          setTimeout(() => {
            if (conversationActiveRef.current) startRecording();
          }, 800);
        }
        return;
      }

      // Show user's transcription
      addMsg({ role: "user", text: result.transcribed });

      if (mode === "feed") {
        const feedReply = result.saved
          ? "Got it, saved that."
          : "Already saved this earlier.";
        addMsg({ role: "agent", text: feedReply });
        // ALWAYS speak, even in feed mode
        speakBrowser(feedReply, result.language || langPref);
        return;
      }

      // Ask mode — show answer immediately + speak it
      addMsg({
        role: "agent",
        text: result.answer,
        context_count: result.context_count,
      });
      speakBrowser(result.answer, result.language || langPref);
    } catch (err) {
      console.error(err);
      setAppState(STATE.IDLE);
      addMsg({ role: "agent", text: "Something went wrong. Try again." });
    }
  }

  function addMsg(msg) {
    setMessages((prev) => [...prev, { ...msg, ts: new Date() }]);
  }

  // Toggle recording — click to start, click again to stop
  // Uses a lock so double-clicks or handler-overlaps don't create rapid start/stop cycles
  const toggleLockRef = useRef(false);
  function handleCanvasInteract() {
    if (appState === STATE.THINKING || appState === STATE.SPEAKING) return;
    if (toggleLockRef.current) return;
    toggleLockRef.current = true;
    setTimeout(() => {
      toggleLockRef.current = false;
    }, 400); // Debounce 400ms
    if (isRecording) stopRecording();
    else startRecording();
  }

  const sc = STATE_COLOR[appState];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#050510",
        fontFamily: "'Inter',system-ui,sans-serif",
        overflow: "hidden",
      }}
    >
      {/* Full-screen canvas */}
      <canvas
        ref={canvasRef}
        onClick={handleCanvasInteract}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 0,
          cursor:
            appState === STATE.THINKING || appState === STATE.SPEAKING
              ? "wait"
              : "pointer",
        }}
      />

      {/* ── NAVBAR — always visible ─────────────────────────────────────── */}
      <nav
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: panel ? 300 : 0,
          zIndex: 30,
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "13px 24px",
          background: "rgba(5,5,16,0.72)",
          backdropFilter: "blur(22px)",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          transition: "right 0.35s ease",
          flexWrap: "wrap",
        }}
      >
        {/* Logo + status */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginRight: 6,
          }}
        >
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: sc,
              boxShadow: `0 0 10px ${sc}`,
              transition: "all 0.5s",
            }}
          />
          <span
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: "rgba(205,205,235,0.9)",
              letterSpacing: "0.01em",
            }}
          >
            Personal AI
          </span>
          <span
            style={{
              fontSize: 10,
              color: serverOk ? "rgba(90,210,120,0.7)" : "rgba(210,90,90,0.7)",
              letterSpacing: "0.05em",
              textTransform: "uppercase",
              border: `1px solid ${serverOk ? "rgba(90,210,120,0.25)" : "rgba(210,90,90,0.25)"}`,
              padding: "2px 7px",
              borderRadius: 8,
            }}
          >
            {serverOk === null ? "…" : serverOk ? "online" : "offline"}
          </span>
        </div>

        {/* Mode */}
        <div style={{ display: "flex", gap: 4, marginRight: 4 }}>
          {["ask", "feed"].map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                setMessages([]);
                if (conversationActive) toggleConversation();
              }}
              style={{
                background:
                  mode === m
                    ? "rgba(124,111,255,0.22)"
                    : "rgba(255,255,255,0.05)",
                border: `1px solid ${mode === m ? "rgba(124,111,255,0.48)" : "rgba(255,255,255,0.09)"}`,
                color: mode === m ? "#a78bfa" : "rgba(180,180,215,0.55)",
                fontSize: 11,
                padding: "5px 13px",
                borderRadius: 18,
                cursor: "pointer",
                fontFamily: "inherit",
                letterSpacing: "0.04em",
                textTransform: "capitalize",
                transition: "all 0.2s",
              }}
            >
              {m === "ask" ? "💬 ask" : "📝 feed"}
            </button>
          ))}
        </div>

        {/* JARVIS-style continuous conversation toggle — only in ask mode */}
        {mode === "ask" && (
          <button
            onClick={toggleConversation}
            style={{
              background: conversationActive
                ? "rgba(220,80,120,0.22)"
                : "rgba(255,255,255,0.05)",
              border: `1px solid ${conversationActive ? "rgba(220,80,120,0.5)" : "rgba(255,255,255,0.09)"}`,
              color: conversationActive ? "#f472b6" : "rgba(180,180,215,0.55)",
              fontSize: 11,
              padding: "5px 13px",
              borderRadius: 18,
              cursor: "pointer",
              fontFamily: "inherit",
              letterSpacing: "0.04em",
              transition: "all 0.2s",
              display: "flex",
              alignItems: "center",
              gap: 5,
            }}
          >
            {conversationActive ? (
              <>
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: "#f472b6",
                    animation: "pulseDot 1s ease-in-out infinite",
                  }}
                />{" "}
                live
              </>
            ) : (
              "🎙 start convo"
            )}
          </button>
        )}

        {/* Agent name button */}
        <button
          onClick={() => setShowNameSetup(true)}
          title="Change agent name"
          style={{
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)",
            color: "rgba(180,180,215,0.7)",
            fontSize: 11,
            padding: "5px 13px",
            borderRadius: 18,
            cursor: "pointer",
            fontFamily: "inherit",
            letterSpacing: "0.04em",
          }}
        >
          🤖 {agentName}
        </button>

        {/* Language */}
        <select
          value={langPref}
          onChange={(e) => setLangPref(e.target.value)}
          style={{
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)",
            color: "rgba(180,180,215,0.7)",
            fontSize: 11,
            padding: "5px 10px",
            borderRadius: 18,
            cursor: "pointer",
            fontFamily: "inherit",
            outline: "none",
          }}
        >
          <option value="english">English</option>
          <option value="hindi">Hindi</option>
          <option value="hinglish">Hinglish</option>
        </select>

        {/* Microphone selector — includes wired earphones, USB mics, bluetooth */}
        {devices.length > 0 && (
          <select
            value={deviceId || ""}
            onChange={(e) => setDeviceId(e.target.value || null)}
            title="Choose microphone"
            style={{
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              color: "rgba(180,180,215,0.7)",
              fontSize: 11,
              padding: "5px 10px",
              borderRadius: 18,
              cursor: "pointer",
              fontFamily: "inherit",
              outline: "none",
              maxWidth: 180,
              textOverflow: "ellipsis",
            }}
          >
            <option value="">🎙 System default</option>
            {devices.map((d) => (
              <option key={d.deviceId} value={d.deviceId}>
                🎙 {d.label || `Mic ${d.deviceId.slice(0, 6)}`}
              </option>
            ))}
          </select>
        )}

        {/* Panel buttons */}
        {["memories", "beliefs", "stats"].map((p) => (
          <button
            key={p}
            onClick={() => setPanel(panel === p ? null : p)}
            style={{
              background:
                panel === p
                  ? "rgba(124,111,255,0.18)"
                  : "rgba(255,255,255,0.04)",
              border: `1px solid ${panel === p ? "rgba(124,111,255,0.4)" : "rgba(255,255,255,0.08)"}`,
              color: panel === p ? "#a78bfa" : "rgba(170,170,210,0.5)",
              fontSize: 11,
              padding: "5px 13px",
              borderRadius: 18,
              cursor: "pointer",
              fontFamily: "inherit",
              letterSpacing: "0.04em",
              textTransform: "capitalize",
              transition: "all 0.2s",
            }}
          >
            {p}
          </button>
        ))}

        {/* Clear conversation */}
        {messages.length > 0 && (
          <button
            onClick={() => setMessages([])}
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "rgba(160,160,200,0.45)",
              fontSize: 11,
              padding: "5px 13px",
              borderRadius: 18,
              cursor: "pointer",
              fontFamily: "inherit",
              marginLeft: "auto",
            }}
          >
            clear
          </button>
        )}

        {/* State label */}
        <span
          style={{
            fontSize: 10,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: `${sc}99`,
            marginLeft: messages.length > 0 ? 0 : "auto",
            transition: "color 0.5s",
          }}
        >
          {STATE_HINT[appState]}
        </span>
      </nav>

      {/* Center hint dot */}
      <div
        style={{
          position: "fixed",
          top: "50%",
          left: panel ? `calc(50% - 150px)` : "50%",
          transform: "translate(-50%,-50%)",
          zIndex: 5,
          pointerEvents: "none",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 14,
          transition: "left 0.35s ease",
        }}
      >
        <div
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: sc,
            boxShadow: `0 0 18px ${sc}, 0 0 36px ${sc}55`,
            transition: "all 0.6s",
            animation:
              appState !== STATE.IDLE
                ? "pulseDot 1.2s ease-in-out infinite"
                : "none",
          }}
        />
        <span
          style={{
            fontSize: 11,
            color: "rgba(170,170,210,0.38)",
            letterSpacing: "0.14em",
            textTransform: "uppercase",
          }}
        >
          {micError ||
            (appState === STATE.IDLE
              ? mode === "ask"
                ? "conversation mode"
                : "feed mode"
              : "")}
        </span>
      </div>

      {/* Conversation — hidden during live conversation for full voice-only experience */}
      {messages.length > 0 && !conversationActive && (
        <div
          style={{
            position: "fixed",
            bottom: 0,
            left: 0,
            right: panel ? 300 : 0,
            zIndex: 10,
            display: "flex",
            flexDirection: "column",
            pointerEvents: "none",
            transition: "right 0.35s ease",
          }}
        >
          <div
            style={{
              height: 60,
              background:
                "linear-gradient(to bottom,transparent,rgba(5,5,16,0.55))",
              pointerEvents: "none",
            }}
          />
          <div
            ref={convRef}
            style={{
              maxHeight: "30vh",
              overflowY: "auto",
              padding: "0 22px 20px",
              display: "flex",
              flexDirection: "column",
              gap: 9,
              background: "rgba(5,5,16,0.65)",
              backdropFilter: "blur(16px)",
              borderTop: "1px solid rgba(255,255,255,0.05)",
              pointerEvents: "all",
            }}
          >
            {messages.map((m, i) => (
              <Bubble key={m.id || i} msg={m} />
            ))}
          </div>
        </div>
      )}

      {/* During conversation — show a subtle live caption of what the agent last said */}
      {conversationActive && messages.length > 0 && (
        <div
          style={{
            position: "fixed",
            bottom: 40,
            left: 0,
            right: 0,
            zIndex: 10,
            display: "flex",
            justifyContent: "center",
            padding: "0 32px",
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              maxWidth: 600,
              textAlign: "center",
              background: "rgba(5,5,16,0.35)",
              backdropFilter: "blur(10px)",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 16,
              padding: "14px 22px",
            }}
          >
            <p
              style={{
                fontSize: 10,
                color: "rgba(160,160,200,0.4)",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                marginBottom: 6,
              }}
            >
              {messages[messages.length - 1].role === "user"
                ? "you said"
                : agentName}
            </p>
            <p
              style={{
                fontSize: 15,
                color: "rgba(220,220,240,0.85)",
                lineHeight: 1.5,
                fontWeight: 400,
              }}
            >
              {messages[messages.length - 1].text}
            </p>
          </div>
        </div>
      )}

      {/* Name setup modal — shown on first launch or when agent name button clicked */}
      {showNameSetup && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 50,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0,0,0,0.6)",
            backdropFilter: "blur(8px)",
          }}
        >
          <div
            style={{
              background: "rgba(15,15,30,0.95)",
              border: "1px solid rgba(124,111,255,0.3)",
              borderRadius: 20,
              padding: "32px 36px",
              width: 400,
              textAlign: "center",
            }}
          >
            <h2
              style={{
                fontSize: 24,
                fontWeight: 700,
                marginBottom: 8,
                background: "linear-gradient(135deg,#e8e8f8,#a78bfa,#7c6fff)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              Name your agent
            </h2>
            <p
              style={{
                fontSize: 13,
                color: "rgba(180,180,220,0.55)",
                marginBottom: 20,
                lineHeight: 1.6,
              }}
            >
              This is what your digital self will be called. It will introduce
              itself when you start a conversation.
            </p>
            <input
              type="text"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              placeholder="Flux, Nova, Echo..."
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && agentName.trim())
                  setShowNameSetup(false);
              }}
              style={{
                width: "100%",
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.12)",
                color: "#e8e8f0",
                fontSize: 15,
                padding: "12px 16px",
                borderRadius: 12,
                outline: "none",
                fontFamily: "inherit",
                marginBottom: 20,
                letterSpacing: "0.02em",
                textAlign: "center",
              }}
            />
            <button
              onClick={() => {
                if (agentName.trim()) setShowNameSetup(false);
              }}
              disabled={!agentName.trim()}
              style={{
                width: "100%",
                background: agentName.trim()
                  ? "rgba(124,111,255,0.25)"
                  : "rgba(255,255,255,0.05)",
                border: `1px solid ${agentName.trim() ? "rgba(124,111,255,0.5)" : "rgba(255,255,255,0.1)"}`,
                color: agentName.trim() ? "#a78bfa" : "rgba(180,180,220,0.3)",
                fontSize: 14,
                padding: "10px",
                borderRadius: 12,
                cursor: agentName.trim() ? "pointer" : "not-allowed",
                fontFamily: "inherit",
                fontWeight: 500,
              }}
            >
              Set name & continue
            </button>
          </div>
        </div>
      )}

      {/* Side panel */}
      <SidePanel panel={panel} onClose={() => setPanel(null)} />

      <style>{`
        @keyframes fadeUp { from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)} }
        @keyframes blink  { 0%,100%{opacity:1}50%{opacity:0} }
        @keyframes pulseDot { 0%,100%{transform:scale(1)}50%{transform:scale(1.5)} }
        input::placeholder,textarea::placeholder{color:rgba(170,170,210,0.28)}
        ::-webkit-scrollbar{width:3px}
        ::-webkit-scrollbar-thumb{background:rgba(124,111,255,0.18);border-radius:2px}
        *{box-sizing:border-box;margin:0;padding:0}
        select option{background:#0d0d20;color:#e0e0f0}
      `}</style>
    </div>
  );
}