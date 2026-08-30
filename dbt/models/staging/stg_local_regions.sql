{#
    The other entity packed into raw.local_seed_data — see
    stg_local_categories.sql and sources.yml for why the split happens here
    rather than in the extractor.
#}
select
    region_id::int as region_id,
    region_name,
    source_file,
    source_modified::timestamptz as source_modified
from {{ source('raw', 'local_seed_data') }}
where region_id is not null
