import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** 2026-07-05T04:10:44.011107Z → "2026-07-05 04:10:44 UTC" */
export function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`
  );
}

/** Seconds → "3d 4h", "2h 15m", "45m", "30s" — supervisory timeliness display. */
export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

/** "sha256:29356fff…cf0d" → abbreviated hash for table cells. */
export function abbreviateHash(hash: string, chars = 8): string {
  const [alg, hex] = hash.split(":");
  if (!hex) return hash;
  return `${alg}:${hex.slice(0, chars)}…${hex.slice(-4)}`;
}
