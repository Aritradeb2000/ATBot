"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMarketStream } from "@/lib/websocket";
import { motion } from "framer-motion";

const NAV_ITEMS = [
  { href: "/",          icon: "⊞",  label: "Dashboard" },
  { href: "/screener",  icon: "⊙",  label: "Screener" },
  { href: "/optimizer", icon: "◈",  label: "Optimizer" },
  { href: "/news",      icon: "◉",  label: "News" },
  { href: "/market",    icon: "⊕",  label: "Market" },
  { href: "/learn",     icon: "⚛",  label: "Learn" },
  { href: "/settings",  icon: "⊘",  label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { connected } = useMarketStream();

  return (
    <aside
      style={{
        width: 220,
        minHeight: "100vh",
        background: "#0a0e1a",
        borderRight: "1px solid rgba(255,255,255,0.06)",
        display: "flex",
        flexDirection: "column",
        position: "fixed",
        left: 0,
        top: 0,
        bottom: 0,
        zIndex: 50,
      }}
    >
      {/* Logo */}
      <div style={{ padding: "24px 20px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18, fontWeight: 800, color: "#fff",
            boxShadow: "0 0 16px rgba(59,130,246,0.4)",
          }}>A</div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, color: "#f1f5f9", letterSpacing: "-0.02em" }}>ATBot</div>
            <div style={{ fontSize: 10, color: "#475569", fontWeight: 500 }}>AI Trade Intelligence</div>
          </div>
        </div>

        {/* Connection status */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 12, padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.04)" }}>
          <span style={{
            width: 7, height: 7, borderRadius: "50%",
            background: connected ? "#22c55e" : "#ef4444",
            boxShadow: connected ? "0 0 6px #22c55e" : "none",
            display: "inline-block",
          }} />
          <span style={{ fontSize: 11, color: connected ? "#86efac" : "#f87171", fontWeight: 600 }}>
            {connected ? "Live" : "Reconnecting..."}
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ padding: "8px 12px", flex: 1 }}>
        <div style={{ fontSize: 10, color: "#334155", fontWeight: 700, letterSpacing: "0.1em", paddingLeft: 8, marginBottom: 4 }}>MENU</div>
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link key={item.href} href={item.href}>
              <motion.div
                whileHover={{ x: 3 }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "10px 12px",
                  borderRadius: 10,
                  marginBottom: 2,
                  background: active ? "rgba(59,130,246,0.12)" : "transparent",
                  border: active ? "1px solid rgba(59,130,246,0.25)" : "1px solid transparent",
                  cursor: "pointer",
                  transition: "background 0.15s ease",
                }}
              >
                <span style={{ fontSize: 16, color: active ? "#60a5fa" : "#475569" }}>{item.icon}</span>
                <span style={{ fontSize: 13, fontWeight: 600, color: active ? "#93c5fd" : "#64748b" }}>{item.label}</span>
                {active && (
                  <div style={{ marginLeft: "auto", width: 4, height: 4, borderRadius: "50%", background: "#3b82f6" }} />
                )}
              </motion.div>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div style={{ padding: "16px 20px", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ fontSize: 10, color: "#1e293b" }}>ATBot v1.0 · NSE/BSE India</div>
      </div>
    </aside>
  );
}
