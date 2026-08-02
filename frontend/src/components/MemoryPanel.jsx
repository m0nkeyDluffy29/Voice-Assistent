/**
 * MemoryPanel.jsx — Sidebar panel showing memories, beliefs, and stats
 * Phase 5: Desktop UI Layer
 */

import { useState, useEffect } from "react";
import {
  getStats,
  getBeliefs,
  getRecentMemories,
  searchMemories,
} from "../utils/api";

export default function MemoryPanel() {
  const [tab, setTab] = useState("stats"); // 'stats' | 'memories' | 'beliefs'
  const [stats, setStats] = useState(null);
  const [beliefs, setBeliefs] = useState([]);
  const [memories, setMemories] = useState([]);
  const [search, setSearch] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadTab(tab);
  }, [tab]);

  async function loadTab(t) {
    setLoading(true);
    try {
      if (t === "stats") {
        const d = await getStats();
        setStats(d);
      }
      if (t === "beliefs") {
        const d = await getBeliefs(20);
        setBeliefs(d.beliefs || []);
      }
      if (t === "memories") {
        const d = await getRecentMemories(30);
        setMemories(d.messages || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(e) {
    e.preventDefault();
    if (!search.trim()) return;
    setSearching(true);
    try {
      const data = await searchMemories(search, 8);
      setResults(data.results || []);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="w-72 flex flex-col bg-white/5 border-l border-white/10 h-full">
      {/* Tab bar */}
      <div className="flex border-b border-white/10">
        {["stats", "memories", "beliefs"].map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setResults([]);
              setSearch("");
            }}
            className={`flex-1 py-2 text-xs capitalize transition-colors
              ${tab === t ? "text-indigo-400 border-b-2 border-indigo-400" : "text-white/40 hover:text-white/70"}`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {loading && (
          <p className="text-white/30 text-xs text-center py-4">Loading...</p>
        )}

        {/* ── Stats tab ─────────────────────────────────────── */}
        {tab === "stats" && stats && !loading && (
          <div className="space-y-3">
            <StatCard
              label="Total Messages"
              value={stats.sqlite?.total_messages ?? "—"}
            />
            <StatCard
              label="Opinions Saved"
              value={stats.sqlite?.total_opinions ?? "—"}
            />
            <StatCard
              label="Sessions"
              value={stats.sqlite?.total_sessions ?? "—"}
            />
            <StatCard label="Beliefs Indexed" value={stats.beliefs ?? "—"} />
            {stats.chroma && (
              <StatCard
                label="Vectors in DB"
                value={stats.chroma.total_memories_embedded}
              />
            )}
            {stats.sqlite?.by_language && (
              <div className="rounded-lg bg-white/5 p-3 space-y-1">
                <p className="text-xs text-white/40 mb-2">Languages</p>
                {Object.entries(stats.sqlite.by_language).map(
                  ([lang, count]) => (
                    <div key={lang} className="flex justify-between text-xs">
                      <span className="text-white/60 capitalize">{lang}</span>
                      <span className="text-white/90">{count}</span>
                    </div>
                  ),
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Memories tab ──────────────────────────────────── */}
        {tab === "memories" && !loading && (
          <div className="space-y-2">
            {/* Search bar */}
            <form onSubmit={handleSearch} className="flex gap-1">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search memories..."
                className="flex-1 bg-white/10 rounded px-2 py-1 text-xs text-white placeholder-white/30 outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                type="submit"
                disabled={searching}
                className="text-xs px-2 py-1 bg-indigo-600 rounded hover:bg-indigo-500 text-white disabled:opacity-40"
              >
                {searching ? "…" : "Go"}
              </button>
            </form>

            {/* Search results */}
            {results.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs text-white/30">
                  {results.length} results
                </p>
                {results.map((r, i) => (
                  <MemoryCard
                    key={i}
                    text={r.text}
                    lang={r.metadata?.language}
                    score={r.relevance_score}
                    ts={r.metadata?.timestamp}
                  />
                ))}
              </div>
            )}

            {/* Recent list (when no search) */}
            {results.length === 0 &&
              memories.map((m, i) => (
                <MemoryCard
                  key={m.id || i}
                  text={m.text}
                  lang={m.language}
                  ts={m.timestamp}
                />
              ))}
          </div>
        )}

        {/* ── Beliefs tab ───────────────────────────────────── */}
        {tab === "beliefs" && !loading && (
          <div className="space-y-2">
            {beliefs.length === 0 ? (
              <p className="text-white/30 text-xs text-center py-4">
                No beliefs indexed yet.
                <br />
                Run: python main.py --beliefs
              </p>
            ) : (
              beliefs.map((b, i) => (
                <div
                  key={b.id || i}
                  className="rounded-lg bg-white/5 p-3 space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-indigo-300 font-medium capitalize">
                      {b.topic}
                    </span>
                    <span className="text-xs text-white/30">
                      {Math.round(b.confidence * 100)}% conf
                    </span>
                  </div>
                  <p className="text-xs text-white/80 leading-relaxed">
                    {b.belief_text}
                  </p>
                  <p className="text-xs text-white/30">
                    mentioned {b.mention_count}×
                  </p>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="rounded-lg bg-white/5 p-3 flex justify-between items-center">
      <span className="text-xs text-white/50">{label}</span>
      <span className="text-sm font-semibold text-white/90">{value}</span>
    </div>
  );
}

function MemoryCard({ text, lang, ts, score }) {
  const badge = { english: "EN", hindi: "HI", hinglish: "HI+EN" }[lang] || "?";
  return (
    <div className="rounded-lg bg-white/5 p-2 space-y-1">
      {score !== undefined && (
        <span className="text-xs text-indigo-300">
          {Math.round(score * 100)}% match
        </span>
      )}
      <p className="text-xs text-white/80 leading-relaxed line-clamp-3">
        {text}
      </p>
      <div className="flex gap-2 text-xs text-white/30">
        <span>{badge}</span>
        {ts && <span>{ts.slice(0, 10)}</span>}
      </div>
    </div>
  );
}
