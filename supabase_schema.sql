-- DataWeaver Supabase Schema
-- Run this in the Supabase SQL Editor (supabase.com → your project → SQL Editor)

-- 1. uploads table (may already exist — skip if so)
CREATE TABLE IF NOT EXISTS public.uploads (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  text NOT NULL,
    filename    text NOT NULL,
    file_hash   text NOT NULL,
    extension   text NOT NULL,
    row_count   int,
    col_count   int,
    size_kb     float,
    created_at  timestamptz DEFAULT now()
);

-- 2. session_state table (NEW — stores EDA, charts, and insights as JSON)
CREATE TABLE IF NOT EXISTS public.session_state (
    session_id    text PRIMARY KEY,
    eda_result    jsonb,
    chart_cache   jsonb,
    insight_cache jsonb,
    updated_at    timestamptz DEFAULT now()
);

-- 3. chat_messages table (may already exist — skip if so)
CREATE TABLE IF NOT EXISTS public.chat_messages (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  text NOT NULL,
    role        text NOT NULL CHECK (role IN ('user', 'assistant')),
    content     text NOT NULL,
    created_at  timestamptz DEFAULT now()
);

-- 4. Row Level Security — needed if you use the anon key (default)
--    Skip this block if you use the service_role key instead.

ALTER TABLE public.uploads       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.session_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- Allow full access for anon key (backend is the only writer; no user auth yet)
CREATE POLICY "anon_all" ON public.uploads       FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON public.session_state FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON public.chat_messages FOR ALL TO anon USING (true) WITH CHECK (true);

-- 5. Storage bucket
--    Go to: Supabase Dashboard → Storage → New bucket
--    Name:  session-files
--    Public: NO (keep private)
--
--    Then add this storage policy so the backend can read/write:
--    Dashboard → Storage → session-files → Policies → New policy → "Full access for all"
--    Or run:

INSERT INTO storage.buckets (id, name, public)
VALUES ('session-files', 'session-files', false)
ON CONFLICT (id) DO NOTHING;

CREATE POLICY "backend_all" ON storage.objects
FOR ALL TO anon
USING (bucket_id = 'session-files')
WITH CHECK (bucket_id = 'session-files');
