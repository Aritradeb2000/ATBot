"use client";
import { useEffect, useRef } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import {
  createChart,
  ColorType,
  LineStyle,
  CandlestickSeries,
  type IChartApi,
} from "lightweight-charts";

interface OHLCVBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface Targets {
  stopLoss?: number;
  conservative?: number;
  base?: number;
  aggressive?: number;
}

interface Props {
  symbol: string;
  period?: string;
  interval?: string;
  height?: number;
  targets?: Targets;
}

async function fetchOHLCV(symbol: string, period: string, interval: string): Promise<OHLCVBar[]> {
  const res = await api.get(`/api/ohlcv/${encodeURIComponent(symbol)}`, {
    params: { period, interval },
  });
  return res.data;
}

export default function StockChart({ symbol, period = "6mo", interval = "1d", height = 460, targets }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const { data, isLoading, error } = useSWR<OHLCVBar[]>(
    ["ohlcv", symbol, period, interval],
    () => fetchOHLCV(symbol, period, interval),
    { revalidateOnFocus: false }
  );

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;

    // Destroy previous chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0d1225" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      crosshair: {
        vertLine: { color: "#3b82f6", width: 1, style: LineStyle.Dashed },
        horzLine: { color: "#3b82f6", width: 1, style: LineStyle.Dashed },
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: {
        borderColor: "rgba(255,255,255,0.08)",
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height,
    });

    chartRef.current = chart;

    // Candlestick series — v5 syntax
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    candleSeries.setData(data);

    // Price target lines
    if (targets?.stopLoss) {
      candleSeries.createPriceLine({ price: targets.stopLoss, color: "#ef4444", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "SL" });
    }
    if (targets?.conservative) {
      candleSeries.createPriceLine({ price: targets.conservative, color: "#86efac", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "T1" });
    }
    if (targets?.base) {
      candleSeries.createPriceLine({ price: targets.base, color: "#4ade80", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "T2" });
    }
    if (targets?.aggressive) {
      candleSeries.createPriceLine({ price: targets.aggressive, color: "#22c55e", lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "T3 ★" });
    }

    chart.timeScale().fitContent();

    // Responsive resize
    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data, targets, height]);

  if (isLoading) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 10 }}>
        <div style={{ width: 32, height: 32, border: "3px solid rgba(59,130,246,0.3)", borderTopColor: "#3b82f6", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
        <span style={{ fontSize: 12, color: "#475569" }}>Loading chart…</span>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (error || !data || data.length === 0) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}>
        <span style={{ fontSize: 28 }}>📉</span>
        <span style={{ fontSize: 13, color: "#475569" }}>Could not load chart data</span>
      </div>
    );
  }

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
