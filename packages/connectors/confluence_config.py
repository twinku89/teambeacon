from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from .interfaces import ConnectorConfig


@dataclass
class ConfluenceRuntimeConfig:
    base_url: str
    pat_token: str
    auth_mode: str = "pat_bearer"
    username: str | None = None
    timeout_seconds: int = 30
    ca_bundle_path: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ConfluenceRuntimeConfig:
        source = dict(os.environ if env is None else env)
        missing = [name for name in ("CONFLUENCE_BASE_URL", "CONFLUENCE_PAT") if not source.get(name)]
        if missing:
            missing_csv = ", ".join(missing)
            raise ValueError(f"missing required environment variables: {missing_csv}")

        return cls(
            base_url=source["CONFLUENCE_BASE_URL"],
            pat_token=source["CONFLUENCE_PAT"],
            auth_mode=source.get("CONFLUENCE_AUTH_MODE", "pat_bearer"),
            username=source.get("CONFLUENCE_USERNAME"),
            timeout_seconds=int(source.get("CONFLUENCE_TIMEOUT_SECONDS", "30")),
            ca_bundle_path=source.get("CONFLUENCE_CA_BUNDLE") or source.get("ATLASSIAN_CA_BUNDLE"),
        )

    def to_connector_config(self) -> ConnectorConfig:
        return ConnectorConfig(
            base_url=self.base_url,
            pat_token=self.pat_token,
            auth_mode=self.auth_mode,
            username=self.username,
            timeout_seconds=self.timeout_seconds,
            ca_bundle_path=self.ca_bundle_path,
        )
