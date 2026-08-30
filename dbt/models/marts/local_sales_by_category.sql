select
    category_id,
    category,
    date_trunc('month', sale_date) as sale_month,
    count(*) as num_sales,
    sum(amount) as total_amount,
    avg(amount) as avg_amount
from {{ ref('int_local_monthly_sales_enriched') }}
group by category_id, category, date_trunc('month', sale_date)
