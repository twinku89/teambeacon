from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.connectors.jira_config import JiraRuntimeConfig, load_env_files
from packages.connectors.jira_rest_stub import JiraAPIError, JiraRestConnector


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_board_url(base_url: str, board_id: int | None) -> str | None:
    if board_id is None:
        return None
    return f"{base_url.rstrip('/')}/secure/RapidBoard.jspa?rapidView={board_id}"


def _build_issue_url(base_url: str, issue_key: str | None) -> str | None:
    if not issue_key:
        return None
    return f"{base_url.rstrip('/')}/browse/{issue_key}"


def _build_project_url(base_url: str, project_key: str | None) -> str | None:
    if not project_key:
        return None
    return f"{base_url.rstrip('/')}/projects/{project_key}"


def _format_jira_error(error: Exception, runtime: JiraRuntimeConfig) -> str:
    detail = str(error)
    if "CERTIFICATE_VERIFY_FAILED" not in detail:
        return detail

    if runtime.ca_bundle_path:
        return (
            f"{detail}. Python could not validate the Jira TLS certificate using "
            f"the configured CA bundle at {runtime.ca_bundle_path}."
        )

    return (
        f"{detail}. Python does not trust Jira's TLS certificate chain. "
        "Set JIRA_CA_BUNDLE or ATLASSIAN_CA_BUNDLE in config/.env to a PEM file "
        "containing your corporate/internal CA certificate chain, then restart the API."
    )


def get_jira_status() -> dict[str, Any]:
    load_env_files()
    base_payload: dict[str, Any] = {
        "source": "jira",
        "connected": False,
        "checkedAt": _utc_iso_now(),
        "config": {},
        "checks": [],
        "metrics": {},
        "error": None,
    }

    try:
        runtime = JiraRuntimeConfig.from_env()
    except ValueError as exc:
        base_payload["error"] = str(exc)
        base_payload["checks"].append(
            {
                "name": "configuration",
                "ok": False,
                "detail": "Required JIRA environment variables are missing.",
            }
        )
        return base_payload

    base_payload["config"] = {
        "baseUrl": runtime.base_url,
        "projectKey": runtime.project_key,
        "boardId": runtime.board_id,
        "storyPointsField": runtime.story_points_field,
        "epicLinkField": runtime.epic_link_field,
        "sprintFields": list(runtime.sprint_field_candidates),
        "authMode": runtime.auth_mode,
    }

    connector = JiraRestConnector(
        config=runtime.to_connector_config(),
        project_key=runtime.project_key,
        story_points_field=runtime.story_points_field,
        epic_link_field=runtime.epic_link_field,
        sprint_field_candidates=runtime.sprint_field_candidates,
    )

    checks = []
    metrics: dict[str, Any] = {}
    sample_issue_key: str | None = None
    configured_board: dict[str, Any] | None = None
    configured_project_url = _build_project_url(runtime.base_url, runtime.project_key)
    errors: list[str] = []
    board_check_ok = False
    project_check_ok = False

    if runtime.board_id is not None:
        try:
            board = connector.get_board(runtime.board_id)
            configured_board = {
                "id": board.external_board_id,
                "name": board.name or f"Board {runtime.board_id}",
                "url": _build_board_url(runtime.base_url, runtime.board_id),
                "visible": True,
            }
            board_check_ok = True
            checks.append(
                {
                    "name": "configured_board_access",
                    "ok": True,
                    "detail": f"Board {runtime.board_id} ({configured_board['name']}) is accessible.",
                }
            )
        except JiraAPIError as exc:
            configured_board = {
                "id": runtime.board_id,
                "name": f"Board {runtime.board_id}",
                "url": _build_board_url(runtime.base_url, runtime.board_id),
                "visible": False,
            }
            checks.append(
                {
                    "name": "configured_board_access",
                    "ok": False,
                    "detail": f"Board {runtime.board_id} is not accessible ({exc.status_code or 'n/a'}).",
                }
            )
            errors.append(_format_jira_error(exc, runtime))
        except Exception as exc:  # noqa: BLE001
            configured_board = {
                "id": runtime.board_id,
                "name": f"Board {runtime.board_id}",
                "url": _build_board_url(runtime.base_url, runtime.board_id),
                "visible": False,
            }
            checks.append(
                {
                    "name": "configured_board_access",
                    "ok": False,
                    "detail": f"Unexpected failure while checking board {runtime.board_id}.",
                }
            )
            errors.append(_format_jira_error(exc, runtime))
    else:
        checks.append(
            {
                "name": "configured_board_access",
                "ok": False,
                "detail": "JIRA_BOARD_ID not configured.",
            }
        )

    if runtime.project_key:
        try:
            issues, _ = connector.search_issues(
                jql=f"project = {runtime.project_key} ORDER BY updated DESC",
                max_results=1,
            )
            metrics["projectSampleIssueCount"] = len(issues)
            sample_issue_key = issues[0].issue_key if issues else None
            project_check_ok = True
            checks.append(
                {
                    "name": "project_query",
                    "ok": True,
                    "detail": (
                        f"Project query succeeded for {runtime.project_key}."
                        if issues
                        else f"Project query succeeded for {runtime.project_key} (no recent issues)."
                    ),
                }
            )
        except JiraAPIError as exc:
            checks.append(
                {
                    "name": "project_query",
                    "ok": False,
                    "detail": f"Project query failed for {runtime.project_key} ({exc.status_code or 'n/a'}).",
                }
            )
            errors.append(_format_jira_error(exc, runtime))
        except Exception as exc:  # noqa: BLE001
            checks.append(
                {
                    "name": "project_query",
                    "ok": False,
                    "detail": f"Unexpected failure while querying project {runtime.project_key}.",
                }
            )
            errors.append(_format_jira_error(exc, runtime))
    else:
        checks.append(
            {
                "name": "project_query",
                "ok": False,
                "detail": "JIRA_PROJECT_KEY not configured.",
            }
        )

    base_payload["connected"] = board_check_ok and project_check_ok
    if errors:
        base_payload["error"] = "; ".join(errors)

    base_payload["checks"] = checks
    base_payload["metrics"] = metrics
    base_payload["sampleIssueKey"] = sample_issue_key
    base_payload["sampleIssueUrl"] = _build_issue_url(runtime.base_url, sample_issue_key)
    base_payload["configuredProjectUrl"] = configured_project_url
    base_payload["configuredBoard"] = configured_board
    return base_payload
