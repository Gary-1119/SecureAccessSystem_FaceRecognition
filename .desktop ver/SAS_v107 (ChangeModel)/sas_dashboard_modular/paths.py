from __future__ import annotations

import os
import sys


def app_resource_path(*parts: str) -> str:
    """Resolve bundled/static app resources for source and PyInstaller builds."""
    candidates: list[str] = []
    module_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(module_dir, *parts))

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(os.path.join(bundle_dir, *parts))
        candidates.append(os.path.join(bundle_dir, "sas_dashboard_modular", *parts))

    candidates.append(os.path.join(os.getcwd(), *parts))
    candidates.append(os.path.join(os.getcwd(), "sas_dashboard_modular", *parts))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return os.path.join(module_dir, *parts)
