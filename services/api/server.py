from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, unquote, urlparse

from services.api.issues.current_sprint import get_current_sprint
from services.api.issues.current_sprint_changes import get_current_sprint_changes
from services.api.issues.current_sprint_work import get_current_sprint_work
from services.api.issues.query import search_synced_issues
from services.api.issues.release_insights import get_release_insights
from services.api.issues.team_insights import get_team_insights
from services.api.integrations.confluence_status import get_confluence_status
from services.api.integrations.jenkins_status import get_jenkins_status
from services.api.integrations.jira_status import get_jira_status
from services.api.integrations.jira_sync import (
    get_jira_sync_history,
    get_jira_sync_status,
    start_jira_sync,
)
from services.api.integrations.intelligence_chat import chat_with_intelligence, get_intelligence_status
from services.api.integrations.oci_genai_chat import get_oci_genai_status
from services.api.integrations.release_refresh import (
    get_release_refresh_result,
    get_release_refresh_status,
    start_release_refresh,
)
from services.api.integrations.security_audit import get_security_audit
from services.api.metadata.epic_config import (
    add_epic_group,
    add_work_type,
    delete_epic_metadata,
    delete_epic_group,
    delete_work_type,
    get_configured_epics_completed_cards,
    get_configured_epic_summary,
    get_epic_completed_cards,
    get_epic_lookup_config,
    get_epic_metadata,
    search_unconfigured_epics,
    update_epic_group,
    update_work_type,
    upsert_epic_metadata,
)
from services.api.news_dashboard import get_news_dashboard


StatusProvider = Callable[[], dict[str, Any]]
StartProvider = Callable[[Optional[str], Optional[str]], dict[str, Any]]
HistoryProvider = Callable[[int], dict[str, Any]]
IssueSearchProvider = Callable[..., dict[str, Any]]
CurrentSprintProvider = Callable[..., dict[str, Any]]
CurrentSprintWorkProvider = Callable[..., dict[str, Any]]
CurrentSprintChangesProvider = Callable[..., dict[str, Any]]
TeamInsightsProvider = Callable[..., dict[str, Any]]
ReleaseInsightsProvider = Callable[..., dict[str, Any]]
MetadataLookupProvider = Callable[[], dict[str, Any]]
MetadataCreateProvider = Callable[[str], dict[str, Any]]
MetadataUpdateProvider = Callable[[int, str], dict[str, Any]]
MetadataDeleteProvider = Callable[[int], dict[str, Any]]
MetadataEpicReadProvider = Callable[..., dict[str, Any]]
MetadataEpicSummaryProvider = Callable[..., dict[str, Any]]
MetadataEpicSearchProvider = Callable[..., dict[str, Any]]
MetadataEpicUpsertProvider = Callable[..., dict[str, Any]]
MetadataEpicDeleteProvider = Callable[[str], dict[str, Any]]
MetadataEpicCompletedCardsProvider = Callable[..., dict[str, Any]]
ConfluenceStatusProvider = Callable[[], dict[str, Any]]
JenkinsStatusProvider = Callable[[], dict[str, Any]]
AiStatusProvider = Callable[..., dict[str, Any]]
AiChatProvider = Callable[..., dict[str, Any]]
OciGenAiStatusProvider = Callable[[], dict[str, Any]]
ReleaseRefreshStatusProvider = Callable[[], dict[str, Any]]
ReleaseRefreshStartProvider = Callable[[Optional[list[dict[str, Any]]], Optional[str]], dict[str, Any]]
ReleaseRefreshResultProvider = Callable[[], dict[str, Any]]
SecurityAuditProvider = Callable[[], dict[str, Any]]
NewsDashboardProvider = Callable[[], dict[str, Any]]


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _text_bytes(payload: str) -> bytes:
    return payload.encode("utf-8")


def _resolve_static_file(web_root: Optional[Path], request_path: str) -> Optional[Path]:
    if web_root is None:
        return None
    if not web_root.exists() or not web_root.is_dir():
        return None

    path_only = request_path.split("?", 1)[0]
    cleaned_path = unquote(path_only).split("#", 1)[0].strip()
    if cleaned_path in {"", "/"}:
        candidate_rel = Path("index.html")
    else:
        candidate_rel = Path(cleaned_path.lstrip("/"))

    try:
        candidate = (web_root / candidate_rel).resolve()
        candidate.relative_to(web_root)
    except (ValueError, OSError):
        return None

    if candidate.is_file():
        return candidate

    # For SPA paths (for example "/team-insights"), return index.html fallback.
    if candidate.suffix:
        return None

    fallback = (web_root / "index.html").resolve()
    try:
        fallback.relative_to(web_root)
    except (ValueError, OSError):
        return None
    return fallback if fallback.is_file() else None


