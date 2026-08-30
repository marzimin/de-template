{#
    load_mode: replace, so raw.local_latest_orders is already exactly one
    snapshot — no ranking/dedup needed, unlike stg_local_monthly_sales.
#}
select
    order_id,
    customer_name,
    category,
    amount::numeric as amount,
    order_date::date as order_date,
    source_file,
    source_modified::timestamptz as source_modified
from {{ source('raw', 'local_latest_orders') }}
