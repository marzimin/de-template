"""Resolve ``module:ClassName`` strings from configuration into real objects.

Lets ``cfg/config.yaml`` name an extractor without this package importing every
extractor, so adding a source stays a configuration change.
"""

import importlib
from typing import Any


def import_from_path(path: str) -> Any:
    """Import an object named as ``module.path:AttributeName``.

    Args:
        path: A ``module:attribute`` reference, e.g.
            ``"extractors.api.example_api:ExampleApiExtractor"``.

    Returns:
        The named attribute.

    Raises:
        ValueError: If the reference is not in ``module:attribute`` form.
        ImportError: If the module cannot be imported, or has no such attribute.
    """
    module_name, separator, attribute_name = path.partition(":")
    if not separator or not module_name or not attribute_name:
        raise ValueError(
            f"Invalid import path {path!r}. Use 'module.path:AttributeName', "
            "e.g. 'extractors.api.example_api:ExampleApiExtractor'."
        )

    module = importlib.import_module(module_name)
    try:
        return getattr(module, attribute_name)
    except AttributeError as exc:
        raise ImportError(
            f"Module {module_name!r} has no attribute {attribute_name!r}."
        ) from exc
