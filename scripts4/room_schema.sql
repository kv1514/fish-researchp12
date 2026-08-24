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
