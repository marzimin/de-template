{#
    Starter staging model with a hard-coded row so `dbt build` works on a fresh
    clone before any data has landed. Replace the SELECT below with a real query
    against your raw table once the pipeline has loaded data, e.g.:

        select
            id          as item_id,
            trim(name)  as item_name
        from {{ source('raw', 'example_items') }}

    (define the `raw` source in a schema.yml `sources:` block first).

    DEDUPLICATION. The loader appends by default, so re-running a pipeline
    loads the same rows again. Keep the newest row per key here rather than
    truncating the raw table — raw keeps the history, and the choice of which
    row wins stays visible in SQL:

        with ranked as (
            select
                *,
                row_number() over (
                    partition by id
                    order by updated_at desc
                ) as row_num
            from {{ source('raw', 'example_items') }}
        )
        select id as item_id, trim(name) as item_name
        from ranked
        where row_num = 1

    Set `load_mode: replace` in cfg/config.yaml instead when the source is
    small enough to re-fetch in full and you want a snapshot, not a history.

    This text is a Jinja comment, so the source() references above are NOT
    evaluated by dbt.
#}
select
    1 as item_id,
    'example' as item_name
