from __future__ import annotations

from enum import Enum


class AdapterToolNamespace(Enum):
    NATIVE_PYTHON = "python"
    NATIVE_BROWSER = "browser"
    CUSTOM_DEVELOPER = "functions"


class AdapterToolType(Enum):
    PYTHON = "python"
    BROWSER = "browser"
    FUNCTION = "function"
    CUSTOM = "custom"
