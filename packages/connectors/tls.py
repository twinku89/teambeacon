from __future__ import annotations

import ssl
from pathlib import Path


def create_ssl_context(ca_bundle_path: str | None = None) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not ca_bundle_path:
        return context

    expanded_path = Path(ca_bundle_path).expanduser()
    context.load_verify_locations(cafile=str(expanded_path))
    return context
