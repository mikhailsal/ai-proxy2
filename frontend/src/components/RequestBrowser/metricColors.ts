import type { RequestSummary } from '../../types';

const NEUTRAL = '#8b949e';

function clamp(val: number, min: number, max: number): number {
  return Math.min(Math.max(val, min), max);
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * clamp(t, 0, 1);
}

function lerpColor(c1: [number, number, number], c2: [number, number, number], t: number): string {
  const r = Math.round(lerp(c1[0], c2[0], t));
  const g = Math.round(lerp(c1[1], c2[1], t));
  const b = Math.round(lerp(c1[2], c2[2], t));
  return `rgb(${r}, ${g}, ${b})`;
}

const COLD: [number, number, number] = [100, 160, 220];
const WARM: [number, number, number] = [220, 140, 80];
const HOT: [number, number, number] = [220, 100, 80];
const GREEN: [number, number, number] = [80, 200, 120];
const DIM: [number, number, number] = [139, 148, 158];

/**
 * TPS: higher = better (faster generation).
 * <15 = slow (warm/red), 15-50 = normal, >50 = fast (cool/blue).
 */
export function tpsColor(item: RequestSummary): string {
  const tokens = item.output_tokens;
  const ms = item.latency_ms;
  if (tokens == null || tokens === 0 || ms == null || ms <= 0) return NEUTRAL;
  const tps = tokens / (ms / 1000);
  if (tps < 15) return lerpColor(HOT, WARM, tps / 15);
  if (tps < 50) return NEUTRAL;
  return lerpColor(COLD, [100, 200, 230], clamp((tps - 50) / 50, 0, 1));
}

/**
 * Duration: shorter = better.
 * <1s fast (cool), 1-5s normal, >5s slow (warm), >15s hot.
 */
export function durationColor(latencyMs: number | null): string {
  if (latencyMs == null) return NEUTRAL;
  const s = latencyMs / 1000;
  if (s < 1) return lerpColor(COLD, DIM, s);
  if (s < 5) return NEUTRAL;
  if (s < 15) return lerpColor(WARM, HOT, (s - 5) / 10);
  return lerpColor(HOT, [200, 70, 70], clamp((s - 15) / 30, 0, 1));
}

/**
 * Cost: lower = better.
 * <$0.005 cheap (neutral), $0.005-$0.05 moderate, >$0.05 expensive (warm).
 */
export function costColor(cost: number | null): string {
  if (cost == null || cost === 0) return NEUTRAL;
  if (cost < 0.005) return NEUTRAL;
  if (cost < 0.05) return lerpColor(DIM, WARM, (cost - 0.005) / 0.045);
  return lerpColor(WARM, HOT, clamp((cost - 0.05) / 0.2, 0, 1));
}

/**
 * Cache ratio: higher = better utilization (green tint).
 * <10% = neutral, 10-100% = progressively green.
 */
export function cacheRatioColor(item: RequestSummary): string {
  const cached = item.cached_input_tokens;
  const input = item.input_tokens;
  if (cached == null || cached <= 0 || input == null || input <= 0) return NEUTRAL;
  const ratio = cached / input;
  if (ratio < 0.1) return NEUTRAL;
  return lerpColor(DIM, GREEN, ratio);
}

/**
 * Message count: higher = longer conversation (blue tint).
 * 1-2 = neutral, 3-8 = slight blue, >8 = stronger blue.
 */
export function messageCountColor(count: number | null): string {
  if (count == null) return NEUTRAL;
  if (count <= 2) return NEUTRAL;
  if (count <= 8) return lerpColor(DIM, COLD, (count - 2) / 6);
  return lerpColor(COLD, [80, 180, 240], clamp((count - 8) / 20, 0, 1));
}
