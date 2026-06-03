"use client";
import { useState } from "react";
import { motion } from "framer-motion";

export default function SettingsPage() {
  const [capital, setCapital] = useState<string>(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("atbot_capital") || "";
    }
    return "";
  });
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    const val = parseFloat(capital);
    if (!isNaN(val) && val > 0) {
      localStorage.setItem("atbot_capital", val.toString());
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }
  };

  const quickAmounts = [50000, 100000, 250000, 500000, 1000000];

  return (
    <div style={{ maxWidth: 600 }}>
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", marginBottom: 4 }}>Settings</h1>
        <p style={{ fontSize: 13, color: "#475569", marginBottom: 28 }}>Configure your trading profile for AI-powered position sizing</p>
      </motion.div>

      {/* Capital Card */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card p-6 mb-6">
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <div style={{ fontSize: 24 }}>💰</div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9" }}>Trading Capital</div>
            <div style={{ fontSize: 12, color: "#64748b" }}>
              ATBot uses this to calculate how many shares to buy per trade
            </div>
          </div>
        </div>

        {/* Quick amounts */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          {quickAmounts.map((amt) => (
            <button
              key={amt}
              onClick={() => setCapital(amt.toString())}
              style={{
                padding: "6px 14px",
                borderRadius: 8,
                background: capital === amt.toString() ? "rgba(59,130,246,0.2)" : "rgba(255,255,255,0.04)",
                border: capital === amt.toString() ? "1px solid rgba(59,130,246,0.4)" : "1px solid rgba(255,255,255,0.08)",
                color: capital === amt.toString() ? "#60a5fa" : "#94a3b8",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              ₹{(amt / 100000).toFixed(amt >= 100000 ? 1 : 0)}{amt >= 100000 ? "L" : "K"}
            </button>
          ))}
        </div>

        {/* Manual input */}
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <div style={{ position: "relative", flex: 1 }}>
            <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#64748b", fontSize: 16, fontWeight: 700 }}>₹</span>
            <input
              type="number"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
              placeholder="Enter your capital..."
              style={{
                width: "100%",
                padding: "12px 16px 12px 32px",
                borderRadius: 10,
                border: "1px solid rgba(255,255,255,0.1)",
                background: "rgba(255,255,255,0.05)",
                color: "#f1f5f9",
                fontSize: 15,
                outline: "none",
                fontWeight: 600,
              }}
            />
          </div>
          <button
            onClick={handleSave}
            style={{
              padding: "12px 24px",
              borderRadius: 10,
              background: saved
                ? "linear-gradient(135deg, #22c55e, #16a34a)"
                : "linear-gradient(135deg, #3b82f6, #6366f1)",
              border: "none",
              color: "#fff",
              fontSize: 14,
              fontWeight: 700,
              cursor: "pointer",
              whiteSpace: "nowrap",
              transition: "background 0.3s",
            }}
          >
            {saved ? "✓ Saved!" : "Save"}
          </button>
        </div>

        {capital && !isNaN(parseFloat(capital)) && (
          <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 10, background: "rgba(59,130,246,0.07)", border: "1px solid rgba(59,130,246,0.15)" }}>
            <span style={{ fontSize: 12, color: "#93c5fd" }}>
              💡 With ₹{parseFloat(capital).toLocaleString("en-IN")}, ATBot will suggest position sizes risking 1–2% per trade, capping any single stock at 20% of your portfolio.
            </span>
          </div>
        )}
      </motion.div>

      {/* Info card */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass-card p-6">
        <div style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9", marginBottom: 14 }}>⚙ How Position Sizing Works</div>
        <div className="space-y-3">
          {[
            { step: "1", text: "ATBot calculates risk per share = Current Price − Stop Loss (ATR-based)" },
            { step: "2", text: "It targets risking 1%–2% of your capital per trade (based on signal confidence)" },
            { step: "3", text: "Quantity = (Capital × Risk%) ÷ Risk per Share" },
            { step: "4", text: "Safety cap: never allocates more than 20% of your capital to one stock" },
          ].map(({ step, text }) => (
            <div key={step} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <div style={{
                width: 22, height: 22, borderRadius: "50%", background: "rgba(59,130,246,0.15)", border: "1px solid rgba(59,130,246,0.3)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#60a5fa", flexShrink: 0,
              }}>{step}</div>
              <span style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.5 }}>{text}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
