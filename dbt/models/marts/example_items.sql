select
    item_id,
    item_name,
    item_name_length
from {{ ref('int_example_items') }}
