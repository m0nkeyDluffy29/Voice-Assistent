/**
 * ChatWindow.jsx — Scrollable message list for both Feed and Ask modes
 * Phase 5: Desktop UI Layer
 */

import { useEffect, useRef } from "react";

function FeedMessage({ msg }) {
  const langBadge =
    { english: "EN", hindi: "HI", hinglish: "HI+EN" }[msg.language] || "?";
  return (
    <div className="flex flex-col gap-1 py-3 border-b border-white/10">
      <div className="flex items-center gap-2">
        <span className="text-xs px-2 py-0.5 rounded bg-white/10 text-white/60">
          {langBadge}
        </span>
        {msg.is_opinion && (
          <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/30 text-indigo-300">
            💭 belief
          </span>
        )}
        {!msg.saved && (
          <span className="text-xs text-yellow-400/70">
            duplicate — not saved
          </span>
        )}
        <span className="text-xs text-white/30 ml-auto">
          {new Date(msg.timestamp).toLocaleTimeString()}
        </span>
      </div>
      <p className="text-white/90 text-sm leading-relaxed">{msg.text}</p>
    </div>
  );
}

function AgentMessage({ msg }) {
  return (
    <div className="flex flex-col gap-1 py-3">
      <div className="flex items-center gap-2">
        <span className="text-xs text-indigo-400 font-semibold">🧠 Agent</span>
        {msg.context_count > 0 && (
          <span className="text-xs text-white/30">
            {msg.context_count} memor{msg.context_count === 1 ? "y" : "ies"}{" "}
            used
          </span>
        )}
        {msg.streaming && (
          <span className="text-xs text-indigo-300 animate-pulse">
            thinking...
          </span>
        )}
      </div>
      <p
        className={`text-white/90 text-sm leading-relaxed ${msg.streaming ? "after:content-['▋'] after:animate-pulse" : ""}`}
      >
        {msg.content || (msg.streaming ? "" : "...")}
      </p>
    </div>
  );
}

function UserMessage({ msg }) {
  return (
    <div className="flex flex-col items-end gap-1 py-3">
      <div className="flex items-center gap-2">
        <span className="text-xs text-white/30">
          {new Date(msg.timestamp).toLocaleTimeString()}
        </span>
        <span className="text-xs text-white/50 font-semibold">You</span>
      </div>
      <div className="bg-indigo-600/40 rounded-2xl rounded-tr-sm px-4 py-2 max-w-[80%]">
        <p className="text-white/90 text-sm leading-relaxed">{msg.content}</p>
      </div>
    </div>
  );
}

export default function ChatWindow({
  messages = [],
  mode = "feed",
  emptyText = "Nothing yet.",
}) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-white/30 text-sm select-none">
        {emptyText}
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1 scrollbar-thin scrollbar-thumb-white/10">
      {mode === "feed"
        ? messages.map((m, i) => <FeedMessage key={m.id || i} msg={m} />)
        : messages.map((m, i) =>
            m.role === "user" ? (
              <UserMessage key={i} msg={m} />
            ) : (
              <AgentMessage key={i} msg={m} />
            ),
          )}
      <div ref={bottomRef} />
    </div>
  );
}
