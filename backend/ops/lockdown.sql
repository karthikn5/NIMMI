-- Close Supabase's public REST API (PostgREST) over Nimmi's tables.
--
-- Supabase publishes every table in the `public` schema at https://<project>.supabase.co/rest/v1/<table>,
-- readable with the publishable/anon key that ships in the website. Nimmi never uses that API for
-- its data (the backend connects to Postgres directly as the table owner), so:
--   1. turn on row level security for every table (no policies = no rows for anon/authenticated),
--   2. remove the anon/authenticated grants, now and for tables created later.
-- The backend is unaffected: the table owner bypasses RLS. Safe to run more than once.
-- Run in Supabase: SQL Editor -> New query -> paste -> Run.

do $$
declare t record;
begin
  for t in select schemaname, tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table %I.%I enable row level security', t.schemaname, t.tablename);
  end loop;
end $$;

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;

-- Check: every row should say rls_on = true.
select tablename, rowsecurity as rls_on from pg_tables where schemaname = 'public' order by tablename;
