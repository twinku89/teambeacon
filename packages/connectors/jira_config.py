from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .interfaces import ConnectorConfig
from .jira_rest_stub import (
    DEFAULT_EPIC_LINK_FIELD,
    DEFAULT_SPRINT_FIELD_CANDIDATES,
    DEFAULT_STORY_POINTS_FIELD,
)

DEFAULT_ENV_PATHS = (Path("config/.env"), Path(".env"))


def load_env_files(paths: Iterable[Path] = DEFAULT_ENV_PATHS, override: bool = True) -> None:
    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if not key:
                continue
            if override or key not in os.environ:
                os.environ[key] = value


@dataclass
class JiraRuntimeConfig:
    base_url: str
    pat_token: str
    project_key: str | None
    board_id: int | None
    story_points_field: str
    epic_link_field: str = DEFAULT_EPIC_LINK_FIELD
    sprint_field_candidates: tuple[str, ...] = DEFAULT_SPRINT_FIELD_CANDIDATES
    auth_mode: str = "pat_bearer"
    username: str | None = None
    timeout_seconds: int = 30
    ca_bundle_path: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> JiraRuntimeConfig:
        source = dict(os.environ if env is None else env)

        missing = [name for name in ("JIRA_BASE_URL", "JIRA_PAT") if not source.get(name)]
        if missing:
            missing_csv = ", ".join(missing)
            raise ValueError(f"missing required environment variables: {missing_csv}")

        board_id_raw = source.get("JIRA_BOARD_ID")
        board_id = int(board_id_raw) if board_id_raw else None

        timeout_raw = source.get("JIRA_TIMEOUT_SECONDS", "30")
        timeout_seconds = int(timeout_raw)

        sprint_fields_value = source.get("JIRA_SPRINT_FIELDS", source.get("JIRA_SPRINT_FIELD"))
        if sprint_fields_value:
            parsed_candidates = tuple(
                segment.strip() for segment in sprint_fields_value.split(",") if segment.strip()
            )
            sprint_field_candidates = parsed_candidates or DEFAULT_SPRINT_FIELD_CANDIDATES
        else:
            sprint_field_candidates = DEFAULT_SPRINT_FIELD_CANDIDATES

        return cls(
            base_url=source["JIRA_BASE_URL"],
            pat_token=source["JIRA_PAT"],
            project_key=source.get("JIRA_PROJECT_KEY"),
            board_id=board_id,
            story_points_field=source.get("JIRA_STORY_POINTS_FIELD", DEFAULT_STORY_POINTS_FIELD),
            epic_link_field=source.get("JIRA_EPIC_LINK_FIELD", DEFAULT_EPIC_LINK_FIELD),
            sprint_field_candidates=sprint_field_candidates,
            auth_mode=source.get("JIRA_AUTH_MODE", "pat_bearer"),
            username=source.get("JIRA_USERNAME"),
            timeout_seconds=timeout_seconds,
            ca_bundle_path=source.get("JIRA_CA_BUNDLE") or source.get("ATLASSIAN_CA_BUNDLE"),
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
