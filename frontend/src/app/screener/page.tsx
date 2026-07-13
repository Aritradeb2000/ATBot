"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import SignalBadge from "@/components/ui/SignalBadge";
import { runScreener, type ScreenerResult, type ScreenerParams } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────
type SignalFilter = "ALL" | "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL";
type SortBy = "score" | "rsi" | "change_pct" | "symbol";
type Preset = "custom" | "breakout" | "reversal";

// ── Helpers ───────────────────────────────────────────────────────────────────
const scoreColor = (s: number) => s >= 70 ? "#22c55e" : s >= 50 ? "#f59e0b" : "#ef4444";
const rsiColor   = (r: number) => r < 30 ? "#22c55e" : r > 70 ? "#ef4444" : "#94a3b8";
const regimeColor = (r: string) => r === "BULL" ? "#22c55e" : r === "BEAR" ? "#ef4444" : "#f59e0b";

// ── Subcomponents ─────────────────────────────────────────────────────────────
function FilterPill({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "5px 12px",
        borderRadius: 8,
        fontSize: 12,
        fontWeight: 600,
        cursor: "pointer",
        background: active ? "rgba(59,130,246,0.15)" : "transparent",
        border: active ? "1px solid rgba(59,130,246,0.4)" : "1px solid transparent",
        color: active ? "#60a5fa" : "#64748b",
        textAlign: "left",
        transition: "all 0.15s",
      }}
    >
      {children}
    </button>
  );
}

function Chip({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 6,
      background: color + "18", border: `1px solid ${color}30`, color,
    }}>
      {children}
    </span>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
type Universe = "nifty50" | "nifty200" | "watchlist";

