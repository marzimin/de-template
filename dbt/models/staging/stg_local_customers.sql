{#
    load_mode: replace, so raw.local_customers is already exactly one
    snapshot — no ranking/dedup needed, unlike stg_local_monthly_sales.
#}
select
    customer_id,
    customer_name,
    region,
    signup_date::date as signup_date,
    source_file,
    source_modified::timestamptz as source_modified
from {{ source('raw', 'local_customers') }}
