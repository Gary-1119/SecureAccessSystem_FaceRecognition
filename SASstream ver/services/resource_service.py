from __future__ import annotations

import os
import sys
from pathlib import Path


def app_resource_path(*parts: str) -> str:
    """Resolve bundled/static app resources for source and PyInstaller builds."""
    module_dir = Path(__file__).resolve().parent.parent
    candidates = [module_dir.joinpath(*parts)]

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        bundle = Path(str(bundle_dir))
        candidates.append(bundle.joinpath(*parts))
        candidates.append(bundle.joinpath("sas_dashboard_modular", *parts))

    cwd = Path(os.getcwd())
    candidates.append(cwd.joinpath(*parts))
    candidates.append(cwd.joinpath("sas_dashboard_modular", *parts))

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(module_dir.joinpath(*parts))
