{#
    Starter staging model with a hard-coded row so `dbt build` works on a fresh
    clone before any data has landed. Replace the SELECT below with a real query
    against your raw table once the pipeline has loaded data, e.g.:

        select
            id          as item_id,
            trim(name)  as item_name
        from {{ source('raw', 'example_items') }}

    (define the `raw` source in a schema.yml `sources:` block first). This text is
    a Jinja comment, so the source() reference above is NOT evaluated by dbt.
#}
select
    1 as item_id,
    'example' as item_name
