-- Removes the new public-work and attempt guards, not account/provider/quota history.
begin;
drop function if exists public.muse_reserve_public_work(text,text,integer,text);
drop table if exists muse_private.public_work_reservations;
do $$ begin
    if to_regprocedure('muse_private.begin_operation_before_abuse(uuid,text,uuid,uuid)') is not null then
        drop function if exists public.muse_begin_operation(uuid,text,uuid,uuid);
        alter function muse_private.begin_operation_before_abuse(uuid,text,uuid,uuid)
            rename to muse_begin_operation;
        alter function muse_private.muse_begin_operation(uuid,text,uuid,uuid) set schema public;
    end if;
    if to_regprocedure('muse_private.reserve_provider_before_abuse(uuid,text,bigint,text,uuid)') is not null then
        drop function if exists public.muse_reserve_provider(uuid,text,bigint,text,uuid);
        alter function muse_private.reserve_provider_before_abuse(uuid,text,bigint,text,uuid)
            rename to muse_reserve_provider;
        alter function muse_private.muse_reserve_provider(uuid,text,bigint,text,uuid) set schema public;
    end if;
end $$;
revoke all on function public.muse_reserve_provider(uuid,text,bigint,text,uuid) from public,anon,authenticated;
grant execute on function public.muse_reserve_provider(uuid,text,bigint,text,uuid) to service_role;
revoke all on function public.muse_begin_operation(uuid,text,uuid,uuid) from public,anon,authenticated;
grant execute on function public.muse_begin_operation(uuid,text,uuid,uuid) to service_role;
drop index if exists muse_private.muse_operations_created_abuse;
drop index if exists muse_private.muse_provider_created_abuse;
commit;
