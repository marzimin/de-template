-- Singular test: assert that raw.example_items has been loaded with at least one row.
-- dbt singular tests pass when the query returns zero rows (zero rows = no failures).
-- Copy and adapt this pattern for your own tables.

select 1
from raw.example_items
having count(*) = 0
