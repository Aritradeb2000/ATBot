"""
ATBot — PDF Report Generator
Generates a professional PDF accuracy report from the signal_outcomes table.
Includes: overall stats, signal breakdown, recent trades, top/worst stocks.
"""

import os
import logging
from datetime import datetime
from typing import Optional

from fpdf import FPDF
from sqlalchemy import select
from backend.models.database import AsyncSessionLocal
from backend.models.schemas import SignalOutcome
from backend.config import IST

logger = logging.getLogger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")


# ── Color Palette ─────────────────────────────────────────────────────────────
COLOR_BG       = (10, 15, 28)       # dark navy
COLOR_CARD     = (20, 27, 45)       # card bg
COLOR_ACCENT   = (99, 102, 241)     # indigo
COLOR_WIN      = (34, 197, 94)      # green
COLOR_LOSS     = (239, 68, 68)      # red
COLOR_TEXT     = (241, 245, 249)    # near-white
COLOR_SUBTEXT  = (100, 116, 139)    # slate
COLOR_HOLD     = (245, 158, 11)     # amber


def _safe(text: str) -> str:
    """Strip characters that fpdf's built-in Helvetica (latin-1) cannot encode."""
    replacements = {
        "\u2014": "-",   # em dash
        "\u2013": "-",   # en dash
        "\u2022": "*",   # bullet
        "\u2019": "'",   # right single quote
        "\u2018": "'",   # left single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u20b9": "Rs.",  # rupee sign
        "\u2b50": "*",   # star emoji
        "\u2705": "+",   # checkmark emoji
        "\u274c": "x",   # cross emoji
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Final fallback: drop anything still outside latin-1
    return text.encode("latin-1", errors="ignore").decode("latin-1")


class ATBotReport(FPDF):
    """Custom FPDF class with ATBot branding."""

    def header(self):
        # Dark header bar
        self.set_fill_color(*COLOR_BG)
        self.rect(0, 0, 210, 22, "F")
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*COLOR_ACCENT)
        self.set_xy(10, 6)
        self.cell(0, 10, _safe("ATBot - AI Signal Accuracy Report"), ln=False)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*COLOR_SUBTEXT)
        self.set_xy(10, 14)
        self.cell(0, 6, f"Generated: {datetime.now(IST).strftime('%d %b %Y, %I:%M %p IST')}", ln=True)
        self.set_draw_color(*COLOR_ACCENT)
        self.set_line_width(0.5)
        self.line(0, 22, 210, 22)
        self.ln(6)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(*COLOR_SUBTEXT)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*COLOR_SUBTEXT)
        self.cell(0, 8, f"ATBot v1.0 | Page {self.page_no()} | Signals tracked over last 90 days", align="C")

    def section_title(self, title: str):
        self.ln(3)
        self.set_fill_color(*COLOR_CARD)
        self.set_text_color(*COLOR_ACCENT)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, f"  {title}", ln=True, fill=True)
        self.ln(2)

    def stat_card(self, x: float, y: float, w: float, h: float, label: str, value: str, color=None):
        color = color or COLOR_ACCENT
        self.set_xy(x, y)
        self.set_fill_color(*COLOR_CARD)
        self.set_draw_color(*color)
        self.set_line_width(0.4)
        self.rect(x, y, w, h, "FD")
        # value
        self.set_xy(x, y + 3)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*color)
        self.cell(w, 8, value, align="C")
        # label
        self.set_xy(x, y + 11)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*COLOR_SUBTEXT)
        self.cell(w, 5, label.upper(), align="C")


