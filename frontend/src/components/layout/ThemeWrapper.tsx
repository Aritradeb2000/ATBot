"use client";
import ThemeProvider from "./ThemeProvider";

export default function ThemeWrapper({ children }: { children: React.ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}
