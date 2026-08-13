"""Fail-closed, data-only adapter plugin SDK."""

from civicdecision.plugins.models import (
    PluginCapability,
    PluginManifest,
    PluginPackage,
    PluginPackageSummary,
)
from civicdecision.plugins.registry import (
    PluginRegistry,
    PluginValidationError,
    load_plugin_package,
)
from civicdecision.plugins.starter import scaffold_plugin

__all__ = [
    "PluginCapability",
    "PluginManifest",
    "PluginPackage",
    "PluginPackageSummary",
    "PluginRegistry",
    "PluginValidationError",
    "load_plugin_package",
    "scaffold_plugin",
]
