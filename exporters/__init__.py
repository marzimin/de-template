"""Warehouse → file exporters.

The third peer of ``extractors/`` (source → records) and ``loaders/`` (records →
warehouse). This layer closes the loop: warehouse → file, so that any
downstream consumer that doesn't speak SQL can pick the data up — the
reference example this is built and tested against is ds-template, but the
exporter itself has no idea what reads the file. See ``docs/handoff.md``.
"""
