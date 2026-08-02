/**
 * App.jsx — Particle Globe UI
 * Personal AI Agent — Phase 5 redesign
 *
 * Full-screen particle canvas with:
 *   - Globe formation at idle
 *   - Sound wave formation when recording
 *   - All nav options in top navbar
 *   - Floating center UI (title, record button, input)
 *   - Slide-in memory panel from right
 */

import { useState, useEffect, useRef, useCallback } from "react";
import useAgent from "./hooks/useAgent";
import useVoiceRecorder from "./hooks/useVoiceRecorder";
import { checkHealth } from "./utils/api";

// ---------------------------------------------------------------------------
// Particle canvas hook
// ---------------------------------------------------------------------------
function useParticleGlobe(canvasRef, recording) {
  const animRef = useRef(null);
  const particlesRef = useRef([]);
  const tRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const COUNT = 280;

    function resize() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    const particles = [];
    for (let i = 0; i < COUNT; i++) {
      particles.push({
        theta: Math.random() * Math.PI * 2,
        phi: Math.acos(2 * Math.random() - 1),
        baseR: 160 + Math.random() * 30,
        speed: 0.002 + Math.random() * 0.003,
        size: 1.2 + Math.random() * 1.8,
        phase: Math.random() * Math.PI * 2,
        hue: 240 + Math.random() * 60,
        alpha: 0.4 + Math.random() * 0.5,
      });
    }
    particlesRef.current = particles;

    function frame() {
      const W = canvas.width;
      const H = canvas.height;
      const cx = W / 2;
      const cy = H / 2;
      const isRec = recording.current;
      tRef.current += 0.016;
      const t = tRef.current;

      ctx.clearRect(0, 0, W, H);

      // Centre glow
      const grd = ctx.createRadialGradient(cx, cy, 0, cx, cy, 220);
      grd.addColorStop(0, `hsla(250,60%,${isRec ? 25 : 15}%,0.5)`);
      grd.addColorStop(1, "transparent");
      ctx.fillStyle = grd;
      ctx.fillRect(0, 0, W, H);

      const cols = 20;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.theta += p.speed * (isRec ? 1.8 : 1);

        let x, y, depth;

        if (isRec) {
          const col = i % cols;
          const row = Math.floor(i / cols);
          const rows = Math.ceil(particles.length / cols);
          const bh = 20 + Math.abs(Math.sin(t * 3 + col * 0.4 + p.phase)) * 80;
          x = cx - 200 + (col / cols) * 400;
          y = cy + bh - (row / rows) * bh * 2.2 + (Math.random() - 0.5) * 4;
          depth = 1;
          const hue = 340 + Math.sin(t + col * 0.3) * 30;
          ctx.beginPath();
          ctx.arc(x, y, Math.max(0.3, p.size), 0, Math.PI * 2);
          ctx.fillStyle = `hsla(${hue},85%,65%,${0.6 + Math.random() * 0.3})`;
          ctx.fill();
        } else {
          const r = p.baseR + Math.sin(t * 0.5 + p.phase) * 8;
          x = cx + r * Math.sin(p.phi) * Math.cos(p.theta);
          y = cy + r * Math.cos(p.phi) * 0.55;
          const z = r * Math.sin(p.phi) * Math.sin(p.theta);
          depth = (z + p.baseR) / (p.baseR * 2);
          const size = p.size * (0.4 + depth * 0.8);
          const alpha = p.alpha * (0.3 + depth * 0.7);
          const hue = p.hue + Math.sin(t * 0.4 + p.phase) * 30;

          ctx.beginPath();
          ctx.arc(x, y, Math.max(0.3, size), 0, Math.PI * 2);
          ctx.fillStyle = `hsla(${hue},75%,65%,${alpha})`;
          ctx.fill();

          // Connection lines
          if (i % 3 === 0) {
            for (let j = i + 1; j < Math.min(i + 8, particles.length); j++) {
              const q = particles[j];
              const qx = cx + q.baseR * Math.sin(q.phi) * Math.cos(q.theta);
              const qy = cy + q.baseR * Math.cos(q.phi) * 0.55;
              const d = Math.hypot(x - qx, y - qy);
              if (d < 40) {
                ctx.beginPath();
                ctx.moveTo(x, y);
                ctx.lineTo(qx, qy);
                ctx.strokeStyle = `hsla(260,70%,70%,${(1 - d / 40) * 0.12})`;
                ctx.lineWidth = 0.5;
                ctx.stroke();
              }
            }
          }
        }
      }
      animRef.current = requestAnimationFrame(frame);
    }

    animRef.current = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("resize", resize);
    };
  }, []);
}

