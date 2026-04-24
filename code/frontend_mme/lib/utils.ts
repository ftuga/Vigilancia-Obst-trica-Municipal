import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Heurística: el bootstrap CI degenerado (ci_low == ci_high) significa que el
 * champion no tiene residuals.npy adjunto. Se reporta como "no disponible".
 */
export function isCIAvailable(ci_low: number, ci_high: number): boolean {
  return Math.abs(ci_high - ci_low) > 1e-6;
}
