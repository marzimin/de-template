{#
    Use the model's `+schema:` value as the literal schema name.

    dbt's built-in behaviour concatenates the target schema with the custom
    schema (e.g. target `staging` + custom `marts` -> `staging_marts`). That
    surprises newcomers and would not match the `raw` / `staging` / `marts`
    schemas created in docker/postgres/init.sh. This override makes a model
    with `+schema: marts` land in exactly the `marts` schema.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema | trim }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
