{#
    One of two entities packed into raw.local_seed_data — see sources.yml for
    why. category_id is NULL on every row that came from seed_regions.xlsx,
    so filtering on it is what pulls just this entity out of the union.
#}
select
    category_id::int as category_id,
    category_name,
    source_file,
    source_modified::timestamptz as source_modified
from {{ source('raw', 'local_seed_data') }}
where category_id is not null
