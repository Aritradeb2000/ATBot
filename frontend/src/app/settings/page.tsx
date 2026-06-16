"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import useSWR from "swr";
import { getSettings, saveSettings, type UserSettings } from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n: number) =>
  n >= 10000000 ? `₹${(n / 10000000).toFixed(1)}Cr`
  : n >= 100000 ? `₹${(n / 100000).toFixed(1)}L`
  : n >= 1000   ? `₹${(n / 1000).toFixed(0)}K`
  : `₹${n}`;

// ── Subcomponents ─────────────────────────────────────────────────────────────
function SectionHeader({ icon, title, subtitle }: { icon: string; title: string; subtitle: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
      <div style={{ fontSize: 26, lineHeight: 1 }}>{icon}</div>
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9" }}>{title}</div>
        <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>{subtitle}</div>
      </div>
    </div>
  );
}

function Toggle({
  checked, onChange, id,
}: { checked: boolean; onChange: (v: boolean) => void; id: string }) {
  return (
    <label htmlFor={id} style={{ display: "inline-flex", alignItems: "center", cursor: "pointer", gap: 0 }}>
      <input id={id} type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)}
        style={{ position: "absolute", opacity: 0, width: 0, height: 0 }} />
      <div
        onClick={() => onChange(!checked)}
        style={{
          width: 44, height: 24, borderRadius: 99, position: "relative", cursor: "pointer",
          background: checked ? "linear-gradient(135deg, #3b82f6, #6366f1)" : "rgba(255,255,255,0.08)",
          border: checked ? "1px solid rgba(59,130,246,0.5)" : "1px solid rgba(255,255,255,0.1)",
          transition: "all 0.2s",
        }}
      >
        <div style={{
          position: "absolute", top: 3, left: checked ? 22 : 3,
          width: 16, height: 16, borderRadius: "50%", background: "#fff",
          boxShadow: "0 1px 4px rgba(0,0,0,0.3)", transition: "left 0.2s",
        }} />
      </div>
    </label>
  );
}

