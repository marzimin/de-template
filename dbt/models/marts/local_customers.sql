select
    customer_id,
    customer_name,
    region,
    signup_date
from {{ ref('stg_local_customers') }}
