-- SOURCE ONLY. Execute only under a separately authorized Danger Room run.
begin;
select pg_catalog.current_setting('session_replication_role') as pre_role;
set local session_replication_role=replica;
select pg_catalog.current_setting('session_replication_role') as in_tx_role;
rollback;
select pg_catalog.current_setting('session_replication_role') as post_role;
