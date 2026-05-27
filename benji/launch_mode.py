"""Détection du mode de lancement : CLI overlay vs .app fenêtre principale."""

from __future__ import annotations

import os
import sys
from typing import Literal

Mode = Literal["window", "overlay"]


def launch_mode() -> Mode:
    """Renvoie 'window' si lancé comme app .app macOS, 'overlay' sinon.

    Override possible via la variable d'env BENJI_LAUNCH_MODE.
    """
    env = os.environ.get("BENJI_LAUNCH_MODE")
    if env in ("window", "overlay"):
        return env  # type: ignore[return-value]
    if ".app/Contents/MacOS/" in sys.executable:
        return "window"
    return "overlay"
