"use client";
import { useEffect, useRef } from "react";
import { createChart, ColorType, LineStyle, type IChartApi, type ISeriesApi, type CandlestickSeriesOptions } from "lightweight-charts";

interface OHLCVBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface TargetLines {
  stopLoss?: number;
  conservative?: number;
  base?: number;
  aggressive?: number;
}

interface Props {
  data: OHLCVBar[];
  targets?: TargetLines;
  height?: number;
}

export default function TradingViewChart({ data, targets, height = 420 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

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

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    candleSeries.setData(data);

    // Target price lines
    if (targets) {
      if (targets.stopLoss) {
        const sl = candleSeries.createPriceLine({
          price: targets.stopLoss,
          color: "#ef4444",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: "SL",
        });
      }
      if (targets.conservative) {
        candleSeries.createPriceLine({ price: targets.conservative, color: "#86efac", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "T1" });
      }
      if (targets.base) {
        candleSeries.createPriceLine({ price: targets.base, color: "#4ade80", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "T2" });
      }
      if (targets.aggressive) {
        candleSeries.createPriceLine({ price: targets.aggressive, color: "#16a34a", lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "T3 ⭐" });
      }
    }

    chart.timeScale().fitContent();

    // Resize observer
    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, [data, targets, height]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height, borderRadius: 12, overflow: "hidden" }}
    />
  );
}
