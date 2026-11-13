-- Player profiles, behind the same key gate as the rooms.
--
-- Run after scripts4/room_rpc.sql (it reuses fish_private.key_ok). Safe to
-- run again.
--
-- A profile document holds a SHA-256 of the player's secret, their rating and
-- record, and their fair-play tallies. Like fish_rooms, the table has RLS on
-- and NO policies, so no browser key can read it; the server reaches it only
-- through these SECURITY DEFINER functions, each of which checks FISH_DB_KEY
-- first. Unlike fish_rooms it is NOT swept: a profile lasts until its owner
-- deletes it (App Review Guideline 5.1.1(v)) or it is closed for fair play.
--
-- The indexed columns (rating, games, listed, review, touched) are computed
-- by the server from the document on every write -- see columns() in
-- api/_profiles.py -- so the leaderboard and the review queue are index scans
-- rather than reads of every document.

create table if not exists public.fish_profiles (
  id       text primary key check (id ~ '^[a-z0-9]{6,16}$'),
  version  integer not null default 1,
  rating   double precision not null default 1500,
  games    integer not null default 0,
  listed   boolean not null default false,
  review   boolean not null default false,
  touched  double precision not null default 0,
  doc      jsonb not null
);
alter table public.fish_profiles enable row level security;
revoke all on table public.fish_profiles from anon, authenticated;

create index if not exists fish_profiles_board_idx
  on public.fish_profiles (rating desc) where listed;
create index if not exists fish_profiles_review_idx
  on public.fish_profiles (touched desc) where review;

create or replace function public.fish_profile_create(
  p_key text, p_id text, p_doc jsonb, p_rating double precision,
  p_games integer, p_listed boolean, p_review boolean,
  p_touched double precision)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not fish_private.key_ok(p_key) then
    raise exception 'denied' using errcode = '42501';
  end if;
  insert into public.fish_profiles
    (id, version, rating, games, listed, review, touched, doc)
  values (p_id, 1, p_rating, p_games, p_listed, p_review, p_touched, p_doc)
  on conflict (id) do nothing;
  return found;
end;
$$;

create or replace function public.fish_profile_read(p_key text, p_id text)
returns table (version integer, doc jsonb)
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
    select p.version, p.doc from public.fish_profiles p where p.id = p_id;
end;
$$;

create or replace function public.fish_profile_write(
  p_key text, p_id text, p_version integer, p_doc jsonb,
  p_rating double precision, p_games integer, p_listed boolean,
  p_review boolean, p_touched double precision)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not fish_private.key_ok(p_key) then
    raise exception 'denied' using errcode = '42501';
  end if;
  update public.fish_profiles
     set version = p_version + 1, doc = p_doc, rating = p_rating,
         games = p_games, listed = p_listed, review = p_review,
         touched = p_touched
   where id = p_id and version = p_version;
  return found;
end;
$$;

create or replace function public.fish_profile_delete(p_key text, p_id text)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not fish_private.key_ok(p_key) then
    raise exception 'denied' using errcode = '42501';
  end if;
  delete from public.fish_profiles where id = p_id;
  return found;
end;
$$;

create or replace function public.fish_profile_top(p_key text, p_limit integer)
returns table (doc jsonb)
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
    select p.doc from public.fish_profiles p
     where p.listed
     order by p.rating desc
     limit least(greatest(p_limit, 1), 100);
end;
$$;

create or replace function public.fish_profile_review(p_key text, p_limit integer)
returns table (doc jsonb)
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
    select p.doc from public.fish_profiles p
     where p.review
     order by p.touched desc
     limit least(greatest(p_limit, 1), 100);
end;
$$;

create or replace function public.fish_profile_rank(
  p_key text, p_rating double precision)
returns integer
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if not fish_private.key_ok(p_key) then
    raise exception 'denied' using errcode = '42501';
  end if;
  return (select count(*)::integer from public.fish_profiles p
           where p.listed and p.rating > p_rating);
end;
$$;

revoke execute on function public.fish_profile_create(text, text, jsonb, double precision, integer, boolean, boolean, double precision) from public;
revoke execute on function public.fish_profile_read(text, text) from public;
revoke execute on function public.fish_profile_write(text, text, integer, jsonb, double precision, integer, boolean, boolean, double precision) from public;
revoke execute on function public.fish_profile_delete(text, text) from public;
revoke execute on function public.fish_profile_top(text, integer) from public;
revoke execute on function public.fish_profile_review(text, integer) from public;
revoke execute on function public.fish_profile_rank(text, double precision) from public;
grant execute on function public.fish_profile_create(text, text, jsonb, double precision, integer, boolean, boolean, double precision) to anon, authenticated;
grant execute on function public.fish_profile_read(text, text) to anon, authenticated;
grant execute on function public.fish_profile_write(text, text, integer, jsonb, double precision, integer, boolean, boolean, double precision) to anon, authenticated;
grant execute on function public.fish_profile_delete(text, text) to anon, authenticated;
grant execute on function public.fish_profile_top(text, integer) to anon, authenticated;
grant execute on function public.fish_profile_review(text, integer) to anon, authenticated;
grant execute on function public.fish_profile_rank(text, double precision) to anon, authenticated;

-- Account deletion (App Review Guideline 5.1.1(v)): deleting a profile in the
-- app also deletes the Supabase Auth user behind it -- email, phone and every
-- sign-in identity -- which the publishable key alone cannot do. Same key gate
-- as everything above; the server calls it only for the account whose own
-- device secret it has just checked (api/_profiles.py, delete()).
create or replace function public.fish_auth_delete(p_key text, p_uid uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not fish_private.key_ok(p_key) then
    raise exception 'denied' using errcode = '42501';
  end if;
  delete from auth.users where id = p_uid;
  return found;
end;
$$;
revoke execute on function public.fish_auth_delete(text, uuid) from public;
grant execute on function public.fish_auth_delete(text, uuid) to anon, authenticated;
