-- FocusBuddy v5: satu dokumen state per akun. Semua akses client wajib
-- memakai JWT Supabase Auth; publishable key saja tidak bisa membaca row.
create table if not exists public.focusbuddy_states (
    user_id uuid primary key references auth.users(id) on delete cascade,
    state jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    constraint focusbuddy_state_is_object check (jsonb_typeof(state) = 'object')
);

alter table public.focusbuddy_states enable row level security;

drop policy if exists "focusbuddy_select_own_state" on public.focusbuddy_states;
create policy "focusbuddy_select_own_state"
on public.focusbuddy_states for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "focusbuddy_insert_own_state" on public.focusbuddy_states;
create policy "focusbuddy_insert_own_state"
on public.focusbuddy_states for insert to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "focusbuddy_update_own_state" on public.focusbuddy_states;
create policy "focusbuddy_update_own_state"
on public.focusbuddy_states for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "focusbuddy_delete_own_state" on public.focusbuddy_states;
create policy "focusbuddy_delete_own_state"
on public.focusbuddy_states for delete to authenticated
using ((select auth.uid()) = user_id);

create or replace function public.focusbuddy_set_updated_at()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists focusbuddy_states_updated_at on public.focusbuddy_states;
create trigger focusbuddy_states_updated_at
before update on public.focusbuddy_states
for each row execute function public.focusbuddy_set_updated_at();

grant select, insert, update, delete on public.focusbuddy_states to authenticated;