def _guess_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _swagger_ui_html(openapi_url: str = "/openapi.json") -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>TeamBeacon Local API - Swagger UI</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
    <style>
      html {{
        box-sizing: border-box;
        overflow-y: scroll;
      }}

      *,
      *::before,
      *::after {{
        box-sizing: inherit;
      }}

      body {{
        margin: 0;
        background: #f7f9fd;
      }}
    </style>
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
      window.ui = SwaggerUIBundle({{
        url: "{openapi_url}",
        dom_id: "#swagger-ui",
        presets: [SwaggerUIBundle.presets.apis],
        layout: "BaseLayout",
        deepLinking: true
      }});
    </script>
  </body>
</html>
"""


def _build_openapi_spec(server_url: str) -> dict[str, Any]:
    json_payload = {"application/json": {"schema": {"type": "object"}}}
    error_payload = {"description": "Bad request", "content": json_payload}

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "TeamBeacon Local API",
            "version": "1.0.0",
            "description": "Local HTTP API used by TeamBeacon desktop and web shells.",
        },
        "servers": [{"url": server_url}],
        "tags": [
            {"name": "health", "description": "Service health checks."},
            {"name": "integrations", "description": "Integration status and sync controls."},
            {"name": "issues", "description": "Issue and sprint-level views."},
            {"name": "metadata", "description": "Epic metadata and lookup configuration."},
            {"name": "news", "description": "Daily news dashboard feeds."},
            {"name": "ai", "description": "Provider-agnostic AI status and chat utilities."},
            {"name": "docs", "description": "OpenAPI and Swagger UI docs endpoints."},
        ],
        "paths": {
            "/health": {
                "get": {
                    "tags": ["health"],
                    "summary": "Health check",
                    "responses": {"200": {"description": "Service is healthy", "content": json_payload}},
                }
            },
            "/openapi.json": {
                "get": {
                    "tags": ["docs"],
                    "summary": "OpenAPI schema",
                    "responses": {"200": {"description": "OpenAPI schema document", "content": json_payload}},
                }
            },
            "/docs": {
                "get": {
                    "tags": ["docs"],
                    "summary": "Swagger UI",
                    "responses": {
                        "200": {
                            "description": "Swagger UI HTML",
                            "content": {"text/html": {"schema": {"type": "string"}}},
                        }
                    },
                }
            },
            "/api/integrations/jira/status": {
                "get": {
                    "tags": ["integrations"],
                    "summary": "JIRA integration status",
                    "responses": {"200": {"description": "JIRA status", "content": json_payload}},
                }
            },
            "/api/integrations/jira/sync/status": {
                "get": {
                    "tags": ["integrations"],
                    "summary": "Current JIRA sync state",
                    "responses": {"200": {"description": "JIRA sync state", "content": json_payload}},
                }
            },
            "/api/integrations/jira/sync/history": {
                "get": {
                    "tags": ["integrations"],
                    "summary": "JIRA sync history",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 20},
                            "description": "Maximum history rows to return.",
                        }
                    ],
                    "responses": {"200": {"description": "JIRA sync history", "content": json_payload}},
                }
            },
            "/api/integrations/jira/sync/start": {
                "post": {
                    "tags": ["integrations"],
                    "summary": "Start JIRA sync",
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "mode": {
                                            "type": "string",
                                            "enum": ["full", "since_last", "since_date"],
                                        },
                                        "sinceDate": {"type": "string", "description": "ISO date or timestamp"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Sync already running or no-op", "content": json_payload},
                        "202": {"description": "Sync started", "content": json_payload},
                        "400": error_payload,
                    },
                }
            },
            "/api/integrations/confluence/status": {
                "get": {
                    "tags": ["integrations"],
                    "summary": "Confluence integration status",
                    "responses": {"200": {"description": "Confluence status", "content": json_payload}},
                }
            },
            "/api/integrations/jenkins/status": {
                "get": {
                    "tags": ["integrations"],
                    "summary": "Jenkins integration status",
                    "responses": {"200": {"description": "Jenkins status", "content": json_payload}},
                }
            },
            "/api/releases/refresh/status": {
                "get": {
                    "tags": ["integrations"],
                    "summary": "Release Insights refresh status",
                    "responses": {"200": {"description": "Release refresh status", "content": json_payload}},
                }
            },
            "/api/releases/insights": {
                "get": {
                    "tags": ["issues"],
                    "summary": "JIRA release/version analytics",
                    "parameters": [
                        {"name": "releaseLimit", "in": "query", "schema": {"type": "integer", "default": 12}},
                        {"name": "projectKey", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Release insights payload", "content": json_payload}},
                }
            },
            "/api/releases/refresh/result": {
                "get": {
                    "tags": ["integrations"],
                    "summary": "Release Insights refresh result",
                    "responses": {"200": {"description": "Release refresh result", "content": json_payload}},
                }
            },
            "/api/releases/refresh/start": {
                "post": {
                    "tags": ["integrations"],
                    "summary": "Start Release Insights refresh",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["sources"],
                                    "properties": {
                                        "sources": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "confluenceUrl": {"type": "string"},
                                                    "prompt": {"type": "string"},
                                                },
                                            },
                                        },
                                        "overallPrompt": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Refresh already running or no-op", "content": json_payload},
                        "202": {"description": "Refresh started", "content": json_payload},
                        "400": error_payload,
                    },
                }
            },
            "/api/security/audit": {
                "get": {
                    "tags": ["integrations"],
                    "summary": "Security audit pipeline findings",
                    "responses": {"200": {"description": "Security audit findings", "content": json_payload}},
                }
            },
            "/api/news/dashboard": {
                "get": {
                    "tags": ["news"],
                    "summary": "Daily news dashboard",
                    "responses": {"200": {"description": "Latest news grouped by category", "content": json_payload}},
                }
            },
            "/api/integrations/oci-genai/status": {
                "get": {
                    "tags": ["ai"],
                    "summary": "OCI GenAI integration status (legacy compatibility endpoint)",
                    "responses": {"200": {"description": "OCI GenAI status", "content": json_payload}},
                }
            },
            "/api/integrations/ai/status": {
                "get": {
                    "tags": ["ai"],
                    "summary": "Active AI provider integration status",
                    "parameters": [
                        {
                            "name": "provider",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["oci", "ollama", "openai"]},
                            "description": "Optional provider override. Defaults to INTELLIGENCE_PROVIDER.",
                        }
                    ],
                    "responses": {
                        "200": {"description": "AI provider status", "content": json_payload},
                        "400": error_payload,
                    },
                }
            },
            "/api/ai/chat": {
                "post": {
                    "tags": ["ai"],
                    "summary": "Send chat request to active AI provider",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["message"],
                                    "properties": {
                                        "message": {"type": "string"},
                                        "provider": {"type": "string", "enum": ["oci", "ollama", "openai"]},
                                        "modelId": {"type": "string"},
                                        "maxTokens": {"type": "integer"},
                                        "temperature": {"type": "number"},
                                        "topP": {"type": "number"},
                                        "topK": {"type": "integer"},
                                        "frequencyPenalty": {"type": "number"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "AI provider response", "content": json_payload},
                        "400": error_payload,
                        "502": {"description": "AI provider upstream error", "content": json_payload},
                    },
                }
            },
            "/api/issues/search": {
                "get": {
                    "tags": ["issues"],
                    "summary": "Search synced issues",
                    "parameters": [
                        {"name": "epicKey", "in": "query", "schema": {"type": "string"}},
                        {"name": "assignee", "in": "query", "schema": {"type": "string"}},
                        {"name": "reporter", "in": "query", "schema": {"type": "string"}},
                        {"name": "workedBy", "in": "query", "schema": {"type": "string"}},
                        {"name": "issueType", "in": "query", "schema": {"type": "string"}},
                        {"name": "status", "in": "query", "schema": {"type": "string"}},
                        {"name": "updatedSince", "in": "query", "schema": {"type": "string"}},
                        {"name": "updatedUntil", "in": "query", "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 100}},
                    ],
                    "responses": {"200": {"description": "Issue search results", "content": json_payload}},
                }
            },
            "/api/sprints/current": {
                "get": {
                    "tags": ["issues"],
                    "summary": "Current sprint metadata",
                    "responses": {"200": {"description": "Current sprint", "content": json_payload}},
                }
            },
            "/api/sprints/current/work": {
                "get": {
                    "tags": ["issues"],
                    "summary": "Current sprint work buckets",
                    "responses": {"200": {"description": "Current sprint work", "content": json_payload}},
                }
            },
            "/api/sprints/current/changes": {
                "get": {
                    "tags": ["issues"],
                    "summary": "Current sprint scope/blocker changes",
                    "responses": {"200": {"description": "Current sprint changes", "content": json_payload}},
                }
            },
            "/api/team/insights": {
                "get": {
                    "tags": ["issues"],
                    "summary": "Team sprint trend and work-mix insights",
                    "parameters": [
                        {
                            "name": "sprintLimit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 1, "maximum": 12, "default": 6},
                            "description": (
                                "Number of recent sprints to include. API accepts 1-12; "
                                "UI presets are 1, 2, 3, 4, 6, 8, 10, and 12."
                            ),
                        },
                        {
                            "name": "cycleTimeStatusMode",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["default", "custom"], "default": "default"},
                            "description": (
                                "When set to custom, calculate cycle time from the explicitly selected workflow "
                                "statuses instead of the default status set."
                            ),
                        },
                        {
                            "name": "cycleTimeStatus",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "array", "items": {"type": "string"}},
                            "style": "form",
                            "explode": True,
                            "description": (
                                "Normalized workflow status keys to include in cycle-time calculations when "
                                "cycleTimeStatusMode=custom."
                            ),
                        },
                    ],
                    "responses": {"200": {"description": "Team insights payload", "content": json_payload}},
                }
            },
            "/api/metadata/lookup": {
                "get": {
                    "tags": ["metadata"],
                    "summary": "Lookup data (groups/work types)",
                    "responses": {"200": {"description": "Lookup data", "content": json_payload}},
                }
            },
            "/api/metadata/lookup/groups": {
                "post": {
                    "tags": ["metadata"],
                    "summary": "Create epic group",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
                            }
                        },
                    },
                    "responses": {"200": {"description": "Group created", "content": json_payload}, "400": error_payload},
                }
            },
            "/api/metadata/lookup/groups/update": {
                "post": {
                    "tags": ["metadata"],
                    "summary": "Update epic group",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["id", "name"],
                                    "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Group updated", "content": json_payload}, "400": error_payload},
                }
            },
            "/api/metadata/lookup/groups/delete": {
                "post": {
                    "tags": ["metadata"],
                    "summary": "Delete epic group",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}
                            }
                        },
                    },
                    "responses": {"200": {"description": "Group deleted", "content": json_payload}, "400": error_payload},
                }
            },
            "/api/metadata/lookup/work-types": {
                "post": {
                    "tags": ["metadata"],
                    "summary": "Create work type",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
                            }
                        },
                    },
                    "responses": {"200": {"description": "Work type created", "content": json_payload}, "400": error_payload},
                }
            },
            "/api/metadata/lookup/work-types/update": {
                "post": {
                    "tags": ["metadata"],
                    "summary": "Update work type",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["id", "name"],
                                    "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Work type updated", "content": json_payload}, "400": error_payload},
                }
            },
            "/api/metadata/lookup/work-types/delete": {
                "post": {
                    "tags": ["metadata"],
                    "summary": "Delete work type",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}
                            }
                        },
                    },
                    "responses": {"200": {"description": "Work type deleted", "content": json_payload}, "400": error_payload},
                }
            },
            "/api/metadata/epics": {
                "get": {
                    "tags": ["metadata"],
                    "summary": "Read configured epics",
                    "parameters": [
                        {"name": "epicKey", "in": "query", "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50}},
                    ],
                    "responses": {"200": {"description": "Configured epics", "content": json_payload}},
                },
                "post": {
                    "tags": ["metadata"],
                    "summary": "Create or update epic metadata",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["epicKey"],
                                    "properties": {
                                        "epicKey": {"type": "string"},
                                        "successCriteria": {"type": "array", "items": {"type": "string"}},
                                        "groupIds": {"type": "array", "items": {"type": "integer"}},
                                        "workTypeIds": {"type": "array", "items": {"type": "integer"}},
                                        "timelineEnabled": {"type": "boolean"},
                                        "timelineStartDate": {"type": "string"},
                                        "targetCompletionDate": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Epic metadata saved", "content": json_payload}, "400": error_payload},
                },
            },
            "/api/metadata/epics/delete": {
                "post": {
                    "tags": ["metadata"],
                    "summary": "Delete epic metadata",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["epicKey"],
                                    "properties": {"epicKey": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Epic metadata deleted", "content": json_payload}, "400": error_payload},
                }
            },
            "/api/metadata/epics/summary": {
                "get": {
                    "tags": ["metadata"],
                    "summary": "Configured epic summary",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50}},
                        {"name": "periodStart", "in": "query", "schema": {"type": "string"}},
                        {"name": "periodEnd", "in": "query", "schema": {"type": "string"}},
                        {"name": "timezone", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Configured epic summary", "content": json_payload}, "400": error_payload},
                }
            },
            "/api/metadata/epics/completed-cards": {
                "get": {
                    "tags": ["metadata"],
                    "summary": "Completed cards in reporting period for an epic",
                    "parameters": [
                        {"name": "epicKey", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 200}},
                        {"name": "periodStart", "in": "query", "schema": {"type": "string"}},
                        {"name": "periodEnd", "in": "query", "schema": {"type": "string"}},
                        {"name": "timezone", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {"description": "Completed cards in period", "content": json_payload},
                        "400": error_payload,
                    },
                }
            },
            "/api/metadata/epics/completed-cards/configured": {
                "get": {
                    "tags": ["metadata"],
                    "summary": "Completed cards in reporting period across configured initiatives",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 300}},
                        {"name": "periodStart", "in": "query", "schema": {"type": "string"}},
                        {"name": "periodEnd", "in": "query", "schema": {"type": "string"}},
                        {"name": "timezone", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {"description": "Completed cards across configured initiatives", "content": json_payload},
                        "400": error_payload,
                    },
                }
            },
            "/api/metadata/epics/candidates": {
                "get": {
                    "tags": ["metadata"],
                    "summary": "Unconfigured epic candidates",
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20}},
                    ],
                    "responses": {"200": {"description": "Epic candidates", "content": json_payload}},
                }
            },
        },
    }


def build_handler(
    jira_status_provider: StatusProvider = get_jira_status,
    jira_sync_status_provider: StatusProvider = get_jira_sync_status,
    jira_sync_start_provider: StartProvider = start_jira_sync,
    jira_sync_history_provider: HistoryProvider = get_jira_sync_history,
    issue_search_provider: IssueSearchProvider = search_synced_issues,
    current_sprint_provider: CurrentSprintProvider = get_current_sprint,
    current_sprint_work_provider: CurrentSprintWorkProvider = get_current_sprint_work,
    current_sprint_changes_provider: CurrentSprintChangesProvider = get_current_sprint_changes,
    team_insights_provider: TeamInsightsProvider = get_team_insights,
    release_insights_provider: ReleaseInsightsProvider = get_release_insights,
    metadata_lookup_provider: MetadataLookupProvider = get_epic_lookup_config,
    metadata_add_group_provider: MetadataCreateProvider = add_epic_group,
    metadata_add_work_type_provider: MetadataCreateProvider = add_work_type,
    metadata_update_group_provider: MetadataUpdateProvider = update_epic_group,
    metadata_delete_group_provider: MetadataDeleteProvider = delete_epic_group,
    metadata_update_work_type_provider: MetadataUpdateProvider = update_work_type,
    metadata_delete_work_type_provider: MetadataDeleteProvider = delete_work_type,
    metadata_read_epics_provider: MetadataEpicReadProvider = get_epic_metadata,
    metadata_summary_provider: MetadataEpicSummaryProvider = get_configured_epic_summary,
    metadata_completed_cards_provider: MetadataEpicCompletedCardsProvider = get_epic_completed_cards,
    metadata_configured_completed_cards_provider: MetadataEpicCompletedCardsProvider = get_configured_epics_completed_cards,
    metadata_search_epics_provider: MetadataEpicSearchProvider = search_unconfigured_epics,
    metadata_upsert_epic_provider: MetadataEpicUpsertProvider = upsert_epic_metadata,
    metadata_delete_epic_provider: MetadataEpicDeleteProvider = delete_epic_metadata,
    confluence_status_provider: ConfluenceStatusProvider = get_confluence_status,
    jenkins_status_provider: JenkinsStatusProvider = get_jenkins_status,
    ai_status_provider: AiStatusProvider = get_intelligence_status,
    ai_chat_provider: AiChatProvider = chat_with_intelligence,
    oci_genai_status_provider: OciGenAiStatusProvider = get_oci_genai_status,
    release_refresh_status_provider: ReleaseRefreshStatusProvider = get_release_refresh_status,
    release_refresh_result_provider: ReleaseRefreshResultProvider = get_release_refresh_result,
    release_refresh_start_provider: ReleaseRefreshStartProvider = start_release_refresh,
    security_audit_provider: SecurityAuditProvider = get_security_audit,
    news_dashboard_provider: NewsDashboardProvider = get_news_dashboard,
    web_dir: str | Path | None = None,
) -> type[BaseHTTPRequestHandler]:
    web_root = Path(web_dir).expanduser().resolve() if web_dir is not None else None

    class TeamBeaconHandler(BaseHTTPRequestHandler):
        def _set_headers(self, content_type: str, status_code: int = 200) -> None:
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def _set_json_headers(self, status_code: int = 200) -> None:
            self._set_headers("application/json; charset=utf-8", status_code)

        def _set_html_headers(self, status_code: int = 200) -> None:
            self._set_headers("text/html; charset=utf-8", status_code)

        def _set_binary_headers(self, content_type: str, content_length: int, status_code: int = 200) -> None:
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", str(content_length))
            self.end_headers()

        def _public_server_url(self) -> str:
            host = (self.headers.get("Host") or "127.0.0.1:8000").strip()
            proto_header = (self.headers.get("X-Forwarded-Proto") or "http").strip()
            proto = proto_header.split(",", 1)[0].strip() or "http"
            return f"{proto}://{host}"

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._set_json_headers(204)
            self.wfile.write(b"")

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            if path in {"/openapi.json", "/api/openapi.json"}:
                payload = _build_openapi_spec(server_url=self._public_server_url())
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path in {"/docs", "/docs/", "/api/docs", "/api/docs/", "/swagger", "/swagger/"}:
                self._set_html_headers(200)
                self.wfile.write(_text_bytes(_swagger_ui_html("/openapi.json")))
                return

            if path == "/health":
                self._set_json_headers(200)
                self.wfile.write(_json_bytes({"status": "ok"}))
                return

            if path == "/api/integrations/jira/status":
                payload = jira_status_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/integrations/jira/sync/status":
                payload = jira_sync_status_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/integrations/jira/sync/history":
                query = parse_qs(parsed.query)
                limit_raw = query.get("limit", ["20"])[0]
                try:
                    limit = int(limit_raw)
                except ValueError:
                    limit = 20
                payload = jira_sync_history_provider(limit)
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/integrations/confluence/status":
                payload = confluence_status_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/integrations/jenkins/status":
                payload = jenkins_status_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/releases/refresh/status":
                payload = release_refresh_status_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/releases/refresh/result":
                payload = release_refresh_result_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/security/audit":
                payload = security_audit_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/news/dashboard":
                payload = news_dashboard_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/releases/insights":
                query = parse_qs(parsed.query)
                release_limit_raw = query.get("releaseLimit", ["12"])[0]
                try:
                    release_limit = int(release_limit_raw)
                except ValueError:
                    release_limit = 12
                project_key_raw = query.get("projectKey", [None])[0]
                project_key = project_key_raw.strip() if isinstance(project_key_raw, str) else None
                payload = release_insights_provider(
                    release_limit=release_limit,
                    project_key=project_key,
                )
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/integrations/oci-genai/status":
                payload = oci_genai_status_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/integrations/ai/status":
                query = parse_qs(parsed.query)
                provider_raw = query.get("provider", [None])[0]
                provider = provider_raw.strip() if isinstance(provider_raw, str) else None
                try:
                    payload = ai_status_provider(provider=provider)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/issues/search":
                query = parse_qs(parsed.query)

                def _param(name: str) -> str | None:
                    value = query.get(name, [None])[0]
                    if isinstance(value, str):
                        value = value.strip()
                        return value or None
                    return None

                limit_raw = _param("limit") or "100"
                try:
                    limit = int(limit_raw)
                except ValueError:
                    limit = 100

                payload = issue_search_provider(
                    epic_key=_param("epicKey"),
                    assignee=_param("assignee"),
                    reporter=_param("reporter"),
                    worked_by=_param("workedBy"),
                    issue_type=_param("issueType"),
                    status=_param("status"),
                    updated_since=_param("updatedSince"),
                    updated_until=_param("updatedUntil"),
                    limit=limit,
                )
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/sprints/current":
                payload = current_sprint_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/sprints/current/work":
                payload = current_sprint_work_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/sprints/current/changes":
                payload = current_sprint_changes_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/team/insights":
                query = parse_qs(parsed.query)
                sprint_limit_raw = query.get("sprintLimit", ["6"])[0]
                try:
                    sprint_limit = int(sprint_limit_raw)
                except ValueError:
                    sprint_limit = 6
                cycle_time_status_mode = query.get("cycleTimeStatusMode", ["default"])[0]
                cycle_time_status_keys = query.get("cycleTimeStatus", []) if cycle_time_status_mode == "custom" else None
                payload = team_insights_provider(
                    sprint_limit=sprint_limit,
                    cycle_time_status_keys=cycle_time_status_keys,
                )
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/lookup":
                payload = metadata_lookup_provider()
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/epics":
                query = parse_qs(parsed.query)
                epic_key_raw = query.get("epicKey", [None])[0]
                epic_key = epic_key_raw.strip() if isinstance(epic_key_raw, str) else None
                limit_raw = query.get("limit", ["50"])[0]
                try:
                    limit = int(limit_raw)
                except ValueError:
                    limit = 50
                payload = metadata_read_epics_provider(epic_key=epic_key, limit=limit)
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/epics/summary":
                query = parse_qs(parsed.query)
                limit_raw = query.get("limit", ["50"])[0]
                try:
                    limit = int(limit_raw)
                except ValueError:
                    limit = 50
                period_start_raw = query.get("periodStart", [None])[0]
                period_start = period_start_raw.strip() if isinstance(period_start_raw, str) else None
                period_end_raw = query.get("periodEnd", [None])[0]
                period_end = period_end_raw.strip() if isinstance(period_end_raw, str) else None
                timezone_raw = query.get("timezone", [None])[0]
                timezone_name = timezone_raw.strip() if isinstance(timezone_raw, str) else None
                try:
                    payload = metadata_summary_provider(
                        limit=limit,
                        period_start=period_start,
                        period_end=period_end,
                        timezone_name=timezone_name,
                    )
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/epics/completed-cards":
                query = parse_qs(parsed.query)
                epic_key_raw = query.get("epicKey", [None])[0]
                epic_key = epic_key_raw.strip() if isinstance(epic_key_raw, str) else None
                if not epic_key:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "epicKey is required."}))
                    return

                limit_raw = query.get("limit", ["200"])[0]
                try:
                    limit = int(limit_raw)
                except ValueError:
                    limit = 200

                period_start_raw = query.get("periodStart", [None])[0]
                period_start = period_start_raw.strip() if isinstance(period_start_raw, str) else None
                period_end_raw = query.get("periodEnd", [None])[0]
                period_end = period_end_raw.strip() if isinstance(period_end_raw, str) else None
                timezone_raw = query.get("timezone", [None])[0]
                timezone_name = timezone_raw.strip() if isinstance(timezone_raw, str) else None

                try:
                    payload = metadata_completed_cards_provider(
                        epic_key=epic_key,
                        limit=limit,
                        period_start=period_start,
                        period_end=period_end,
                        timezone_name=timezone_name,
                    )
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return

                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/epics/completed-cards/configured":
                query = parse_qs(parsed.query)
                limit_raw = query.get("limit", ["300"])[0]
                try:
                    limit = int(limit_raw)
                except ValueError:
                    limit = 300

                period_start_raw = query.get("periodStart", [None])[0]
                period_start = period_start_raw.strip() if isinstance(period_start_raw, str) else None
                period_end_raw = query.get("periodEnd", [None])[0]
                period_end = period_end_raw.strip() if isinstance(period_end_raw, str) else None
                timezone_raw = query.get("timezone", [None])[0]
                timezone_name = timezone_raw.strip() if isinstance(timezone_raw, str) else None

                try:
                    payload = metadata_configured_completed_cards_provider(
                        limit=limit,
                        period_start=period_start,
                        period_end=period_end,
                        timezone_name=timezone_name,
                    )
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return

                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/epics/candidates":
                query = parse_qs(parsed.query)
                query_raw = query.get("q", [None])[0]
                candidate_query = query_raw.strip() if isinstance(query_raw, str) else None
                limit_raw = query.get("limit", ["20"])[0]
                try:
                    limit = int(limit_raw)
                except ValueError:
                    limit = 20
                payload = metadata_search_epics_provider(query=candidate_query, limit=limit)
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            static_file = _resolve_static_file(web_root, path)
            if static_file is not None and path != "/api" and not path.startswith("/api/"):
                content = static_file.read_bytes()
                self._set_binary_headers(_guess_content_type(static_file), len(content), 200)
                self.wfile.write(content)
                return

            self._set_json_headers(404)
            self.wfile.write(_json_bytes({"error": "not_found"}))

        def do_POST(self) -> None:  # noqa: N802
            body_payload: Any = {}
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            if content_length > 0:
                raw_body = self.rfile.read(content_length)
                try:
                    decoded = raw_body.decode("utf-8")
                    body_payload = json.loads(decoded) if decoded else {}
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "Invalid JSON payload."}))
                    return

            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/integrations/jira/sync/start":
                mode = None
                since_date = None
                if isinstance(body_payload, dict):
                    mode_raw = body_payload.get("mode")
                    mode = mode_raw if isinstance(mode_raw, str) else None
                    since_date_raw = body_payload.get("sinceDate")
                    since_date = since_date_raw if isinstance(since_date_raw, str) else None
                try:
                    payload = jira_sync_start_provider(mode, since_date)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                status_code = 202 if payload.get("started") else 200
                self._set_json_headers(status_code)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/releases/refresh/start":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return

                sources_raw = body_payload.get("sources")
                if sources_raw is None:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "sources is required."}))
                    return
                if not isinstance(sources_raw, list):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "sources must be an array."}))
                    return

                overall_prompt_raw = body_payload.get("overallPrompt")
                if overall_prompt_raw is not None and not isinstance(overall_prompt_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "overallPrompt must be a string."}))
                    return
                overall_prompt = overall_prompt_raw if isinstance(overall_prompt_raw, str) else None

                try:
                    payload = release_refresh_start_provider(sources_raw, overall_prompt)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return

                status_code = 202 if payload.get("started") else 200
                self._set_json_headers(status_code)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/ai/chat":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return

                message_raw = body_payload.get("message")
                if not isinstance(message_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "message is required."}))
                    return

                provider_raw = body_payload.get("provider")
                if provider_raw is not None and not isinstance(provider_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "provider must be a string."}))
                    return
                provider = provider_raw if isinstance(provider_raw, str) else None

                model_id_raw = body_payload.get("modelId")
                if model_id_raw is not None and not isinstance(model_id_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "modelId must be a string."}))
                    return
                model_id = model_id_raw if isinstance(model_id_raw, str) else None

                max_tokens_raw = body_payload.get("maxTokens")
                if max_tokens_raw is not None and not isinstance(max_tokens_raw, int):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "maxTokens must be an integer."}))
                    return
                max_tokens = max_tokens_raw if isinstance(max_tokens_raw, int) else None

                temperature_raw = body_payload.get("temperature")
                if temperature_raw is not None and not isinstance(temperature_raw, (int, float)):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "temperature must be a number."}))
                    return
                temperature = float(temperature_raw) if isinstance(temperature_raw, (int, float)) else None

                top_p_raw = body_payload.get("topP")
                if top_p_raw is not None and not isinstance(top_p_raw, (int, float)):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "topP must be a number."}))
                    return
                top_p = float(top_p_raw) if isinstance(top_p_raw, (int, float)) else None

                top_k_raw = body_payload.get("topK")
                if top_k_raw is not None and not isinstance(top_k_raw, int):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "topK must be an integer."}))
                    return
                top_k = top_k_raw if isinstance(top_k_raw, int) else None

                frequency_penalty_raw = body_payload.get("frequencyPenalty")
                if frequency_penalty_raw is not None and not isinstance(frequency_penalty_raw, (int, float)):
                    self._set_json_headers(400)
                    self.wfile.write(
                        _json_bytes({"error": "bad_request", "detail": "frequencyPenalty must be a number."})
                    )
                    return
                frequency_penalty = (
                    float(frequency_penalty_raw) if isinstance(frequency_penalty_raw, (int, float)) else None
                )

                try:
                    payload = ai_chat_provider(
                        message=message_raw,
                        provider=provider,
                        model_id=model_id,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        top_k=top_k,
                        frequency_penalty=frequency_penalty,
                    )
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                except RuntimeError as exc:
                    self._set_json_headers(502)
                    self.wfile.write(_json_bytes({"error": "upstream_error", "detail": str(exc)}))
                    return

                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/lookup/groups":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return
                name_raw = body_payload.get("name")
                if not isinstance(name_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "name is required."}))
                    return
                try:
                    payload = metadata_add_group_provider(name_raw)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/lookup/work-types":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return
                name_raw = body_payload.get("name")
                if not isinstance(name_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "name is required."}))
                    return
                try:
                    payload = metadata_add_work_type_provider(name_raw)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/lookup/groups/update":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return
                id_raw = body_payload.get("id")
                name_raw = body_payload.get("name")
                if not isinstance(id_raw, int):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "id is required as integer."}))
                    return
                if not isinstance(name_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "name is required."}))
                    return
                try:
                    payload = metadata_update_group_provider(id_raw, name_raw)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/lookup/groups/delete":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return
                id_raw = body_payload.get("id")
                if not isinstance(id_raw, int):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "id is required as integer."}))
                    return
                try:
                    payload = metadata_delete_group_provider(id_raw)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/lookup/work-types/update":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return
                id_raw = body_payload.get("id")
                name_raw = body_payload.get("name")
                if not isinstance(id_raw, int):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "id is required as integer."}))
                    return
                if not isinstance(name_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "name is required."}))
                    return
                try:
                    payload = metadata_update_work_type_provider(id_raw, name_raw)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/lookup/work-types/delete":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return
                id_raw = body_payload.get("id")
                if not isinstance(id_raw, int):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "id is required as integer."}))
                    return
                try:
                    payload = metadata_delete_work_type_provider(id_raw)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/epics":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return
                epic_key_raw = body_payload.get("epicKey")
                if not isinstance(epic_key_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "epicKey is required."}))
                    return

                success_criteria_raw = body_payload.get("successCriteria")
                if success_criteria_raw is not None and not isinstance(success_criteria_raw, list):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "successCriteria must be a list of strings."}))
                    return
                group_ids_raw = body_payload.get("groupIds")
                if group_ids_raw is not None and not isinstance(group_ids_raw, list):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "groupIds must be a list of integers."}))
                    return
                if isinstance(group_ids_raw, list) and len(group_ids_raw) > 1:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "Only one group can be configured per epic."}))
                    return
                work_type_ids_raw = body_payload.get("workTypeIds")
                if work_type_ids_raw is not None and not isinstance(work_type_ids_raw, list):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "workTypeIds must be a list of integers."}))
                    return
                if isinstance(work_type_ids_raw, list) and len(work_type_ids_raw) > 1:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "Only one work type can be configured per epic."}))
                    return
                timeline_enabled_raw = body_payload.get("timelineEnabled")
                if timeline_enabled_raw is not None and not isinstance(timeline_enabled_raw, bool):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "timelineEnabled must be a boolean."}))
                    return
                timeline_start_date_raw = body_payload.get("timelineStartDate")
                if timeline_start_date_raw is not None and not isinstance(timeline_start_date_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(
                        _json_bytes({"error": "bad_request", "detail": "timelineStartDate must be a string date."})
                    )
                    return
                target_completion_date_raw = body_payload.get("targetCompletionDate")
                if target_completion_date_raw is not None and not isinstance(target_completion_date_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(
                        _json_bytes({"error": "bad_request", "detail": "targetCompletionDate must be a string date."})
                    )
                    return

                try:
                    payload = metadata_upsert_epic_provider(
                        epic_key=epic_key_raw,
                        success_criteria=success_criteria_raw,
                        group_ids=group_ids_raw,
                        work_type_ids=work_type_ids_raw,
                        timeline_enabled=timeline_enabled_raw,
                        timeline_start_date=timeline_start_date_raw,
                        target_completion_date=target_completion_date_raw,
                    )
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            if path == "/api/metadata/epics/delete":
                if not isinstance(body_payload, dict):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "JSON object payload is required."}))
                    return
                epic_key_raw = body_payload.get("epicKey")
                if not isinstance(epic_key_raw, str):
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": "epicKey is required."}))
                    return
                try:
                    payload = metadata_delete_epic_provider(epic_key_raw)
                except ValueError as exc:
                    self._set_json_headers(400)
                    self.wfile.write(_json_bytes({"error": "bad_request", "detail": str(exc)}))
                    return
                self._set_json_headers(200)
                self.wfile.write(_json_bytes(payload))
                return

            self._set_json_headers(404)
            self.wfile.write(_json_bytes({"error": "not_found"}))

        def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
            # Keep local API output quiet during normal development.
            return

    return TeamBeaconHandler


def run_server(host: str = "127.0.0.1", port: int = 8000, web_dir: str | Path | None = None) -> None:
    handler = build_handler(web_dir=web_dir)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"TeamBeacon API listening on http://{host}:{port}")
    published_port_raw = os.getenv("TEAMBEACON_HOST_PORT", "").strip()
    if published_port_raw:
        try:
            published_port = int(published_port_raw)
        except ValueError:
            published_port = None
        if published_port is not None and published_port > 0 and published_port <= 65535:
            print(f"TeamBeacon host URL (Docker port mapping): http://127.0.0.1:{published_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TeamBeacon local API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--web-dir",
        default=None,
        help="Optional path to a built web directory (for example app/web) to serve static assets.",
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, web_dir=args.web_dir)


if __name__ == "__main__":
    main()
