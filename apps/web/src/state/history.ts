/**
 * Browser-local decision log. Entries are hash-chained (SHA-256 over the previous hash and the entry),
 * which detects accidental edits or truncation. It is a demonstration: localStorage is not tamper-proof,
 * not shared and not a system of record.
 */
import { useSyncExternalStore } from "react";

const KEY = "edi.decision-log.v1";
export const MAX_IMPORT_BYTES = 1_000_000;

export const ACTIONS = ["approved", "escalated", "count requested", "rejected", "deferred", "scenario saved"] as const;
export const OUTCOMES = ["recommend", "investigate", "defer", "escalate", "reject"] as const;

export interface Entry {
  id: string;
  at: string;
  case_id: string;
  title: string;
  entity: string;
  action: (typeof ACTIONS)[number];
  validator_outcome: (typeof OUTCOMES)[number];
  orders: number[];
  expected_cost: number | null;
  cvar: number | null;
  assumptions: Record<string, number | boolean>;
  note: string;
  simulated: true;
  prev_hash: string;
  hash: string;
}

/** Light structural check for stored entries (full schema validation happens on import). */
export function isEntry(x: unknown): x is Entry {
  if (!x || typeof x !== "object") return false;
  const e = x as Record<string, unknown>;
  const str = (k: string, max: number) => typeof e[k] === "string" && (e[k] as string).length <= max;
  return str("id", 80) && str("at", 40) && str("case_id", 40) && str("title", 200) && str("entity", 120) && str("note", 500)
    && str("prev_hash", 64) && str("hash", 64) && e.simulated === true
    && (ACTIONS as readonly string[]).includes(e.action as string) && (OUTCOMES as readonly string[]).includes(e.validator_outcome as string)
    && Array.isArray(e.orders) && e.orders.length === 3 && e.orders.every((v) => typeof v === "number" && Number.isFinite(v) && v >= 0)
    && (e.expected_cost === null || typeof e.expected_cost === "number") && (e.cvar === null || typeof e.cvar === "number")
    && typeof e.assumptions === "object" && e.assumptions !== null;
}

let listeners: (() => void)[] = [];
let snapshot: Entry[] = read();

function read(): Entry[] {
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(KEY) : null;
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.every(isEntry) ? parsed : [];
  } catch {
    return [];
  }
}

function write(entries: Entry[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries));
  } catch {
    /* storage unavailable or full: keep the in-memory copy */
  }
  snapshot = entries;
  listeners.forEach((l) => l());
}

export function useLog(): Entry[] {
  return useSyncExternalStore(
    (cb) => {
      listeners.push(cb);
      return () => {
        listeners = listeners.filter((l) => l !== cb);
      };
    },
    () => snapshot,
    () => snapshot,
  );
}

async function sha256(text: string): Promise<string> {
  if (!globalThis.crypto?.subtle) return "unavailable";
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

function canonical(e: Omit<Entry, "hash">): string {
  const { prev_hash, ...rest } = e;
  return prev_hash + "|" + JSON.stringify(rest, Object.keys(rest).sort());
}

export async function append(e: Omit<Entry, "id" | "at" | "prev_hash" | "hash" | "simulated">): Promise<Entry> {
  const prev = snapshot.length ? snapshot[snapshot.length - 1].hash : "genesis";
  const base = { ...e, id: `rec-${Date.now().toString(36)}-${snapshot.length + 1}`, at: new Date().toISOString(), simulated: true as const, prev_hash: prev };
  const entry: Entry = { ...base, hash: await sha256(canonical(base)) };
  write([...snapshot, entry]);
  return entry;
}

export async function verify(entries: Entry[]): Promise<{ ok: boolean; brokenAt: number | null }> {
  let prev = "genesis";
  for (let i = 0; i < entries.length; i++) {
    const { hash, ...rest } = entries[i];
    if (rest.prev_hash !== prev || (await sha256(canonical(rest))) !== hash) return { ok: false, brokenAt: i };
    prev = hash;
  }
  return { ok: true, brokenAt: null };
}

export function resetLog(): void {
  write([]);
}

export function replaceAll(entries: Entry[]): void {
  write(entries);
}

export const _setForTests = replaceAll;
