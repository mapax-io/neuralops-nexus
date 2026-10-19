-- NeuralOps portal — the claim-code table (device flow, Step 4's contract).
-- Paste into Supabase: Dashboard → SQL Editor → New query → Run.
--
-- SECURITY (owner's ruling 2026-10-18, "installer-only"): this table is
-- reachable ONLY by the edge functions (service role). RLS is enabled with
-- NO policies, so the anon key and signed-in users can never read or write
-- it directly — a signed-in user can only act through device-claim, which
-- demands the code from the install's own screen.

create table if not exists public.device_requests (
  id          uuid primary key default gen_random_uuid(),  -- the request_id: only the install knows it
  code        text not null,                               -- what the installer sees, e.g. 483-291
  server_url  text not null default '',                    -- which install asked (informational)
  status      text not null default 'pending',             -- pending | claimed | consumed | expired
  access_token text,                                       -- set at claim, handed to the install ONCE
  claimed_email text,                                      -- who claimed (informational)
  created_at  timestamptz not null default now(),
  expires_at  timestamptz not null default now() + interval '15 minutes'
);

-- Two different pending requests must never share a code.
create unique index if not exists device_requests_pending_code
  on public.device_requests (code) where (status = 'pending');

alter table public.device_requests enable row level security;
-- No policies on purpose: service-role-only access.

-- ---------------------------------------------------------------------------
-- phone-home (added 2026-10-18) — Step 6 ruling 5's collector table.
-- ONE value ever leaves a customer's server: its total token count, sent on
-- app open and app close. Each report is one row here; nothing else arrives.
-- Same security stance: RLS on, NO policies — only the phone-home edge
-- function (service role) can write, and nobody can read via the anon key.

create table if not exists public.phone_home_events (
  id            bigint generated always as identity primary key,
  install_token text not null,                       -- which install reported
  event         text not null check (event in ('open', 'close')),
  total_tokens  bigint not null check (total_tokens >= 0),
  received_at   timestamptz not null default now()
);

-- Fast "latest reports per install" lookups for the future portal dashboard.
create index if not exists phone_home_events_by_install
  on public.phone_home_events (install_token, received_at desc);

alter table public.phone_home_events enable row level security;
-- No policies on purpose: service-role-only access.
