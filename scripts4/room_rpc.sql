-- Key-gated access to fish_rooms, so the server never needs the service key.
--
-- Run after scripts4/room_schema.sql. Safe to run again.
--
-- WHY THIS EXISTS
-- ---------------
-- room_schema.sql keeps fish_rooms unreachable from every public key (RLS on,
-- no policies) and has the server bypass that with the SERVICE key. That works,
-- but the service key bypasses RLS on EVERY table in the project -- a far
-- bigger credential than "read and write game tables" -- and it cannot be read
-- back through Supabase's management API, so setting it up needs a person to
-- copy it by hand.
--
-- This gives the server exactly the four operations api/_rooms.py performs and
-- nothing else, each behind a key that only the server holds:
--
--     fish_store_create   insert a new room, refusing a code already taken
--     fish_store_read     one room by code
--     fish_store_write    compare-and-set on version
--     fish_store_lobbies  public tables still seating, newest first
--
-- They are SECURITY DEFINER so they can reach the RLS-locked table, and each
-- first checks its p_key against a SHA-256 hash in a schema PostgREST does not
-- expose. The plaintext key lives only in the deployment's environment
-- (FISH_DB_KEY); the database holds its hash. Called with the public key but no
-- p_key, or a wrong one, every function raises "denied" before touching a row.
--
-- The nonce in a room document derives all six hands, so the boundary that
-- matters is unchanged: no browser can read a room. Rotating the key is one
-- UPDATE of fish_private.store_key plus the environment variable.

create schema if not exists fish_private;
revoke all on schema fish_private from public;
revoke all on schema fish_private from anon, authenticated;

create table if not exists fish_private.store_key (
  id         integer primary key default 1 check (id = 1),
  key_sha256 text not null
);

create or replace function fish_private.key_ok(p_key text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select p_key is not null
     and length(p_key) >= 32
     and exists (select 1 from fish_private.store_key k
                  where k.key_sha256 = encode(sha256(convert_to(p_key, 'UTF8')), 'hex'));
$$;
revoke execute on function fish_private.key_ok(text) from public, anon, authenticated;

create or replace function public.fish_store_create(
  p_key text, p_code text, p_touched double precision, p_doc jsonb)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not fish_private.key_ok(p_key) then
    raise exception 'denied' using errcode = '42501';
  end if;
  insert into public.fish_rooms (code, version, touched, doc)
  values (p_code, 1, p_touched, p_doc)
  on conflict (code) do nothing;
  return found;
end;
$$;

create or replace function public.fish_store_read(p_key text, p_code text)
returns table (version integer, touched double precision, doc jsonb)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if not fish_private.key_ok(p_key) then
    raise exception 'denied' using errcode = '42501';
  end if;
  return query
    select r.version, r.touched, r.doc
      from public.fish_rooms r
     where r.code = p_code;
end;
$$;

create or replace function public.fish_store_write(
  p_key text, p_code text, p_version integer,
  p_touched double precision, p_doc jsonb)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not fish_private.key_ok(p_key) then
    raise exception 'denied' using errcode = '42501';
  end if;
  update public.fish_rooms
     set version = p_version + 1, touched = p_touched, doc = p_doc
   where code = p_code and version = p_version;
  return found;
end;
$$;

create or replace function public.fish_store_lobbies(
  p_key text, p_since double precision, p_limit integer)
returns table (code text, version integer, doc jsonb)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if not fish_private.key_ok(p_key) then
    raise exception 'denied' using errcode = '42501';
  end if;
  return query
    select r.code, r.version, r.doc
      from public.fish_rooms r
     where r.doc->>'kind' = 'table'
       and r.doc->>'public' = 'true'
       and r.doc->>'phase' = 'lobby'
       and r.touched > p_since
     order by r.touched desc
     limit least(greatest(coalesce(p_limit, 20), 1), 50);
end;
$$;

-- EXECUTE defaults to PUBLIC; make the grant explicit and minimal. Holding the
-- public key gets you as far as the key check and no further.
revoke execute on function public.fish_store_create(text, text, double precision, jsonb) from public;
revoke execute on function public.fish_store_read(text, text) from public;
revoke execute on function public.fish_store_write(text, text, integer, double precision, jsonb) from public;
revoke execute on function public.fish_store_lobbies(text, double precision, integer) from public;
grant execute on function public.fish_store_create(text, text, double precision, jsonb) to anon, authenticated;
grant execute on function public.fish_store_read(text, text) to anon, authenticated;
grant execute on function public.fish_store_write(text, text, integer, double precision, jsonb) to anon, authenticated;
grant execute on function public.fish_store_lobbies(text, double precision, integer) to anon, authenticated;

-- The key's hash is set separately, never committed:
--   insert into fish_private.store_key (id, key_sha256) values (1, '<sha256 hex>')
--   on conflict (id) do update set key_sha256 = excluded.key_sha256;
