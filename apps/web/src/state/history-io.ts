/** Import and export of the decision log (schema-validated, size-bounded). */
import { z } from "zod";
import { ACTIONS, MAX_IMPORT_BYTES, OUTCOMES, replaceAll, verify, type Entry } from "./history";

export const EntrySchema = z.object({
  id: z.string().max(80),
  at: z.string().max(40),
  case_id: z.string().max(40),
  title: z.string().max(200),
  entity: z.string().max(120),
  action: z.enum(ACTIONS),
  validator_outcome: z.enum(OUTCOMES),
  orders: z.array(z.number().finite().min(0).max(1e7)).length(3),
  expected_cost: z.number().finite().nullable(),
  cvar: z.number().finite().nullable(),
  assumptions: z.record(z.string(), z.union([z.number().finite(), z.boolean()])),
  note: z.string().max(500),
  simulated: z.literal(true),
  prev_hash: z.string().max(64),
  hash: z.string().max(64),
});
const LogSchema = z.object({ format: z.literal("edi-decision-log"), version: z.literal(1), entries: z.array(EntrySchema).max(2000) });

export function exportLog(entries: Entry[]): string {
  return JSON.stringify({ format: "edi-decision-log", version: 1, exported_at: new Date().toISOString(), entries }, null, 2);
}

export async function importLog(text: string): Promise<{ ok: true; count: number } | { ok: false; error: string }> {
  if (text.length > MAX_IMPORT_BYTES) return { ok: false, error: "File is larger than 1 MB." };
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return { ok: false, error: "File is not valid JSON." };
  }
  const parsed = LogSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: "File does not match the decision-log format (version 1)." };
  const v = await verify(parsed.data.entries);
  if (!v.ok) return { ok: false, error: `Hash chain breaks at entry ${(v.brokenAt ?? 0) + 1}; the file was edited or truncated.` };
  replaceAll(parsed.data.entries as Entry[]);
  return { ok: true, count: parsed.data.entries.length };
}

