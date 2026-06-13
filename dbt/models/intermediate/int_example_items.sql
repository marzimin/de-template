select
    item_id,
    item_name,
    length(item_name) as item_name_length
from {{ ref('stg_example_items') }}
