"""Warehouse → file exporters.

The third peer of ``extractors/`` (source → records) and ``loaders/`` (records →
warehouse). This layer closes the loop: warehouse → file, so that downstream
consumers which do not speak SQL — notably ds-template-local — can pick the data
up. See ``docs/handoff.md``.
"""
