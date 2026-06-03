"use client";
import { motion, useAnimationFrame } from "framer-motion";
import { useRef, useState } from "react";

interface Props {
  score: number;
  label: string;
  size?: number;
}

function scoreToColor(score: number) {
  if (score >= 70) return "#22c55e";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

export default function ScoreGauge({ score, label, size = 120 }: Props) {
  const clampedScore = Math.max(0, Math.min(100, score));
  const color = scoreToColor(clampedScore);

  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  // We only use 270° of the circle (¾)
  const arcLength = circumference * 0.75;
  const offset = arcLength - (clampedScore / 100) * arcLength;

  const cx = size / 2;
  const cy = size / 2;

  return (
    <div className="flex flex-col items-center gap-2">
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: "rotate(135deg)" }}>
          {/* Track */}
          <circle
            cx={cx} cy={cy} r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={8}
            strokeDasharray={`${arcLength} ${circumference}`}
            strokeLinecap="round"
          />
          {/* Animated fill */}
          <motion.circle
            cx={cx} cy={cy} r={radius}
            fill="none"
            stroke={color}
            strokeWidth={8}
            strokeLinecap="round"
            strokeDasharray={`${arcLength} ${circumference}`}
            initial={{ strokeDashoffset: arcLength }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1.2, ease: "easeOut" }}
            style={{ filter: `drop-shadow(0 0 6px ${color})` }}
          />
        </svg>
        {/* Center score text */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <motion.span
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.5, duration: 0.4 }}
            style={{ fontSize: size * 0.22, fontWeight: 700, color, lineHeight: 1 }}
          >
            {Math.round(clampedScore)}
          </motion.span>
          <span style={{ fontSize: size * 0.1, color: "#64748b", fontWeight: 500 }}>/ 100</span>
        </div>
      </div>
      <span style={{ fontSize: 12, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {label}
      </span>
    </div>
  );
}
