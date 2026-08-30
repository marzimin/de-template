{#
    load_mode: append, and extractors.files.local_excel:LocalMonthlySalesExtractor
    re-reads every monthly_sales_*.xlsx file present on every run, not just
    new ones — so a rerun re-appends rows already in raw.local_monthly_sales.
    Keep the newest copy per sale_id rather than trusting the raw table to
    hold each row once; see docs/pipelines.md "Load modes, and idempotency".
#}
with ranked as (
    select
        *,
        row_number() over (
            partition by sale_id
            order by source_modified desc
        ) as row_num
    from {{ source('raw', 'local_monthly_sales') }}
)
select
    sale_id,
    category,
    amount::numeric as amount,
    sale_date::date as sale_date,
    source_file,
    source_modified::timestamptz as source_modified
from ranked
where row_num = 1