// ---------------------------------------------------------------------------
// Mode config
// ---------------------------------------------------------------------------
const MODES = {
  feed: {
    label: "feed mode — saving thoughts",
    title: "Your Digital Self",
    sub: "Speak or type to save your thoughts. The agent remembers everything you say.",
    placeholder: "Type a thought to save...",
  },
  ask: {
    label: "ask mode — query your memories",
    title: "Ask Your Past Self",
    sub: "Ask anything. The agent answers only from what you have told it.",
    placeholder: "What do I think about...",
  },
  beliefs: {
    label: "beliefs — your worldview",
    title: "Your Belief Index",
    sub: "Your opinions, values and patterns — extracted from everything you've said.",
    placeholder: "Search your beliefs...",
  },
  stats: {
    label: "memory stats",
    title: "Your Memory Bank",
    sub: "Everything stored: messages, opinions, embeddings and weekly digests.",
    placeholder: "Filter...",
  },
};

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------
export default function App() {
  const canvasRef = useRef(null);
  const isRecRef = useRef(false);
  const inputRef = useRef(null);

  const [mode, setModeState] = useState("feed");
  const [panelOpen, setPanelOpen] = useState(false);
  const [serverOk, setServerOk] = useState(null);
  const [inputVal, setInputVal] = useState("");
  const [messages, setMessages] = useState([]);
  const [recActive, setRecActive] = useState(false);

  const {
    submitFeedText,
    submitAsk,
    askMessages,
    feedMessages,
    voiceOutput,
    setVoiceOutput,
    submitFeedVoice,
  } = useAgent();
  const { isRecording, startRecording, stopRecording, audioBlob } =
    useVoiceRecorder();

  // Sync recording ref for canvas
  useEffect(() => {
    isRecRef.current = isRecording;
  }, [isRecording]);
  useEffect(() => {
    setRecActive(isRecording);
  }, [isRecording]);

  // Forward audio blob
  useEffect(() => {
    if (!audioBlob) return;
    if (mode === "feed") submitFeedVoice(audioBlob);
  }, [audioBlob]);

  // Canvas
  useParticleGlobe(canvasRef, isRecRef);

  // Health check
  useEffect(() => {
    checkHealth()
      .then(() => setServerOk(true))
      .catch(() => setServerOk(false));
  }, []);

  function setMode(m) {
    setModeState(m);
    setInputVal("");
  }

  async function handleSend() {
    if (!inputVal.trim()) return;
    const text = inputVal.trim();
    setInputVal("");
    if (mode === "feed") {
      await submitFeedText(text);
      setMessages((prev) => [{ role: "feed", text, ts: new Date() }, ...prev]);
    } else if (mode === "ask") {
      await submitAsk(text);
    }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const cfg = MODES[mode] || MODES.feed;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#070711",
        fontFamily: "'Inter',system-ui,sans-serif",
        color: "#e8e8f0",
        overflow: "hidden",
      }}
    >
      {/* Canvas */}
      <canvas
        ref={canvasRef}
        style={{ position: "fixed", inset: 0, zIndex: 0 }}
      />

      {/* Navbar */}
      <nav
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          zIndex: 20,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "18px 32px",
          background: "rgba(7,7,17,0.6)",
          backdropFilter: "blur(20px)",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "linear-gradient(135deg,#7c6fff,#a78bfa)",
              boxShadow: "0 0 12px rgba(124,111,255,0.8)",
            }}
          />
          <span
            style={{
              fontSize: 15,
              fontWeight: 600,
              letterSpacing: "0.02em",
              color: "#c4c4e0",
            }}
          >
            Personal AI
          </span>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background:
                serverOk === null
                  ? "#facc15"
                  : serverOk
                    ? "#4ade80"
                    : "#f87171",
              marginLeft: 4,
            }}
            title={serverOk ? "Server online" : "Offline"}
          />
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["feed", "ask", "beliefs", "stats"].map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                background:
                  mode === m
                    ? "rgba(124,111,255,0.2)"
                    : "rgba(255,255,255,0.05)",
                border: `1px solid ${mode === m ? "rgba(124,111,255,0.5)" : "rgba(255,255,255,0.08)"}`,
                color: mode === m ? "#a78bfa" : "rgba(200,200,220,0.7)",
                fontSize: 12,
                letterSpacing: "0.04em",
                padding: "7px 16px",
                borderRadius: 20,
                cursor: "pointer",
                fontFamily: "inherit",
                textTransform: "capitalize",
              }}
            >
              {m}
            </button>
          ))}
          <button
            onClick={() => setPanelOpen((p) => !p)}
            style={{
              background: panelOpen
                ? "rgba(124,111,255,0.2)"
                : "rgba(255,255,255,0.05)",
              border: `1px solid ${panelOpen ? "rgba(124,111,255,0.5)" : "rgba(255,255,255,0.08)"}`,
              color: panelOpen ? "#a78bfa" : "rgba(200,200,220,0.7)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "7px 16px",
              borderRadius: 20,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            memories
          </button>
          {mode === "ask" && (
            <button
              onClick={() => setVoiceOutput((v) => !v)}
              style={{
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: voiceOutput ? "#a78bfa" : "rgba(200,200,220,0.4)",
                fontSize: 16,
                width: 36,
                height: 36,
                borderRadius: "50%",
                cursor: "pointer",
              }}
            >
              {voiceOutput ? "🔊" : "🔇"}
            </button>
          )}
        </div>
      </nav>

      {/* Centre UI */}
      <div
        style={{
          position: "fixed",
          top: "50%",
          left: panelOpen ? "calc(50% - 140px)" : "50%",
          transform: "translate(-50%,-50%)",
          zIndex: 10,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 28,
          textAlign: "center",
          transition: "left 0.4s cubic-bezier(0.25,0.46,0.45,0.94)",
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "rgba(180,180,210,0.45)",
              marginBottom: 8,
            }}
          >
            {cfg.label}
          </div>
          <h1
            style={{
              fontSize: 44,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              background:
                "linear-gradient(135deg,#e8e8f8 0%,#a78bfa 50%,#7c6fff 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              lineHeight: 1.1,
            }}
          >
            {cfg.title}
          </h1>
        </div>

        <p
          style={{
            fontSize: 14,
            color: "rgba(180,180,210,0.5)",
            letterSpacing: "0.02em",
            maxWidth: 300,
            lineHeight: 1.6,
          }}
        >
          {cfg.sub}
        </p>

        {/* Record button */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div
            style={{
              position: "relative",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {recActive && (
              <>
                <span
                  style={{
                    position: "absolute",
                    inset: -8,
                    borderRadius: "50%",
                    border: "1px solid rgba(220,50,80,0.4)",
                    animation: "pulse 1s ease-in-out infinite",
                  }}
                />
                <span
                  style={{
                    position: "absolute",
                    inset: -16,
                    borderRadius: "50%",
                    border: "1px solid rgba(220,50,80,0.2)",
                    animation: "pulse 1s ease-in-out infinite 0.2s",
                  }}
                />
              </>
            )}
            {!recActive && (
              <>
                <span
                  style={{
                    position: "absolute",
                    inset: -8,
                    borderRadius: "50%",
                    border: "1px solid rgba(124,111,255,0.3)",
                    animation: "pulse 2s ease-in-out infinite",
                  }}
                />
                <span
                  style={{
                    position: "absolute",
                    inset: -16,
                    borderRadius: "50%",
                    border: "1px solid rgba(124,111,255,0.15)",
                    animation: "pulse 2s ease-in-out infinite 0.4s",
                  }}
                />
              </>
            )}
            <button
              onMouseDown={startRecording}
              onMouseUp={stopRecording}
              onTouchStart={startRecording}
              onTouchEnd={stopRecording}
              style={{
                width: 80,
                height: 80,
                borderRadius: "50%",
                border: `1px solid ${recActive ? "rgba(220,50,80,0.6)" : "rgba(124,111,255,0.4)"}`,
                background: recActive
                  ? "rgba(220,50,80,0.2)"
                  : "rgba(124,111,255,0.15)",
                fontSize: 28,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                transform: recActive ? "scale(1.1)" : "scale(1)",
                transition: "all 0.3s cubic-bezier(0.34,1.56,0.64,1)",
                position: "relative",
              }}
            >
              {recActive ? "⏹" : "🎤"}
            </button>
          </div>
          <span
            style={{
              fontSize: 11,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: recActive
                ? "rgba(220,80,100,0.8)"
                : "rgba(180,180,210,0.4)",
            }}
          >
            {recActive ? "recording..." : "hold to record"}
          </span>
        </div>

        {/* Text input */}
        <div
          style={{ display: "flex", gap: 10, width: 360, alignItems: "center" }}
        >
          <input
            ref={inputRef}
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            onKeyDown={handleKey}
            placeholder={cfg.placeholder}
            style={{
              flex: 1,
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#e8e8f0",
              fontSize: 13,
              padding: "12px 18px",
              borderRadius: 28,
              outline: "none",
              fontFamily: "inherit",
              letterSpacing: "0.01em",
            }}
          />
          <button
            onClick={handleSend}
            style={{
              width: 42,
              height: 42,
              borderRadius: "50%",
              background: "rgba(124,111,255,0.25)",
              border: "1px solid rgba(124,111,255,0.4)",
              color: "#a78bfa",
              fontSize: 18,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            →
          </button>
        </div>

        {/* Ask mode — show last answer */}
        {mode === "ask" &&
          askMessages.length > 0 &&
          (() => {
            const last = askMessages[askMessages.length - 1];
            if (last.role !== "agent") return null;
            return (
              <div
                style={{
                  maxWidth: 380,
                  background: "rgba(124,111,255,0.08)",
                  border: "1px solid rgba(124,111,255,0.2)",
                  borderRadius: 16,
                  padding: "14px 18px",
                  textAlign: "left",
                }}
              >
                <div
                  style={{
                    fontSize: 10,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: "rgba(167,139,250,0.6)",
                    marginBottom: 8,
                  }}
                >
                  🧠 Agent · {last.context_count || 0} memories
                </div>
                <p
                  style={{
                    fontSize: 13,
                    color: "rgba(220,220,240,0.9)",
                    lineHeight: 1.6,
                  }}
                >
                  {last.content}
                </p>
              </div>
            );
          })()}
      </div>

      {/* Memory panel */}
      <div
        style={{
          position: "fixed",
          right: 0,
          top: 0,
          bottom: 0,
          width: 280,
          zIndex: 15,
          background: "rgba(7,7,17,0.85)",
          backdropFilter: "blur(24px)",
          borderLeft: "1px solid rgba(255,255,255,0.06)",
          padding: "88px 20px 24px",
          transform: panelOpen ? "translateX(0)" : "translateX(100%)",
          transition: "transform 0.4s cubic-bezier(0.25,0.46,0.45,0.94)",
          display: "flex",
          flexDirection: "column",
          gap: 10,
          overflowY: "auto",
        }}
      >
        <div
          style={{
            fontSize: 10,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "rgba(180,180,210,0.35)",
            marginBottom: 4,
          }}
        >
          Recent Memories
        </div>
        {feedMessages.length === 0 ? (
          <p
            style={{
              fontSize: 12,
              color: "rgba(180,180,210,0.3)",
              lineHeight: 1.6,
            }}
          >
            No memories yet — start talking in Feed mode.
          </p>
        ) : (
          feedMessages.slice(0, 12).map((m, i) => (
            <div
              key={m.id || i}
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 12,
                padding: "12px 14px",
                cursor: "pointer",
              }}
            >
              <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
                <span
                  style={{
                    fontSize: 9,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    padding: "2px 7px",
                    borderRadius: 10,
                    background: "rgba(124,111,255,0.15)",
                    color: "rgba(167,139,250,0.9)",
                    border: "1px solid rgba(124,111,255,0.2)",
                  }}
                >
                  {{ english: "EN", hindi: "HI", hinglish: "HI+EN" }[
                    m.language
                  ] || "?"}
                </span>
                {m.is_opinion && (
                  <span
                    style={{
                      fontSize: 9,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      padding: "2px 7px",
                      borderRadius: 10,
                      background: "rgba(167,100,200,0.12)",
                      color: "rgba(200,150,240,0.9)",
                      border: "1px solid rgba(167,100,200,0.2)",
                    }}
                  >
                    belief
                  </span>
                )}
              </div>
              <p
                style={{
                  fontSize: 12,
                  color: "rgba(200,200,220,0.7)",
                  lineHeight: 1.5,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {m.text}
              </p>
              <p
                style={{
                  fontSize: 10,
                  color: "rgba(150,150,180,0.35)",
                  marginTop: 6,
                }}
              >
                {new Date(m.timestamp).toLocaleTimeString()}
              </p>
            </div>
          ))
        )}
      </div>

      {/* Pulse keyframes */}
      <style>{`
        @keyframes pulse {
          0%,100% { transform: scale(1); opacity: 0.8; }
          50%      { transform: scale(1.08); opacity: 0.3; }
        }
        input::placeholder { color: rgba(180,180,210,0.3); }
        input:focus { border-color: rgba(124,111,255,0.4) !important; background: rgba(124,111,255,0.05) !important; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }
      `}</style>
    </div>
  );
}
