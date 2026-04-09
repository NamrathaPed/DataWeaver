/// <reference types="vite/client" />
import { createClient } from "@supabase/supabase-js";

const url = (import.meta as unknown as { env: Record<string, string> }).env.VITE_SUPABASE_URL ?? "";
const key = (import.meta as unknown as { env: Record<string, string> }).env.VITE_SUPABASE_ANON_KEY ?? "";

export const supabase = url && key ? createClient(url, key) : null;
export const supabaseEnabled = Boolean(url && key);
