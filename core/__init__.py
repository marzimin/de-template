"""Cross-cutting concerns shared by the extract, load, and export layers.

Kept deliberately small and dependency-light: paths, YAML configuration, and
the warehouse connection. Anything domain-specific belongs in ``extractors/``,
``loaders/``, or ``exporters/``.
"""
