from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .interfaces import ConnectorConfig, JiraConnector
from .models import (
    BoardRecord,
    ChangelogItemRecord,
    IssueRecord,
    JiraProjectVersionRecord,
    JiraVersionRef,
    SprintRecord,
    SyncBatch,
)
from .tls import create_ssl_context

DEFAULT_STORY_POINTS_FIELD = "customfield_10016"
DEFAULT_EPIC_LINK_FIELD = "customfield_10014"
DEFAULT_SPRINT_FIELD_CANDIDATES = ("sprint", "customfield_10901", "customfield_10020")


class JiraAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _parse_jira_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_jira_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return _parse_jira_datetime(value)
    return parsed.replace(tzinfo=timezone.utc)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


class JiraRestConnector(JiraConnector):
    """
    Hosted JIRA REST connector.

    Target APIs:
    - /rest/api/2/search
    - /rest/api/2/issue/{key}?expand=changelog
    - /rest/agile/1.0/board
    - /rest/agile/1.0/board/{id}/sprint
    """

    def __init__(
        self,
        config: ConnectorConfig,
        project_key: str | None = None,
        story_points_field: str = DEFAULT_STORY_POINTS_FIELD,
        epic_link_field: str = DEFAULT_EPIC_LINK_FIELD,
        sprint_field_candidates: tuple[str, ...] = DEFAULT_SPRINT_FIELD_CANDIDATES,
    ) -> None:
        self.config = config
        self.project_key = project_key
        self.story_points_field = story_points_field
        self.epic_link_field = epic_link_field
        self.sprint_field_candidates = self._normalize_sprint_field_candidates(sprint_field_candidates)

    @staticmethod
    def _normalize_sprint_field_candidates(candidates: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for candidate in candidates:
            trimmed = candidate.strip()
            if not trimmed:
                continue
            if trimmed not in normalized:
                normalized.append(trimmed)
        if not normalized:
            return DEFAULT_SPRINT_FIELD_CANDIDATES
        return tuple(normalized)

    def _build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        base = self.config.base_url.rstrip("/")
        url = f"{base}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params, doseq=True)}"
        return url

    def _auth_headers(self) -> dict[str, str]:
        if self.config.auth_mode == "pat_bearer":
            return {"Authorization": f"Bearer {self.config.pat_token}"}
        if self.config.auth_mode == "basic":
            if not self.config.username:
                raise ValueError("username is required for basic auth")
            auth_blob = f"{self.config.username}:{self.config.pat_token}".encode("utf-8")
            encoded = base64.b64encode(auth_blob).decode("ascii")
            return {"Authorization": f"Basic {encoded}"}
        raise ValueError(f"unsupported auth_mode: {self.config.auth_mode}")

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._build_url(path, params)
        headers = {"Accept": "application/json", **self._auth_headers()}
        request = Request(url=url, headers=headers, method="GET")
        ssl_context = create_ssl_context(self.config.ca_bundle_path)
        try:
            with urlopen(request, timeout=self.config.timeout_seconds, context=ssl_context) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise JiraAPIError(
                f"JIRA request failed with HTTP {exc.code}: {path}",
                status_code=exc.code,
                body=body,
            ) from exc
        except URLError as exc:
            raise JiraAPIError(f"JIRA request failed for {path}: {exc}") from exc

        if not raw:
            return {}
        try:
            payload: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JiraAPIError(f"JIRA response was not valid JSON for {path}") from exc
        return payload

    def _extract_sprint_details(self, fields: dict[str, Any]) -> tuple[int | None, bool]:
        for field_name in self.sprint_field_candidates:
            if field_name not in fields:
                continue
            candidate = fields.get(field_name)

            if candidate is None:
                return (None, True)

            if isinstance(candidate, dict):
                sprint_id = candidate.get("id")
                if isinstance(sprint_id, int):
                    return (sprint_id, True)
                if isinstance(sprint_id, str) and sprint_id.isdigit():
                    return (int(sprint_id), True)
                return (None, True)

            if isinstance(candidate, list):
                for entry in reversed(candidate):
                    if isinstance(entry, dict):
                        sprint_id = entry.get("id")
                        if isinstance(sprint_id, int):
                            return (sprint_id, True)
                        if isinstance(sprint_id, str) and sprint_id.isdigit():
                            return (int(sprint_id), True)
                    if isinstance(entry, str):
                        match = re.search(r"id=(\d+)", entry)
                        if match:
                            return (int(match.group(1)), True)
                return (None, True)

            if isinstance(candidate, str):
                match = re.search(r"id=(\d+)", candidate)
                if match:
                    return (int(match.group(1)), True)
                return (None, True)

            return (None, True)

        return (None, False)

    def _extract_sprint_id(self, fields: dict[str, Any]) -> int | None:
        sprint_id, _ = self._extract_sprint_details(fields)
        return sprint_id

    def _extract_epic_key(self, fields: dict[str, Any]) -> str | None:
        epic_value = fields.get(self.epic_link_field)
        if isinstance(epic_value, str) and epic_value:
            return epic_value
        if isinstance(epic_value, dict):
            key = epic_value.get("key")
            if isinstance(key, str) and key:
                return key

        parent = fields.get("parent")
        if isinstance(parent, dict):
            parent_key = parent.get("key")
            if isinstance(parent_key, str) and parent_key:
                return parent_key
        return None

    @staticmethod
    def _extract_parent_issue_key(fields: dict[str, Any]) -> str | None:
        parent = fields.get("parent")
        if not isinstance(parent, dict):
            return None
        parent_key = parent.get("key")
        if isinstance(parent_key, str) and parent_key:
            return parent_key
        return None

    @staticmethod
    def _map_fix_version(raw_version: dict[str, Any]) -> JiraVersionRef | None:
        version_id_raw = raw_version.get("id")
        name = raw_version.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        version_id = str(version_id_raw).strip() if version_id_raw is not None else name.strip()
        if not version_id:
            version_id = name.strip()
        return JiraVersionRef(
            version_id=version_id,
            name=name.strip(),
            archived=bool(raw_version.get("archived")),
            released=bool(raw_version.get("released")),
            release_date=_parse_jira_date(raw_version.get("releaseDate")),
            raw=raw_version,
        )

    def _map_issue(self, raw_issue: dict[str, Any]) -> IssueRecord:
        fields = raw_issue.get("fields") or {}
        status = fields.get("status") or {}
        status_category = status.get("statusCategory") or {}
        sprint_external_id, sprint_field_present = self._extract_sprint_details(fields)
        epic_key = self._extract_epic_key(fields)
        parent_issue_key = self._extract_parent_issue_key(fields) or epic_key

        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}

        components = []
        for component in fields.get("components") or []:
            if isinstance(component, dict):
                name = component.get("name")
                if isinstance(name, str):
                    components.append(name)

        labels = [label for label in (fields.get("labels") or []) if isinstance(label, str)]
        fix_versions = [
            version
            for version in (
                self._map_fix_version(raw_version)
                for raw_version in (fields.get("fixVersions") or [])
                if isinstance(raw_version, dict)
            )
            if version is not None
        ]

        return IssueRecord(
            issue_key=raw_issue.get("key", ""),
            issue_id=str(raw_issue.get("id", "")),
            project_key=(fields.get("project") or {}).get("key"),
            issue_type=(fields.get("issuetype") or {}).get("name"),
            summary=fields.get("summary") or "",
            status_name=status.get("name") or "",
            status_category=status_category.get("name"),
            priority=(fields.get("priority") or {}).get("name"),
            assignee_account_id=assignee.get("accountId") or assignee.get("name"),
            reporter_account_id=reporter.get("accountId") or reporter.get("name"),
            story_points=_coerce_float(fields.get(self.story_points_field)),
            sprint_external_id=sprint_external_id,
            epic_key=epic_key,
            sprint_field_present=sprint_field_present,
            parent_issue_key=parent_issue_key,
            fix_versions=fix_versions,
            labels=labels,
            components=components,
            created_at_source=_parse_jira_datetime(fields.get("created")),
            updated_at_source=_parse_jira_datetime(fields.get("updated")),
            resolved_at_source=_parse_jira_datetime(fields.get("resolutiondate")),
            raw=raw_issue,
        )

    def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 100,
    ) -> tuple[list[IssueRecord], SyncBatch]:
        payload = self._request_json(
            "/rest/api/2/search",
            params={"jql": jql, "startAt": start_at, "maxResults": max_results},
        )
        raw_issues = payload.get("issues") or []
        issues = [self._map_issue(raw_issue) for raw_issue in raw_issues if isinstance(raw_issue, dict)]

        current_start = int(payload.get("startAt", start_at))
        total = int(payload.get("total", len(issues)))
        next_start = current_start + len(issues)
        has_more = next_start < total

        return issues, SyncBatch(next_cursor=str(next_start) if has_more else None, has_more=has_more)

    def incremental_issues(
        self,
        updated_since: datetime | None,
        start_at: int = 0,
        max_results: int = 100,
    ) -> tuple[list[IssueRecord], SyncBatch]:
        jql = self._build_incremental_jql(updated_since)
        return self.search_issues(jql=jql, start_at=start_at, max_results=max_results)

    def _build_incremental_jql(self, updated_since: datetime | None) -> str:
        clauses: list[str] = []
        if self.project_key:
            clauses.append(f"project = {self.project_key}")

        if updated_since:
            cursor = updated_since
            if cursor.tzinfo is None:
                cursor = cursor.replace(tzinfo=timezone.utc)
            cursor = cursor.astimezone(timezone.utc)
            clauses.append(f"updated >= '{cursor.strftime('%Y-%m-%d %H:%M')}'")

        if clauses:
            return " AND ".join(clauses) + " ORDER BY updated ASC"
        return "ORDER BY updated ASC"

    def count_incremental_issues(self, updated_since: datetime | None) -> int | None:
        jql = self._build_incremental_jql(updated_since)
        payload = self._request_json(
            "/rest/api/2/search",
            params={"jql": jql, "startAt": 0, "maxResults": 0},
        )
        total_raw = payload.get("total")
        if isinstance(total_raw, int):
            return total_raw
        try:
            return int(str(total_raw))
        except (TypeError, ValueError):
            return None

    def get_boards(self) -> list[BoardRecord]:
        boards: list[BoardRecord] = []
        start_at = 0
        max_results = 50

        while True:
            payload = self._request_json(
                "/rest/agile/1.0/board",
                params={"startAt": start_at, "maxResults": max_results},
            )
            values = payload.get("values") or []
            for board in values:
                if not isinstance(board, dict):
                    continue
                mapped = self._map_board(board)
                if mapped is not None:
                    boards.append(mapped)

            if not values:
                break
            if bool(payload.get("isLast")):
                break

            start_at += len(values)
            total = payload.get("total")
            if isinstance(total, int) and start_at >= total:
                break

        return boards

    def _map_project_version(
        self,
        raw_version: dict[str, Any],
        project_key: str,
    ) -> JiraProjectVersionRecord | None:
        version_id_raw = raw_version.get("id")
        name = raw_version.get("name")
        if version_id_raw is None or not isinstance(name, str) or not name.strip():
            return None
        version_id = str(version_id_raw).strip()
        if not version_id:
            return None
        description = raw_version.get("description")
        return JiraProjectVersionRecord(
            version_id=version_id,
            project_key=project_key,
            name=name.strip(),
            description=description if isinstance(description, str) else None,
            archived=bool(raw_version.get("archived")),
            released=bool(raw_version.get("released")),
            start_date=_parse_jira_date(raw_version.get("startDate")),
            release_date=_parse_jira_date(raw_version.get("releaseDate")),
            raw=raw_version,
        )

    def get_project_versions(self, project_key: str) -> list[JiraProjectVersionRecord]:
        normalized_project_key = project_key.strip()
        if not normalized_project_key:
            return []
        payload = self._request_json(
            f"/rest/api/2/project/{quote(normalized_project_key, safe='')}/versions"
        )
        if isinstance(payload, list):
            raw_versions = payload
        elif isinstance(payload, dict):
            raw_versions = payload.get("values") or payload.get("versions") or []
        else:
            raw_versions = []
        versions: list[JiraProjectVersionRecord] = []
        for raw_version in raw_versions:
            if not isinstance(raw_version, dict):
                continue
            mapped = self._map_project_version(raw_version, normalized_project_key)
            if mapped is not None:
                versions.append(mapped)
        return versions

    def _map_board(self, board: dict[str, Any]) -> BoardRecord | None:
        board_id_raw = board.get("id")
        try:
            board_id = int(str(board_id_raw))
        except (TypeError, ValueError):
            return None
        location = board.get("location") or {}
        return BoardRecord(
            external_board_id=board_id,
            name=board.get("name") or "",
            project_key=location.get("projectKey"),
            board_type=board.get("type"),
            raw=board,
        )

    def get_board(self, board_id: int) -> BoardRecord:
        payload = self._request_json(f"/rest/agile/1.0/board/{board_id}")
        board = self._map_board(payload)
        if board is None:
            raise JiraAPIError(f"Configured board payload was invalid for board {board_id}.")
        return board

    def get_sprints(self, board_id: int, state: str | None = None) -> list[SprintRecord]:
        sprints: list[SprintRecord] = []
        start_at = 0
        max_results = 50
        while True:
            params: dict[str, Any] = {"startAt": start_at, "maxResults": max_results}
            if state:
                params["state"] = state
            payload = self._request_json(f"/rest/agile/1.0/board/{board_id}/sprint", params=params)

            values = payload.get("values") or []
            for sprint in values:
                if not isinstance(sprint, dict):
                    continue
                sprint_id_raw = sprint.get("id")
                if not isinstance(sprint_id_raw, int):
                    try:
                        sprint_id_raw = int(str(sprint_id_raw))
                    except ValueError:
                        continue

                sprints.append(
                    SprintRecord(
                        external_sprint_id=sprint_id_raw,
                        board_external_id=board_id,
                        name=sprint.get("name") or "",
                        state=sprint.get("state") or "",
                        start_date=_parse_jira_datetime(sprint.get("startDate")),
                        end_date=_parse_jira_datetime(sprint.get("endDate")),
                        complete_date=_parse_jira_datetime(sprint.get("completeDate")),
                        goal=sprint.get("goal"),
                        raw=sprint,
                    )
                )

            if not values:
                break
            if bool(payload.get("isLast")):
                break

            start_at += len(values)
            total = payload.get("total")
            if isinstance(total, int) and start_at >= total:
                break

        return sprints

    def get_board_issues(
        self,
        board_id: int,
        start_at: int = 0,
        max_results: int = 100,
        jql: str | None = None,
    ) -> tuple[list[IssueRecord], SyncBatch, int | None]:
        params: dict[str, Any] = {"startAt": start_at, "maxResults": max_results}
        if jql:
            params["jql"] = jql
        payload = self._request_json(
            f"/rest/agile/1.0/board/{board_id}/issue",
            params=params,
        )
        raw_issues = payload.get("issues") or []
        issues = [self._map_issue(raw_issue) for raw_issue in raw_issues if isinstance(raw_issue, dict)]

        current_start = int(payload.get("startAt", start_at))
        total_raw = payload.get("total")
        total = int(total_raw) if isinstance(total_raw, int) else None
        next_start = current_start + len(issues)
        has_more = (
            len(issues) > 0
            and bool(payload.get("isLast")) is False
            and (total is None or next_start < total)
        )

        return issues, SyncBatch(next_cursor=str(next_start) if has_more else None, has_more=has_more), total

    def get_issue_changelog(self, issue_key: str) -> list[ChangelogItemRecord]:
        payload = self._request_json(
            f"/rest/api/2/issue/{issue_key}",
            params={"expand": "changelog"},
        )
        changelog = payload.get("changelog") or {}
        histories = changelog.get("histories") or []

        items: list[ChangelogItemRecord] = []
        for history in histories:
            if not isinstance(history, dict):
                continue
            changed_at = _parse_jira_datetime(history.get("created")) or datetime.now(
                tz=timezone.utc
            )
            author = history.get("author") or {}
            author_account_id = author.get("accountId") or author.get("name")
            history_id = history.get("id")

            for change_item in history.get("items") or []:
                if not isinstance(change_item, dict):
                    continue
                field_name = change_item.get("field")
                if not field_name:
                    continue
                items.append(
                    ChangelogItemRecord(
                        issue_key=issue_key,
                        history_id=str(history_id) if history_id is not None else None,
                        changed_at=changed_at,
                        author_account_id=author_account_id,
                        field_name=str(field_name),
                        from_value=change_item.get("fromString"),
                        to_value=change_item.get("toString"),
                        raw={"history": history, "item": change_item},
                    )
                )
        return items


# Backward-compatible alias to avoid breaking imports in early scaffolding.
JiraRestConnectorStub = JiraRestConnector
