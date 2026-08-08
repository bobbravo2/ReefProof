"""Local observability API with an import-lazy application factory."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reefproof.api.app import create_app as create_app

__all__ = ["create_app"]


def __getattr__(name: str):
    if name != "create_app":
        raise AttributeError(name)
    value = import_module("reefproof.api.app").create_app
    globals()[name] = value
    return value