export default function ScreenerPage() {
  const [preset, setPreset]         = useState<Preset>("custom");
  const [signal, setSignal]         = useState<SignalFilter>("ALL");
  const [minScore, setMinScore]     = useState(0);
  const [minRsi, setMinRsi]         = useState(0);
  const [maxRsi, setMaxRsi]         = useState(100);
  const [sortBy, setSortBy]         = useState<SortBy>("score");
  const [universe, setUniverse]     = useState<Universe>("nifty50");
  const [watchlistSyms, setWatchlistSyms] = useState<string>("");

  const [results, setResults]       = useState<ScreenerResult[]>([]);
  const [meta, setMeta]             = useState<{ scanned: number; found: number; filtered: number; data_source?: string; last_computed?: string } | null>(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const [hasScanned, setHasScanned] = useState(false);
  const [nightlyStatus, setNightlyStatus] = useState<{ status: string; completed_at: string | null; saved: number; duration_s: number | null } | null>(null);

  // Load watchlist from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem("atbot_watchlist");
      if (stored) setWatchlistSyms(JSON.parse(stored).join(","));
    } catch { /* ignore */ }
  }, []);

  // Fetch nightly status on mount
  useEffect(() => {
    fetch("http://localhost:8000/api/screener/status")
      .then(r => r.json())
      .then(d => setNightlyStatus(d))
      .catch(() => null);
  }, []);

  // Auto-load pre-computed results when universe changes to nifty50 or nifty200
  useEffect(() => {
    if (universe === "nifty50" || universe === "nifty200") {
      handleScan();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [universe]);

  const handleScan = async () => {
    setLoading(true);
    setError(null);
    setHasScanned(true);

    const isCustom = universe === "watchlist";
    const params: ScreenerParams = {
      universe: isCustom ? "custom" : universe,
      signal, min_score: minScore, min_rsi: minRsi, max_rsi: maxRsi, preset, sort_by: sortBy,
    };
    if (isCustom && watchlistSyms) params.symbols = watchlistSyms;

    try {
      const data = await runScreener(params);
      setResults(data.results);
      setMeta({ scanned: data.total_scanned, found: data.total_found, filtered: data.total_filtered,
        data_source: (data as any).data_source, last_computed: (data as any).last_computed });
    } catch {
      setError("Scan failed. Make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  };

  const SIGNAL_OPTIONS: SignalFilter[] = ["ALL", "STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"];
  const universeLabel = universe === "nifty50" ? "Nifty 50 (50 stocks)" : universe === "nifty200" ? "Nifty 200 (200 stocks)" : "My Watchlist";

  return (
    <div style={{ maxWidth: 1300 }}>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 16 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>Screener</h1>
        <p style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>
          Filter and rank NSE stocks by AI composite score · {universeLabel}
        </p>
      </motion.div>

      {/* Nightly status banner */}
      {nightlyStatus && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          style={{ marginBottom: 16, padding: "8px 14px", borderRadius: 10,
            background: nightlyStatus.status === "completed" ? "rgba(34,197,94,0.07)" : nightlyStatus.status === "running" ? "rgba(59,130,246,0.07)" : "rgba(255,255,255,0.03)",
            border: nightlyStatus.status === "completed" ? "1px solid rgba(34,197,94,0.2)" : nightlyStatus.status === "running" ? "1px solid rgba(59,130,246,0.2)" : "1px solid rgba(255,255,255,0.07)",
            display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 12 }}>
            {nightlyStatus.status === "running" && <span style={{ color: "#60a5fa" }}>⏳ Nightly pre-computation running…</span>}
            {nightlyStatus.status === "completed" && (
              <span style={{ color: "#22c55e" }}>
                ✅ Pre-computed · {nightlyStatus.saved} stocks scored
                {nightlyStatus.completed_at && (
                  <> · {new Date(nightlyStatus.completed_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" })}</>
                )}
                {nightlyStatus.duration_s && <> · {nightlyStatus.duration_s}s</>}
              </span>
            )}
            {nightlyStatus.status === "idle" && <span style={{ color: "#475569" }}>🌙 Nightly scan runs at 4:00 PM IST weekdays</span>}
            {nightlyStatus.status === "failed" && <span style={{ color: "#ef4444" }}>⚠️ Last nightly scan failed — showing cached data</span>}
          </div>
          {meta?.data_source && (
            <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 5,
              background: meta.data_source === "precomputed" ? "rgba(34,197,94,0.15)" : "rgba(99,102,241,0.15)",
              color: meta.data_source === "precomputed" ? "#22c55e" : "#a5b4fc" }}>
              {meta.data_source === "precomputed" ? "⚡ INSTANT" : "🔴 LIVE"}
            </span>
          )}
        </motion.div>
      )}

      {/* Preset strategy pills */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        {([
          { id: "custom"   as const, icon: "⊙", label: "Custom Filters" },
          { id: "breakout" as const, icon: "🚀", label: "Breakout Setups" },
          { id: "reversal" as const, icon: "🔄", label: "Reversal Candidates" },
        ] as const).map((p) => (
          <button
            key={p.id}
            onClick={() => setPreset(p.id)}
            style={{
              padding: "9px 20px",
              borderRadius: 10,
              background: preset === p.id ? "rgba(59,130,246,0.15)" : "rgba(255,255,255,0.04)",
              border: preset === p.id ? "1px solid rgba(59,130,246,0.4)" : "1px solid rgba(255,255,255,0.08)",
              color: preset === p.id ? "#60a5fa" : "#64748b",
              fontSize: 13, fontWeight: 700, cursor: "pointer",
            }}
          >
            {p.icon} {p.label}
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 20 }}>
        {/* ── Filters panel ─────────────────────────────────────────── */}
        <div className="glass-card p-5 h-fit" style={{ position: "sticky", top: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", letterSpacing: "0.08em", marginBottom: 16 }}>
            FILTERS
          </div>

          {/* Universe */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>UNIVERSE</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 8 }}>
              {([
                { id: "nifty50"  as const, label: "Nifty 50",  sub: "50 stocks · instant" },
                { id: "nifty200" as const, label: "Nifty 200", sub: "200 stocks · instant" },
                { id: "watchlist" as const, label: "My Watchlist", sub: "custom · live" },
              ]).map((u) => (
                <button key={u.id} onClick={() => setUniverse(u.id)} style={{
                  padding: "7px 10px", borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: "pointer",
                  background: universe === u.id ? "rgba(59,130,246,0.15)" : "rgba(255,255,255,0.04)",
                  border: universe === u.id ? "1px solid rgba(59,130,246,0.4)" : "1px solid rgba(255,255,255,0.08)",
                  color: universe === u.id ? "#60a5fa" : "#64748b",
                  textAlign: "left",
                }}>
                  {u.label}
                  <div style={{ fontSize: 9, fontWeight: 400, color: universe === u.id ? "#93c5fd" : "#334155", marginTop: 2 }}>{u.sub}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Signal */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>SIGNAL TYPE</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 8 }}>
              {SIGNAL_OPTIONS.map((s) => (
                <FilterPill key={s} active={signal === s} onClick={() => setSignal(s)}>{s}</FilterPill>
              ))}
            </div>
          </div>

          {/* Min Score */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>
              MIN SCORE: <span style={{ color: "#60a5fa" }}>{minScore}</span>
            </label>
            <input
              type="range" min={0} max={90} value={minScore}
              onChange={(e) => setMinScore(+e.target.value)}
              style={{ width: "100%", marginTop: 8, accentColor: "#3b82f6" }}
            />
          </div>

          {/* RSI Range */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>
              RSI RANGE: <span style={{ color: "#60a5fa" }}>{minRsi}–{maxRsi}</span>
            </label>
            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              {[
                { label: "Min", val: minRsi, set: setMinRsi },
                { label: "Max", val: maxRsi, set: setMaxRsi },
              ].map(({ label, val, set }) => (
                <input key={label} type="number" value={val} min={0} max={100}
                  onChange={(e) => set(+e.target.value)}
                  style={{ width: "100%", padding: "6px 8px", borderRadius: 8, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#f1f5f9", fontSize: 12, outline: "none" }}
                />
              ))}
            </div>
          </div>

          {/* Sort */}
          <div style={{ marginBottom: 24 }}>
            <label style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>SORT BY</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortBy)}
              style={{ width: "100%", marginTop: 8, padding: "8px 10px", borderRadius: 8, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#f1f5f9", fontSize: 12, outline: "none" }}
            >
              <option value="score">Composite Score ↓</option>
              <option value="rsi">RSI Low → High</option>
              <option value="change_pct">Change % ↓</option>
              <option value="symbol">Symbol A → Z</option>
            </select>
          </div>

          {/* Run Scan button */}
          <button
            onClick={handleScan}
            disabled={loading}
            style={{
              width: "100%", padding: "11px", borderRadius: 10,
              background: loading ? "rgba(59,130,246,0.3)" : "linear-gradient(135deg, #3b82f6, #6366f1)",
              border: "none", color: "#fff", fontSize: 14, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            }}
          >
            {loading ? (
              <>
                <span style={{ display: "inline-block", width: 14, height: 14, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
                Scanning…
              </>
            ) : "▶ Run Scan"}
          </button>
        </div>

        {/* ── Results ───────────────────────────────────────────────── */}
        <div>
          {/* Results header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <span style={{ fontSize: 13, color: "#475569" }}>
              {loading
                ? `⏳ ${universe === "nifty200" ? "Loading 200 stocks" : universe === "nifty50" ? "Loading 50 stocks" : "Scanning watchlist"}…`
                : meta
                  ? `${meta.filtered} results · ${meta.found} analysed · ${meta.scanned} scanned`
                  : "Loading pre-computed data…"}
            </span>
            {meta?.last_computed && (
              <span style={{ fontSize: 10, color: "#334155" }}>
                Computed: {new Date(meta.last_computed).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" })} IST
              </span>
            )}
          </div>

          {/* Loading skeletons */}
          {loading && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[...Array(10)].map((_, i) => (
                <div key={i} className="shimmer" style={{ height: 54, borderRadius: 12 }} />
              ))}
            </div>
          )}

          {/* Error */}
          {error && !loading && (
            <div className="glass-card p-6" style={{ textAlign: "center", color: "#ef4444" }}>
              ⚠️ {error}
            </div>
          )}

          {/* Empty */}
          {!loading && !error && hasScanned && results.length === 0 && (
            <div className="glass-card p-8" style={{ textAlign: "center" }}>
              <div style={{ fontSize: 32, marginBottom: 10 }}>🔍</div>
              <p style={{ color: "#64748b", fontSize: 13 }}>No stocks match your current filters.</p>
              <p style={{ color: "#334155", fontSize: 12, marginTop: 6 }}>Try relaxing the filters or choosing a different preset.</p>
            </div>
          )}

          {/* Pre-scan prompt — only for watchlist in pre-compute mode */}
          {!loading && !error && !hasScanned && universe === "watchlist" && (
            <div className="glass-card p-10" style={{ textAlign: "center" }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>📡</div>
              <p style={{ color: "#64748b", fontSize: 14, fontWeight: 600 }}>Set your filters and click Run Scan</p>
              <p style={{ color: "#334155", fontSize: 12, marginTop: 6 }}>
                Watchlist scan runs live and takes ~10–20 seconds.
              </p>
            </div>
          )}

          {/* Results table */}
          {!loading && results.length > 0 && (
            <AnimatePresence>
              <>
                {/* Table header */}
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "120px 1fr 90px 90px 60px 50px 50px 50px 110px 90px",
                  gap: 8, padding: "8px 16px", marginBottom: 4,
                }}>
                  {["SYMBOL","COMPANY","PRICE","CHANGE","SCORE","T","F","S","SIGNAL","RSI"].map((h) => (
                    <div key={h} style={{ fontSize: 10, fontWeight: 700, color: "#334155", letterSpacing: "0.07em" }}>{h}</div>
                  ))}
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {results.map((r, i) => {
                    const ticker = r.symbol.replace(".NS", "").replace(".BO", "");
                    const isUp = (r.change_pct ?? 0) >= 0;
                    return (
                      <motion.div
                        key={r.symbol}
                        initial={{ opacity: 0, x: -12 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: Math.min(i * 0.025, 0.4) }}
                      >
                        <Link href={`/stock/${encodeURIComponent(r.symbol)}`}>
                          <div
                            className="glass-card"
                            style={{
                              display: "grid",
                              gridTemplateColumns: "120px 1fr 90px 90px 60px 50px 50px 50px 110px 90px",
                              gap: 8, padding: "13px 16px", alignItems: "center", cursor: "pointer",
                              transition: "border-color 0.15s",
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.borderColor = "rgba(59,130,246,0.35)"}
                            onMouseLeave={(e) => e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)"}
                          >
                            {/* Symbol */}
                            <div>
                              <div style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9" }}>{ticker}</div>
                              <Chip color={regimeColor(r.regime)}>{r.regime}</Chip>
                            </div>

                            {/* Company */}
                            <div style={{ fontSize: 11, color: "#64748b" }} className="truncate">{r.company_name}</div>

                            {/* Price */}
                            <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9" }}>
                              {r.price != null ? `₹${r.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : "—"}
                            </div>

                            {/* Change % */}
                            <div style={{ fontSize: 12, fontWeight: 700, color: isUp ? "#22c55e" : "#ef4444" }}>
                              {r.change_pct != null
                                ? `${isUp ? "▲" : "▼"} ${Math.abs(r.change_pct).toFixed(2)}%`
                                : "—"}
                            </div>

                            {/* Score */}
                            <div style={{ fontSize: 16, fontWeight: 800, color: scoreColor(r.score) }}>
                              {Math.round(r.score)}
                            </div>

                            {/* T / F / S */}
                            {[r.components.technical, r.components.fundamental, r.components.sentiment].map((s, j) => (
                              <div key={j} style={{ fontSize: 12, fontWeight: 600, color: scoreColor(s) }}>
                                {Math.round(s)}
                              </div>
                            ))}

                            {/* Signal */}
                            <SignalBadge signal={r.signal} size="sm" />

                            {/* RSI */}
                            <div style={{ fontSize: 13, fontWeight: 700, color: r.rsi != null ? rsiColor(r.rsi) : "#475569" }}>
                              {r.rsi != null ? r.rsi.toFixed(1) : "—"}
                            </div>
                          </div>
                        </Link>
                      </motion.div>
                    );
                  })}
                </div>
              </>
            </AnimatePresence>
          )}
        </div>
      </div>

      {/* Spinner keyframe */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
