select
    s.sale_id,
    s.category,
    c.category_id,
    s.amount,
    s.sale_date
from {{ ref('stg_local_monthly_sales') }} as s
left join {{ ref('stg_local_categories') }} as c
    on lower(s.category) = lower(c.category_name)