function SaveBanner({ show }: { show: boolean }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 10, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10 }}
          style={{
            position: "fixed", bottom: 28, right: 28, zIndex: 100,
            padding: "12px 22px", borderRadius: 12,
            background: "linear-gradient(135deg, #22c55e, #16a34a)",
            color: "#fff", fontSize: 13, fontWeight: 700,
            boxShadow: "0 8px 32px rgba(34,197,94,0.35)",
            display: "flex", alignItems: "center", gap: 8,
          }}
        >
          ✓ Settings saved
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const { data: remote, mutate } = useSWR<UserSettings>("settings", getSettings, { revalidateOnFocus: false });

  // Local state mirrors DB; also backed by localStorage for instant reads
  const [capital, setCapital]   = useState<number>(100000);
  const [riskProfile, setRiskProfile] = useState<"conservative" | "moderate" | "aggressive">("moderate");

  // Alert prefs
  const [alertSignal, setAlertSignal]     = useState(true);
  const [alertStrongOnly, setAlertStrongOnly] = useState(false);
  const [alertVolume, setAlertVolume]     = useState(true);
  const [vixThreshold, setVixThreshold]   = useState(20);
  const [fiiThreshold, setFiiThreshold]   = useState(2000);

  // Notification channels
  const [notifyBrowser, setNotifyBrowser] = useState(true);
  const [notifyTelegram, setNotifyTelegram] = useState(false);
  const [telegramId, setTelegramId]       = useState("");

  // Screener defaults
  const [screenerUniverse, setScreenerUniverse] = useState("nifty50");
  const [screenerSort, setScreenerSort]         = useState("score");

  const [saving, setSaving] = useState(false);
  const [saved, setSaved]   = useState(false);

  // Sync from DB response
  useEffect(() => {
    if (!remote) return;
    setCapital(remote.capital ?? 100000);
    setRiskProfile((remote.risk_profile as any) ?? "moderate");
    setAlertSignal(remote.alert_signal_change ?? true);
    setAlertStrongOnly(remote.alert_strong_signals_only ?? false);
    setAlertVolume(remote.alert_volume_spike ?? true);
    setVixThreshold(remote.alert_vix_threshold ?? 20);
    setFiiThreshold(remote.alert_fii_threshold ?? 2000);
    setNotifyBrowser(remote.notify_browser ?? true);
    setNotifyTelegram(remote.notify_telegram ?? false);
    setTelegramId(remote.telegram_chat_id ?? "");
    setScreenerUniverse(remote.screener_default_universe ?? "nifty50");
    setScreenerSort(remote.screener_default_sort ?? "score");
    // Mirror to localStorage for instant reads by other pages
    localStorage.setItem("atbot_capital", String(remote.capital ?? 100000));
    localStorage.setItem("atbot_risk_profile", remote.risk_profile ?? "moderate");
  }, [remote]);

  const handleSave = async () => {
    setSaving(true);
    const payload = {
      capital, risk_profile: riskProfile,
      alert_signal_change: alertSignal,
      alert_strong_signals_only: alertStrongOnly,
      alert_volume_spike: alertVolume,
      alert_vix_threshold: vixThreshold,
      alert_fii_threshold: fiiThreshold,
      notify_browser: notifyBrowser,
      notify_telegram: notifyTelegram,
      telegram_chat_id: telegramId || null,
      screener_default_universe: screenerUniverse,
      screener_default_sort: screenerSort,
    };
    try {
      await saveSettings(payload);
      // Also persist to localStorage immediately
      localStorage.setItem("atbot_capital", String(capital));
      localStorage.setItem("atbot_risk_profile", riskProfile);
      await mutate();
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      console.error("Save failed", e);
    } finally {
      setSaving(false);
    }
  };

  const QUICK_AMOUNTS = [25000, 50000, 100000, 250000, 500000, 1000000];
  const RISK_PROFILES = [
    { id: "conservative", icon: "🛡️", label: "Conservative", desc: "Risk 1% per trade · Cap 15% per stock · Only BUY/STRONG BUY signals" },
    { id: "moderate",     icon: "⚖️", label: "Moderate",     desc: "Risk 1.5% per trade · Cap 20% per stock · BUY signals and above" },
    { id: "aggressive",   icon: "🚀", label: "Aggressive",   desc: "Risk 2% per trade · Cap 25% per stock · All signals including HOLD" },
  ] as const;

  const inputStyle: React.CSSProperties = {
    padding: "9px 12px", borderRadius: 8, background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)", color: "#f1f5f9", fontSize: 13, outline: "none",
  };

  return (
    <div style={{ maxWidth: 720 }}>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>Settings</h1>
        <p style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>
          Your trading profile · Persisted to both browser and database
        </p>
      </motion.div>

      {/* ── 1. Trading Capital ────────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className="glass-card p-6" style={{ marginBottom: 16 }}>
        <SectionHeader icon="💰" title="Trading Capital" subtitle="ATBot uses this to calculate position sizes for every signal" />

        {/* Quick-select pills */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          {QUICK_AMOUNTS.map(amt => (
            <button key={amt} onClick={() => setCapital(amt)} style={{
              padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer",
              background: capital === amt ? "rgba(59,130,246,0.2)" : "rgba(255,255,255,0.04)",
              border: capital === amt ? "1px solid rgba(59,130,246,0.4)" : "1px solid rgba(255,255,255,0.08)",
              color: capital === amt ? "#60a5fa" : "#94a3b8",
            }}>
              {fmt(amt)}
            </button>
          ))}
        </div>

        {/* Manual input */}
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14 }}>
          <div style={{ position: "relative", flex: 1 }}>
            <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "#64748b", fontSize: 16, fontWeight: 700 }}>₹</span>
            <input type="number" value={capital} onChange={e => setCapital(+e.target.value)}
              placeholder="Custom amount…"
              style={{ ...inputStyle, width: "100%", paddingLeft: 30, fontSize: 15, fontWeight: 700 }} />
          </div>
        </div>

        {/* Capital info pill */}
        {capital > 0 && (
          <div style={{ padding: "10px 14px", borderRadius: 10, background: "rgba(59,130,246,0.07)", border: "1px solid rgba(59,130,246,0.15)" }}>
            <span style={{ fontSize: 12, color: "#93c5fd" }}>
              💡 With {fmt(capital)} capital, ATBot risks{" "}
              {riskProfile === "conservative" ? "1%" : riskProfile === "moderate" ? "1.5%" : "2%"} per trade
              = up to {fmt(capital * (riskProfile === "conservative" ? 0.01 : riskProfile === "moderate" ? 0.015 : 0.02))} risk per trade,
              max {fmt(capital * (riskProfile === "conservative" ? 0.15 : riskProfile === "moderate" ? 0.20 : 0.25))} in any single stock.
            </span>
          </div>
        )}
      </motion.div>

      {/* ── 2. Risk Profile ───────────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
        className="glass-card p-6" style={{ marginBottom: 16 }}>
        <SectionHeader icon="⚖️" title="Risk Profile" subtitle="Controls position sizing limits and which signals are acted upon" />
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {RISK_PROFILES.map(p => (
            <div key={p.id} onClick={() => setRiskProfile(p.id)} style={{
              display: "flex", alignItems: "center", gap: 14, padding: "14px 16px", borderRadius: 12, cursor: "pointer",
              background: riskProfile === p.id ? "rgba(59,130,246,0.12)" : "rgba(255,255,255,0.03)",
              border: riskProfile === p.id ? "1px solid rgba(59,130,246,0.35)" : "1px solid rgba(255,255,255,0.07)",
              transition: "all 0.15s",
            }}>
              <div style={{ fontSize: 22 }}>{p.icon}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: riskProfile === p.id ? "#60a5fa" : "#f1f5f9" }}>{p.label}</div>
                <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>{p.desc}</div>
              </div>
              <div style={{
                width: 18, height: 18, borderRadius: "50%", flexShrink: 0,
                border: riskProfile === p.id ? "5px solid #3b82f6" : "2px solid rgba(255,255,255,0.15)",
                background: riskProfile === p.id ? "#fff" : "transparent",
                transition: "all 0.15s",
              }} />
            </div>
          ))}
        </div>
      </motion.div>

      {/* ── 3. Alert Preferences ─────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
        className="glass-card p-6" style={{ marginBottom: 16 }}>
        <SectionHeader icon="🔔" title="Alert Preferences" subtitle="Choose which market events trigger notifications" />

        {[
          { id: "sig", label: "Signal Change Alerts", desc: "Notify when a stock's signal flips (e.g. HOLD → BUY)", val: alertSignal, set: setAlertSignal },
          { id: "strong", label: "Strong Signals Only", desc: "Only alert on STRONG BUY or STRONG SELL (ignores BUY/SELL/HOLD)", val: alertStrongOnly, set: setAlertStrongOnly },
          { id: "vol", label: "Volume Spike Alerts", desc: "Notify when a watchlist stock has >2× its average volume", val: alertVolume, set: setAlertVolume },
        ].map(({ id, label, desc, val, set }) => (
          <div key={id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#f1f5f9" }}>{label}</div>
              <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>{desc}</div>
            </div>
            <Toggle id={id} checked={val} onChange={set} />
          </div>
        ))}

        {/* Threshold inputs */}
        <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: "#64748b", display: "block", marginBottom: 6 }}>
              VIX ALERT THRESHOLD
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="number" value={vixThreshold} onChange={e => setVixThreshold(+e.target.value)} min={10} max={40} style={{ ...inputStyle, width: "100%" }} />
              <span style={{ fontSize: 11, color: "#475569", whiteSpace: "nowrap" }}>Alert if VIX ≥</span>
            </div>
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: "#64748b", display: "block", marginBottom: 6 }}>
              FII FLOW THRESHOLD (₹ Cr)
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="number" value={fiiThreshold} onChange={e => setFiiThreshold(+e.target.value)} min={0} max={20000} step={500} style={{ ...inputStyle, width: "100%" }} />
              <span style={{ fontSize: 11, color: "#475569", whiteSpace: "nowrap" }}>Alert if |FII| ≥</span>
            </div>
          </div>
        </div>
      </motion.div>

      {/* ── 4. Notification Channels ─────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
        className="glass-card p-6" style={{ marginBottom: 16 }}>
        <SectionHeader icon="📡" title="Notification Channels" subtitle="Where ATBot sends alerts (Telegram bot coming in Phase 7)" />

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#f1f5f9" }}>🌐 Browser Notifications</div>
            <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>Push alerts in the browser while ATBot is open</div>
          </div>
          <Toggle id="browser" checked={notifyBrowser} onChange={setNotifyBrowser} />
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "#f1f5f9" }}>📱 Telegram Alerts</span>
              <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 6, background: "rgba(245,158,11,0.15)", border: "1px solid rgba(245,158,11,0.3)", color: "#f59e0b", fontWeight: 700 }}>PHASE 7</span>
            </div>
            <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>Receive signal alerts directly in Telegram</div>
          </div>
          <Toggle id="telegram" checked={notifyTelegram} onChange={setNotifyTelegram} />
        </div>

        {notifyTelegram && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} style={{ paddingTop: 12 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: "#64748b", display: "block", marginBottom: 6 }}>
              TELEGRAM CHAT ID
            </label>
            <input type="text" value={telegramId} onChange={e => setTelegramId(e.target.value)}
              placeholder="e.g. 123456789" style={{ ...inputStyle, width: "100%" }} />
            <div style={{ fontSize: 11, color: "#334155", marginTop: 6 }}>
              Get your Chat ID by messaging @userinfobot on Telegram
            </div>
          </motion.div>
        )}
      </motion.div>

      {/* ── 5. Screener Defaults ──────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
        className="glass-card p-6" style={{ marginBottom: 24 }}>
        <SectionHeader icon="🔍" title="Screener Defaults" subtitle="Pre-fill the Screener page with your preferred settings" />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: "#64748b", display: "block", marginBottom: 6 }}>DEFAULT UNIVERSE</label>
            <select value={screenerUniverse} onChange={e => setScreenerUniverse(e.target.value)}
              style={{ ...inputStyle, width: "100%" }}>
              <option value="nifty50">Nifty 50</option>
              <option value="watchlist">My Watchlist</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: "#64748b", display: "block", marginBottom: 6 }}>DEFAULT SORT BY</label>
            <select value={screenerSort} onChange={e => setScreenerSort(e.target.value)}
              style={{ ...inputStyle, width: "100%" }}>
              <option value="score">Composite Score ↓</option>
              <option value="rsi">RSI Low → High</option>
              <option value="change_pct">Change % ↓</option>
              <option value="symbol">Symbol A → Z</option>
            </select>
          </div>
        </div>
      </motion.div>

      {/* ── Save button ───────────────────────────────────────────────────── */}
      <motion.button
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
        onClick={handleSave}
        disabled={saving}
        style={{
          width: "100%", padding: "14px", borderRadius: 12,
          background: saving ? "rgba(59,130,246,0.4)" : "linear-gradient(135deg, #3b82f6, #6366f1)",
          border: "none", color: "#fff", fontSize: 15, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer",
          boxShadow: "0 4px 20px rgba(59,130,246,0.25)",
        }}
      >
        {saving ? "Saving…" : "Save All Settings"}
      </motion.button>

      {/* ── How position sizing works ────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}
        className="glass-card p-6" style={{ marginTop: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", marginBottom: 14 }}>⚙ How Position Sizing Works</div>
        {[
          { step: "1", text: "ATBot calculates risk per share = Current Price − Stop Loss (ATR-based)" },
          { step: "2", text: "It targets risking 1–2% of your capital per trade (based on signal confidence + risk profile)" },
          { step: "3", text: "Quantity = (Capital × Risk%) ÷ Risk per Share" },
          { step: "4", text: "Safety cap: never allocates more than 15–25% of your capital to one stock (depends on risk profile)" },
        ].map(({ step, text }) => (
          <div key={step} style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: 10 }}>
            <div style={{ width: 22, height: 22, borderRadius: "50%", background: "rgba(59,130,246,0.15)", border: "1px solid rgba(59,130,246,0.3)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#60a5fa", flexShrink: 0 }}>{step}</div>
            <span style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.5 }}>{text}</span>
          </div>
        ))}
      </motion.div>

      <SaveBanner show={saved} />
    </div>
  );
}
