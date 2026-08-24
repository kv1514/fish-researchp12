-- Shared room state for the public table.
--
-- Run this once against the Postgres database that will hold rooms, then set
-- SUPABASE_URL and SUPABASE_SERVICE_KEY in the deployment's environment.
-- Without both, api/_rooms.py falls back to an in-process store: rooms then
-- work for exactly one player, which is visibly broken rather than silently
-- wrong, and /api/health reports room_backend="memory" so it is diagnosable.
--
-- WHY RLS IS ON WITH NO POLICIES
-- ------------------------------
-- Row-level security enabled and no policy granted means every anonymous and
-- authenticated request is denied. That is deliberate and it is the whole
-- security model: a room row holds the deal NONCE, and the nonce derives the
-- deal, so a client that can read the row can compute all six hands. The
-- project's anon key is public by design (it ships in the page), so the table
-- has to be unreachable with it.
--
-- The server reads and writes with the SERVICE key, which bypasses RLS and
-- lives only in the function's environment. Do not add a policy to "make it
-- work" from the browser; that is the failure this comment exists to prevent.

create table if not exists public.fish_rooms (
  code    text primary key,
  version integer          not null default 1,
  touched double precision not null default 0,
  doc     jsonb            not null
);

alter table public.fish_rooms enable row level security;

-- Reap abandoned tables. `touched` is wall-clock seconds, written by the
-- server on every mutation; api/_rooms.ROOM_TTL is the matching read-side
-- cutoff, so an expired room reads as absent even if this has not run yet.
create index if not exists fish_rooms_touched_idx
  on public.fish_rooms (touched);

-- Optional: schedule with pg_cron if available, or leave it to the read-side
-- TTL check. Kept as a function rather than a trigger because sweeping on
-- every write would make one player's move pay for everybody's cleanup.
--
-- SECURITY DEFINER plus the REVOKEs below, and both halves matter. DEFINER is
-- needed so the reaper can delete through the RLS that makes this table
-- unreachable -- but PostgREST exposes every function in `public` as
-- /rest/v1/rpc/<name>, and EXECUTE defaults to PUBLIC. As first written, this
-- function was callable by anyone holding the project's anon key, which is
-- public by design and ships in the page. With max_age = 0 that deletes every
-- room in the table: a reaper reachable by the same key the browser carries is
-- a delete button on every game in progress.
--
-- Supabase's own security advisor flagged it (lint 0028/0029). Verified after
-- the revoke: an anon-key call returns "permission denied for function
-- fish_rooms_sweep".
create or replace function public.fish_rooms_sweep(max_age double precision)
returns integer
language sql
security definer
set search_path = public
as $$
  with gone as (
    delete from public.fish_rooms
     where touched < (extract(epoch from now()) - max_age)
    returning 1
  )
  select coalesce(count(*), 0)::integer from gone;
$$;

-- The service key authenticates as service_role, which these revokes do not
-- touch, so the server keeps its reaper and nobody else gets one.
revoke execute on function public.fish_rooms_sweep(double precision) from public;
revoke execute on function public.fish_rooms_sweep(double precision) from anon;
revoke execute on function public.fish_rooms_sweep(double precision) from authenticated;
