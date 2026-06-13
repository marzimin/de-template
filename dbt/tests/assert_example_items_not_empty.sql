-- Singular test: assert that the starter mart has at least one row.
-- dbt singular tests pass when the query returns zero rows (zero rows = no failures).
-- Copy and adapt this pattern for your own tables.

select 1
from {{ ref('example_items') }}
having count(*) = 0