async def generate_accuracy_report(days: int = 90, check_day: int = 10) -> str:
    """
    Generate a PDF accuracy report and save it to the reports/ directory.
    check_day: 5 or 10 — must match the dashboard filter (default D10)
    Returns the absolute path to the saved PDF.
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)

    async with AsyncSessionLocal() as db:
        from datetime import timedelta
        cutoff = datetime.now(IST).replace(tzinfo=None) - timedelta(days=days)

        result = await db.execute(
            select(SignalOutcome)
            .where(
                SignalOutcome.entry_date >= cutoff,
                SignalOutcome.check_day == check_day,   # match dashboard filter
            )
            .order_by(SignalOutcome.entry_date.desc())
        )
        rows = result.scalars().all()

    # ── Compute Stats ─────────────────────────────────────────────────────────
    resolved = [r for r in rows if r.outcome in ("WIN", "LOSS", "BREAKEVEN")]
    wins     = [r for r in resolved if r.outcome == "WIN"]
    losses   = [r for r in resolved if r.outcome == "LOSS"]
    holds    = [r for r in rows if r.outcome in ("OPEN",)]

    total_signals  = len(rows)
    total_resolved = len(resolved)
    win_rate       = round((len(wins) / total_resolved) * 100, 1) if total_resolved else 0.0
    avg_pnl        = round(sum(r.pnl_percent or 0 for r in resolved) / total_resolved, 2) if total_resolved else 0.0
    avg_win_pnl    = round(sum(r.pnl_percent or 0 for r in wins) / len(wins), 2) if wins else 0.0
    avg_loss_pnl   = round(sum(r.pnl_percent or 0 for r in losses) / len(losses), 2) if losses else 0.0

    # By signal
    by_signal: dict = {}
    for r in resolved:
        sig = r.signal or "UNKNOWN"
        if sig not in by_signal:
            by_signal[sig] = {"total": 0, "wins": 0, "losses": 0, "pnl": []}
        by_signal[sig]["total"] += 1
        if r.outcome == "WIN":
            by_signal[sig]["wins"] += 1
        elif r.outcome == "LOSS":
            by_signal[sig]["losses"] += 1
        if r.pnl_percent is not None:
            by_signal[sig]["pnl"].append(r.pnl_percent)

    # Top / worst stocks
    by_stock: dict = {}
    for r in resolved:
        if r.symbol not in by_stock:
            by_stock[r.symbol] = {"total": 0, "wins": 0, "pnl": []}
        by_stock[r.symbol]["total"] += 1
        if r.outcome == "WIN":
            by_stock[r.symbol]["wins"] += 1
        if r.pnl_percent is not None:
            by_stock[r.symbol]["pnl"].append(r.pnl_percent)

    stock_stats = [
        {
            "symbol": sym,
            "total": v["total"],
            "win_rate": round((v["wins"] / v["total"]) * 100, 1) if v["total"] else 0,
            "avg_pnl": round(sum(v["pnl"]) / len(v["pnl"]), 2) if v["pnl"] else 0,
        }
        for sym, v in by_stock.items() if v["total"] >= 1
    ]
    stock_stats.sort(key=lambda x: -x["win_rate"])

    # ── Build PDF ─────────────────────────────────────────────────────────────
    pdf = ATBotReport()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(10, 10, 10)
    pdf.add_page()
    pdf.set_fill_color(*COLOR_BG)
    pdf.rect(0, 0, 210, 297, "F")  # full page bg

    # ── Section 1: Summary Title ───────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*COLOR_TEXT)
    pdf.cell(0, 10, _safe("Signal Accuracy Report"), ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*COLOR_SUBTEXT)
    pdf.cell(0, 6, _safe(f"Performance over last {days} days | Day {check_day} outcomes | {total_signals} signals tracked | {total_resolved} resolved"), ln=True, align="C")
    pdf.ln(5)

    # ── Section 2: KPI Cards ───────────────────────────────────────────────────
    pdf.section_title("Overall Performance")
    y = pdf.get_y()
    cw, ch, gap = 43, 24, 3
    cards = [
        ("Win Rate",       f"{win_rate}%",           COLOR_WIN if win_rate >= 50 else COLOR_LOSS),
        ("Avg P&L (All)",  f"{avg_pnl:+.2f}%",      COLOR_WIN if avg_pnl >= 0 else COLOR_LOSS),
        ("Avg Win",        f"{avg_win_pnl:+.2f}%",  COLOR_WIN),
        ("Avg Loss",       f"{avg_loss_pnl:+.2f}%", COLOR_LOSS),
    ]
    for i, (label, value, color) in enumerate(cards):
        pdf.stat_card(10 + i * (cw + gap), y, cw, ch, label, value, color)
    pdf.set_y(y + ch + 5)

    # second row of cards
    y2 = pdf.get_y()
    cards2 = [
        ("Total Signals",  str(total_signals),  COLOR_ACCENT),
        ("Resolved",       str(total_resolved), COLOR_ACCENT),
        ("Wins",           str(len(wins)),       COLOR_WIN),
        ("Losses",         str(len(losses)),     COLOR_LOSS),
    ]
    for i, (label, value, color) in enumerate(cards2):
        pdf.stat_card(10 + i * (cw + gap), y2, cw, ch, label, value, color)
    pdf.set_y(y2 + ch + 8)

    # ── Section 3: Signal Breakdown ────────────────────────────────────────────
    if by_signal:
        pdf.section_title("Accuracy by Signal Type")
        # Table header
        cols = [("Signal", 45), ("Total", 25), ("Wins", 25), ("Losses", 25), ("Win Rate", 30), ("Avg P&L", 30)]
        pdf.set_fill_color(*COLOR_ACCENT)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8)
        for col, w in cols:
            pdf.cell(w, 7, col, border=0, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        alternate = False
        for sig, stats in sorted(by_signal.items(), key=lambda x: -x[1]["wins"]):
            wr = round((stats["wins"] / stats["total"]) * 100, 1) if stats["total"] else 0
            ap = round(sum(stats["pnl"]) / len(stats["pnl"]), 2) if stats["pnl"] else 0
            bg = (18, 30, 50) if alternate else COLOR_CARD
            pdf.set_fill_color(*bg)
            pdf.set_text_color(*COLOR_TEXT)
            pdf.cell(45, 6, sig, fill=True, align="L", border=0)
            pdf.cell(25, 6, str(stats["total"]), fill=True, align="C", border=0)
            pdf.set_text_color(*COLOR_WIN)
            pdf.cell(25, 6, str(stats["wins"]), fill=True, align="C", border=0)
            pdf.set_text_color(*COLOR_LOSS)
            pdf.cell(25, 6, str(stats["losses"]), fill=True, align="C", border=0)
            wr_color = COLOR_WIN if wr >= 50 else COLOR_LOSS
            pdf.set_text_color(*wr_color)
            pdf.cell(30, 6, f"{wr}%", fill=True, align="C", border=0)
            ap_color = COLOR_WIN if ap >= 0 else COLOR_LOSS
            pdf.set_text_color(*ap_color)
            pdf.cell(30, 6, f"{ap:+.2f}%", fill=True, align="C", border=0)
            pdf.ln()
            alternate = not alternate
        pdf.ln(5)

    # ── Section 4: Stock Performance ───────────────────────────────────────────
    if stock_stats:
        pdf.section_title("Stock-level Performance")
        cols2 = [("Symbol", 40), ("Signals", 30), ("Win Rate", 30), ("Avg P&L", 30), ("Rating", 30)]
        pdf.set_fill_color(*COLOR_ACCENT)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8)
        for col, w in cols2:
            pdf.cell(w, 7, col, border=0, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        alternate = False
        for s in stock_stats[:20]:  # Top 20
            wr = s["win_rate"]
            ap = s["avg_pnl"]
            rating = "** Excellent" if wr >= 70 else ("Good" if wr >= 50 else "Poor")
            bg = (18, 30, 50) if alternate else COLOR_CARD
            pdf.set_fill_color(*bg)
            pdf.set_text_color(*COLOR_TEXT)
            pdf.cell(40, 6, s["symbol"].replace(".NS", ""), fill=True, align="L", border=0)
            pdf.cell(30, 6, str(s["total"]), fill=True, align="C", border=0)
            wr_color = COLOR_WIN if wr >= 50 else COLOR_LOSS
            pdf.set_text_color(*wr_color)
            pdf.cell(30, 6, f"{wr}%", fill=True, align="C", border=0)
            ap_color = COLOR_WIN if ap >= 0 else COLOR_LOSS
            pdf.set_text_color(*ap_color)
            pdf.cell(30, 6, f"{ap:+.2f}%", fill=True, align="C", border=0)
            r_color = COLOR_WIN if wr >= 70 else (COLOR_HOLD if wr >= 50 else COLOR_LOSS)
            pdf.set_text_color(*r_color)
            pdf.cell(30, 6, rating, fill=True, align="C", border=0)
            pdf.ln()
            alternate = not alternate
        pdf.ln(5)

    # ── Section 5: Recent Trades ───────────────────────────────────────────────
    recent = [r for r in rows if r.outcome in ("WIN", "LOSS", "BREAKEVEN")][:25]
    if recent:
        pdf.section_title(f"Recent Resolved Signals (Last {min(25, len(recent))})")
        cols3 = [("Date", 25), ("Symbol", 30), ("Signal", 28), ("Entry", 22), ("Exit", 22), ("P&L%", 20), ("Outcome", 23)]
        pdf.set_fill_color(*COLOR_ACCENT)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 7)
        for col, w in cols3:
            pdf.cell(w, 6, col, border=0, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 7)
        alternate = False
        for r in recent:
            bg = (18, 30, 50) if alternate else COLOR_CARD
            pdf.set_fill_color(*bg)
            pdf.set_text_color(*COLOR_TEXT)
            entry_date = r.entry_date.strftime("%d %b") if r.entry_date else "—"
            pnl_color = COLOR_WIN if (r.pnl_percent or 0) >= 0 else COLOR_LOSS
            out_color  = COLOR_WIN if r.outcome == "WIN" else (COLOR_LOSS if r.outcome == "LOSS" else COLOR_HOLD)

            pdf.cell(25, 5, entry_date, fill=True, align="C", border=0)
            pdf.cell(30, 5, (r.symbol or "").replace(".NS", ""), fill=True, align="L", border=0)
            pdf.cell(28, 5, _safe(r.signal or "-"), fill=True, align="C", border=0)
            pdf.cell(22, 5, f"Rs.{r.entry_price:.0f}" if r.entry_price else "-", fill=True, align="R", border=0)
            pdf.cell(22, 5, f"Rs.{r.price_at_check:.0f}" if r.price_at_check else "-", fill=True, align="R", border=0)
            pdf.set_text_color(*pnl_color)
            pdf.cell(20, 5, f"{r.pnl_percent:+.1f}%" if r.pnl_percent else "—", fill=True, align="C", border=0)
            pdf.set_text_color(*out_color)
            pdf.cell(23, 5, r.outcome or "—", fill=True, align="C", border=0)
            pdf.ln()
            alternate = not alternate
        pdf.ln(5)

    # ── Footer disclaimer ─────────────────────────────────────────────────────
    pdf.section_title("Disclaimer")
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*COLOR_SUBTEXT)
    pdf.multi_cell(0, 4,
        "This report is generated by ATBot, an AI-powered stock analysis system. "
        "Past performance is not indicative of future results. All signals are for "
        "informational and educational purposes only. This is not financial advice. "
        "Please consult a SEBI-registered financial advisor before making any investment decisions.",
        align="L"
    )

    # ── Save ──────────────────────────────────────────────────────────────────
    fname = f"ATBot_Accuracy_Report_{datetime.now(IST).strftime('%Y%m%d_%H%M')}.pdf"
    fpath = os.path.join(REPORTS_DIR, fname)
    pdf.output(fpath)
    logger.info(f"📄 Report saved: {fpath}")
    return fpath
