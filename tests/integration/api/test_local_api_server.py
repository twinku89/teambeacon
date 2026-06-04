from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.api.server import build_handler


class LocalApiServerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sync_start_calls: list[tuple[str | None, str | None]] = []
        self.issue_search_calls: list[dict[str, object]] = []
        self.current_sprint_calls: list[bool] = []
        self.current_sprint_changes_calls: list[bool] = []
        self.current_sprint_work_calls: list[bool] = []
        self.team_insights_calls: list[tuple[int, list[str] | None]] = []
        self.group_create_calls: list[str] = []
        self.work_type_create_calls: list[str] = []
        self.group_update_calls: list[tuple[int, str]] = []
        self.work_type_update_calls: list[tuple[int, str]] = []
        self.group_delete_calls: list[int] = []
        self.work_type_delete_calls: list[int] = []
        self.epic_upsert_calls: list[dict[str, object]] = []
        self.epic_delete_calls: list[str] = []
        self.epic_candidate_calls: list[tuple[str | None, int]] = []
        self.epic_summary_calls: list[tuple[int, str | None, str | None, str | None]] = []
        self.epic_completed_cards_calls: list[tuple[str, int, str | None, str | None, str | None]] = []
        self.configured_completed_cards_calls: list[tuple[int, str | None, str | None, str | None]] = []
        self.ai_status_calls: list[str | None] = []
        self.oci_chat_calls: list[dict[str, object]] = []
        self.release_refresh_start_calls: list[dict[str, object]] = []
        self.release_insights_calls: list[tuple[int, str | None]] = []

        def fake_status():
            return {
                "source": "jira",
                "connected": True,
                "checkedAt": "2026-03-25T00:00:00+00:00",
                "config": {"projectKey": "CEGBUPOL"},
                "checks": [],
                "metrics": {"boardCount": 1},
                "sampleIssueKey": "CEGBUPOL-1",
                "error": None,
            }

        def fake_sync_status():
            return {
                "source": "jira",
                "state": "idle",
                "phase": "idle",
                "syncMode": "full",
                "boardsSynced": 0,
                "sprintsSynced": 0,
                "downloadedIssues": 0,
                "totalIssues": None,
                "percent": None,
                "lastSyncedAt": "2026-03-25T00:00:00+00:00",
                "error": None,
            }

        def fake_sync_start(mode=None, since_date=None):  # noqa: ANN001
            if mode not in {None, "full", "since_last", "since_date"}:
                raise ValueError("Unsupported sync mode. Allowed values: full, since_last, since_date.")
            if mode == "since_date" and not since_date:
                raise ValueError("sinceDate is required in YYYY-MM-DD or ISO-8601 format when mode is since_date.")
            self.sync_start_calls.append((mode, since_date))
            return {
                "source": "jira",
                "state": "running",
                "phase": "issues",
                "syncMode": mode or "full",
                "requestedSince": since_date,
                "boardsSynced": 1,
                "sprintsSynced": 12,
                "downloadedIssues": 12,
                "totalIssues": 5000,
                "percent": 0.24,
                "started": True,
                "error": None,
            }

        def fake_sync_history(limit):  # noqa: ANN001
            _ = limit
            return {
                "source": "jira",
                "history": [
                    {
                        "id": 7,
                        "scopeKey": "board:27193",
                        "boardId": 27193,
                        "boardName": "CEGBU Polaris",
                        "syncMode": "since_last",
                        "boardsSynced": 1,
                        "sprintsSynced": 12,
                        "issuesSynced": 5000,
                        "totalIssues": 5000,
                        "status": "completed",
                        "error": None,
                        "startedAt": "2026-03-25T00:00:00+00:00",
                        "finishedAt": "2026-03-25T00:10:00+00:00",
                    }
                ],
            }

        def fake_oci_status():
            return {
                "source": "oci_genai",
                "connected": True,
                "checkedAt": "2026-03-25T00:00:00+00:00",
                "config": {
                    "endpoint": "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
                    "modelId": "cohere.command-r-08-2024",
                },
                "checks": [
                    {"name": "oci_sdk", "ok": True, "detail": "OCI Python SDK is available."},
                    {"name": "oci_profile", "ok": True, "detail": "Profile DEFAULT loaded."},
                ],
                "error": None,
            }

        def fake_confluence_status():
            return {
                "source": "confluence",
                "connected": True,
                "checkedAt": "2026-03-25T00:00:00+00:00",
                "config": {
                    "baseUrl": "https://gbuconfluence.oraclecorp.com",
                    "authMode": "pat_bearer",
                    "timeoutSeconds": 30,
                },
                "checks": [
                    {"name": "space_query", "ok": True, "detail": "Confluence space query succeeded."},
                ],
                "metrics": {"spaceCount": 1},
                "error": None,
            }

        def fake_release_refresh_status():
            return {
                "source": "releases",
                "state": "completed",
                "phase": "done",
                "percent": 100.0,
                "message": "Release refresh complete.",
                "startedAt": "2026-03-25T00:00:00+00:00",
                "finishedAt": "2026-03-25T00:04:00+00:00",
                "generatedAt": "2026-03-25T00:04:00+00:00",
                "error": None,
                "sources": [
                    {
                        "id": 1,
                        "confluenceUrl": "https://gbuconfluence.oraclecorp.com/display/SEN/Release+Notes",
                        "prompt": "Summarize release highlights.",
                        "state": "completed",
                        "percent": 100.0,
                        "message": "Completed.",
                        "error": None,
                    }
                ],
            }

        def fake_release_refresh_result():
            return {
                "source": "releases",
                "state": "completed",
                "generatedAt": "2026-03-25T00:04:00+00:00",
                "html": "<h4>Summary</h4><p>Release output.</p>",
                "text": "Summary:\nRelease output.",
                "sources": [
                    {
                        "id": 1,
                        "confluenceUrl": "https://gbuconfluence.oraclecorp.com/display/SEN/Release+Notes",
                        "title": "Release Notes",
                        "resolvedUrl": "https://gbuconfluence.oraclecorp.com/display/SEN/Release+Notes",
                        "summary": "Source summary",
                        "state": "completed",
                        "error": None,
                    }
                ],
                "error": None,
            }

        def fake_release_refresh_start(sources=None, overall_prompt=None):  # noqa: ANN001
            if not isinstance(sources, list):
                raise ValueError("sources must be an array.")
            self.release_refresh_start_calls.append(
                {
                    "sources": sources,
                    "overall_prompt": overall_prompt,
                }
            )
            return {
                "source": "releases",
                "state": "running",
                "phase": "initializing",
                "percent": 0.0,
                "message": "Starting release refresh.",
                "startedAt": "2026-03-25T00:00:00+00:00",
                "finishedAt": None,
                "generatedAt": None,
                "error": None,
                "started": True,
                "sources": [
                    {
                        "id": 1,
                        "confluenceUrl": "https://gbuconfluence.oraclecorp.com/display/SEN/Release+Notes",
                        "prompt": "Summarize release highlights.",
                        "state": "queued",
                        "percent": 0.0,
                        "message": "Queued",
                        "error": None,
                    }
                ],
            }

        def fake_release_insights(release_limit=12, project_key=None):  # noqa: ANN001
            self.release_insights_calls.append((release_limit, project_key))
            return {
                "source": "local",
                "generatedAt": "2026-05-20T00:00:00+00:00",
                "projectKey": project_key or "CEGBUPOL",
                "metrics": {
                    "totalReleases": 3,
                    "releasedCount": 2,
                    "ongoingCount": 1,
                    "archivedCount": 0,
                    "overdueCount": 1,
                    "dueSoonCount": 0,
                    "avgCycleTimeDays": 25.0,
                    "medianCycleTimeDays": 25.0,
                    "p85CycleTimeDays": 30.0,
                    "avgCadenceDays": 21.0,
                    "deliveredStoryPoints": 16.0,
                },
                "cycleTimeTrend": [
                    {
                        "versionId": "26000",
                        "name": "Search 26.3",
                        "releaseDate": "2026-03-31T00:00:00+00:00",
                        "cycleTimeDays": 30.0,
                        "storyPoints": 13.0,
                        "issueCount": 2,
                    }
                ],
                "ongoingReleases": [],
                "recentReleases": [],
                "riskSignals": [],
                "summary": "1 ongoing release, 1 overdue.",
                "error": None,
            }

        def fake_oci_chat(
            *,
            message,  # noqa: ANN001
            model_id=None,  # noqa: ANN001
            max_tokens=None,  # noqa: ANN001
            temperature=None,  # noqa: ANN001
            top_p=None,  # noqa: ANN001
            top_k=None,  # noqa: ANN001
            frequency_penalty=None,  # noqa: ANN001
        ):
            self.oci_chat_calls.append(
                {
                    "message": message,
                    "model_id": model_id,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "frequency_penalty": frequency_penalty,
                }
            )
            return {
                "source": "oci_genai",
                "modelId": model_id or "cohere.command-r-08-2024",
                "response": {"text": "TeamBeacon can summarize sprint risk weekly."},
                "request": {
                    "message": message,
                    "maxTokens": max_tokens if max_tokens is not None else 1000,
                    "temperature": temperature if temperature is not None else 1.0,
                    "topP": top_p if top_p is not None else 0.75,
                    "topK": top_k if top_k is not None else 0,
                    "frequencyPenalty": frequency_penalty if frequency_penalty is not None else 0.0,
                },
                "error": None,
            }

        def fake_ai_status(*, provider=None):  # noqa: ANN001
            self.ai_status_calls.append(provider)
            selected = provider or "oci"
            if selected == "ollama":
                return {
                    "source": "ollama",
                    "provider": "ollama",
                    "configuredProvider": "oci",
                    "supportedProviders": ["oci", "ollama", "openai"],
                    "connected": True,
                    "checkedAt": "2026-03-25T00:00:00+00:00",
                    "config": {
                        "baseUrl": "http://127.0.0.1:11434",
                        "modelId": "gemma4:e2b",
                    },
                    "checks": [{"name": "ollama_api", "ok": True, "detail": "Ollama API is reachable."}],
                    "error": None,
                }
            if selected == "openai":
                return {
                    "source": "openai",
                    "provider": "openai",
                    "configuredProvider": "oci",
                    "supportedProviders": ["oci", "ollama", "openai"],
                    "connected": True,
                    "checkedAt": "2026-03-25T00:00:00+00:00",
                    "config": {
                        "baseUrl": "https://api.openai.com/v1",
                        "modelId": "gpt-4o-mini",
                    },
                    "checks": [{"name": "openai_api", "ok": True, "detail": "OpenAI API is reachable."}],
                    "error": None,
                }
            return {
                "source": "oci_genai",
                "provider": "oci",
                "configuredProvider": "oci",
                "supportedProviders": ["oci", "ollama", "openai"],
                "connected": True,
                "checkedAt": "2026-03-25T00:00:00+00:00",
                "config": {
                    "endpoint": "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
                    "modelId": "cohere.command-r-08-2024",
                },
                "checks": [
                    {"name": "oci_sdk", "ok": True, "detail": "OCI Python SDK is available."},
                    {"name": "oci_profile", "ok": True, "detail": "Profile DEFAULT loaded."},
                ],
                "error": None,
            }

        def fake_ai_chat(
            *,
            message,  # noqa: ANN001
            provider=None,  # noqa: ANN001
            model_id=None,  # noqa: ANN001
            max_tokens=None,  # noqa: ANN001
            temperature=None,  # noqa: ANN001
            top_p=None,  # noqa: ANN001
            top_k=None,  # noqa: ANN001
            frequency_penalty=None,  # noqa: ANN001
        ):
            self.oci_chat_calls.append(
                {
                    "message": message,
                    "provider": provider,
                    "model_id": model_id,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "frequency_penalty": frequency_penalty,
                }
            )

            selected = provider or "oci"
            response_source = "oci_genai"
            default_model = "cohere.command-r-08-2024"
            if selected == "ollama":
                response_source = "ollama"
                default_model = "gemma4:e2b"
            elif selected == "openai":
                response_source = "openai"
                default_model = "gpt-4o-mini"

            return {
                "source": response_source,
                "provider": selected,
                "configuredProvider": "oci",
                "modelId": model_id or default_model,
                "response": {"text": "TeamBeacon can summarize sprint risk weekly."},
                "request": {
                    "message": message,
                    "maxTokens": max_tokens if max_tokens is not None else (1000 if selected == "oci" else 600),
                    "temperature": temperature if temperature is not None else 1.0,
                    "topP": top_p if top_p is not None else 0.75,
                    "topK": top_k if top_k is not None else 0,
                    "frequencyPenalty": frequency_penalty if frequency_penalty is not None else 0.0,
                },
                "error": None,
            }

        def fake_issue_search(**kwargs):  # noqa: ANN003
            self.issue_search_calls.append(kwargs)
            return {
                "source": "local",
                "filters": {
                    "epicKey": kwargs.get("epic_key"),
                    "workedBy": kwargs.get("worked_by"),
                },
                "count": 1,
                "issues": [
                    {
                        "issueKey": "CEGBUPOL-101",
                        "summary": "Sample",
                        "contributors": ["user-dev", "user-qa"],
                    }
                ],
            }

        def fake_current_sprint():
            self.current_sprint_calls.append(True)
            return {
                "source": "local",
                "sprint": {
                    "id": 55421,
                    "boardId": 27193,
                    "name": "CEGBU Polaris Sprint 45",
                    "state": "active",
                    "startDate": "2026-03-20T00:00:00+00:00",
                    "endDate": "2026-03-31T00:00:00+00:00",
                    "remainingDays": 5,
                },
                "error": None,
            }

        def fake_current_sprint_work():
            self.current_sprint_work_calls.append(True)
            return {
                "source": "local",
                "sprint": {
                    "id": 55421,
                    "boardId": 27193,
                    "name": "CEGBU Polaris Sprint 45",
                    "state": "active",
                    "startDate": "2026-03-20T00:00:00+00:00",
                    "endDate": "2026-03-31T00:00:00+00:00",
                    "remainingDays": 5,
                },
                "work": {
                    "done": [
                        {
                            "issueKey": "CEGBUPOL-6001",
                            "summary": "Completed migration",
                            "status": "Done",
                            "statusCategory": "Done",
                            "storyPoints": 8.0,
                            "epicKey": "CEGBUPOL-5000",
                            "epicName": "Platform Reliability Epic",
                            "issueUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-6001",
                        },
                    ],
                    "inProgress": [
                        {
                            "issueKey": "CEGBUPOL-6002",
                            "summary": "Deploy validation",
                            "status": "In Progress",
                            "statusCategory": "In Progress",
                            "storyPoints": 5.0,
                            "epicKey": "CEGBUPOL-5000",
                            "epicName": "Platform Reliability Epic",
                            "issueUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-6002",
                        },
                    ],
                    "planned": [
                        {
                            "issueKey": "CEGBUPOL-6003",
                            "summary": "Canary extension",
                            "status": "To Do",
                            "statusCategory": "To Do",
                            "storyPoints": 3.0,
                            "epicKey": "CEGBUPOL-5000",
                            "epicName": "Platform Reliability Epic",
                            "issueUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-6003",
                        },
                    ],
                    "totals": {
                        "done": 1,
                        "inProgress": 1,
                        "planned": 1,
                        "total": 3,
                        "storyPoints": {"done": 8.0, "inProgress": 5.0, "planned": 3.0, "total": 16.0},
                    },
                },
                "error": None,
            }

        def fake_current_sprint_changes():
            self.current_sprint_changes_calls.append(True)
            return {
                "source": "local",
                "sprint": {
                    "id": 55421,
                    "boardId": 27193,
                    "name": "CEGBU Polaris Sprint 45",
                    "state": "active",
                    "startDate": "2026-03-20T00:00:00+00:00",
                    "endDate": "2026-03-31T00:00:00+00:00",
                    "remainingDays": 5,
                },
                "changes": {
                    "addedAfterStart": {
                        "count": 4,
                        "storyPointsTotal": 11.0,
                        "issueKeys": ["CEGBUPOL-6101", "CEGBUPOL-6102"],
                        "issueCards": [
                            {
                                "issueKey": "CEGBUPOL-6101",
                                "summary": "Added card 1",
                                "issueUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-6101",
                                "epicName": "Domain Support Q4",
                                "epicUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-3553",
                                "storyPoints": 2.0,
                                "status": "In Progress",
                                "statusCategory": "In Progress",
                            },
                            {
                                "issueKey": "CEGBUPOL-6102",
                                "summary": "Added card 2",
                                "issueUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-6102",
                                "epicName": "Domain Support Q4",
                                "epicUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-3553",
                                "storyPoints": 9.0,
                                "status": "To Do",
                                "statusCategory": "To Do",
                            },
                        ],
                    },
                    "removedAfterStart": {
                        "count": 1,
                        "storyPointsTotal": 3.0,
                        "issueKeys": ["CEGBUPOL-6103"],
                        "issueCards": [
                            {
                                "issueKey": "CEGBUPOL-6103",
                                "summary": "Removed card",
                                "issueUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-6103",
                                "epicName": "Domain Support Q4",
                                "epicUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-3553",
                                "storyPoints": 3.0,
                                "status": "Done",
                                "statusCategory": "Done",
                            }
                        ],
                    },
                    "blockedCards": {
                        "count": 2,
                        "storyPointsTotal": 8.0,
                        "issueKeys": ["CEGBUPOL-6104", "CEGBUPOL-6105"],
                        "issueCards": [
                            {
                                "issueKey": "CEGBUPOL-6104",
                                "summary": "Blocked card 1",
                                "issueUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-6104",
                                "epicName": "Domain Support Q4",
                                "epicUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-3553",
                                "storyPoints": 5.0,
                                "status": "Blocked",
                                "statusCategory": "In Progress",
                            },
                            {
                                "issueKey": "CEGBUPOL-6105",
                                "summary": "Blocked card 2",
                                "issueUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-6105",
                                "epicName": "Domain Support Q4",
                                "epicUrl": "https://gbujira.oraclecorp.com/browse/CEGBUPOL-3553",
                                "storyPoints": 3.0,
                                "status": "In Progress",
                                "statusCategory": "Blocked",
                            },
                        ],
                    },
                },
                "error": None,
            }

        def fake_team_insights(*, sprint_limit=6, cycle_time_status_keys=None):  # noqa: ANN001
            self.team_insights_calls.append((sprint_limit, cycle_time_status_keys))
            return {
                "source": "local",
                "generatedAt": "2026-03-25T00:00:00+00:00",
                "windowSize": sprint_limit,
                "metrics": {
                    "avgCommittedStoryPoints": 84.0,
                    "avgCompletedStoryPoints": 75.5,
                    "completionRatioPercent": 89.88,
                    "carryoverPercent": 10.12,
                    "avgCycleTimeDays": 4.2,
                    "cycleTimeStdDevDays": 4.6,
                    "medianCycleTimeDays": 3.8,
                },
                "trend": [
                    {
                        "sprintId": 55419,
                        "sprintName": "CEGBU Polaris Sprint 43",
                        "state": "closed",
                        "startDate": "2026-02-20T00:00:00+00:00",
                        "endDate": "2026-03-05T00:00:00+00:00",
                        "committedStoryPoints": 88.0,
                        "completedStoryPoints": 80.0,
                        "avgCycleTimeDays": 3.6,
                        "completionRatioPercent": 90.91,
                        "carryoverPercent": 9.09,
                    }
                ],
                "statusCycleTime": {
                    "trackedIssues": 18,
                    "completedIssues": 18,
                    "excludedIssues": 0,
                    "totalDays": 57.2,
                    "appliedStatusKeys": ["in progress", "in review"],
                    "defaultStatusKeys": ["in progress", "in review"],
                    "availableStatuses": [
                        {
                            "statusKey": "in progress",
                            "status": "In Progress",
                            "statusCategory": "In Progress",
                            "defaultIncluded": True,
                        },
                        {
                            "statusKey": "in review",
                            "status": "In Review",
                            "statusCategory": "In Progress",
                            "defaultIncluded": True,
                        },
                    ],
                    "rows": [
                        {
                            "status": "In Progress",
                            "issueCount": 18,
                            "avgDays": 2.1,
                            "medianDays": 1.8,
                            "p85Days": 3.9,
                            "maxDays": 8.2,
                            "totalDays": 37.5,
                            "percentOfCycleTime": 65.56,
                        },
                        {
                            "status": "In Review",
                            "issueCount": 11,
                            "avgDays": 1.79,
                            "medianDays": 1.4,
                            "p85Days": 2.8,
                            "maxDays": 5.1,
                            "totalDays": 19.7,
                            "percentOfCycleTime": 34.44,
                        },
                    ],
                },
                "workMix": {
                    "sprintId": 55421,
                    "sprintName": "CEGBU Polaris Sprint 45",
                    "totalIssues": 3,
                    "slices": [
                        {"label": "Feature", "count": 2, "percent": 66.67},
                        {"label": "Ops", "count": 1, "percent": 33.33},
                    ],
                },
                "summary": "Work mix is currently Feature 67%, Ops 33%.",
                "error": None,
            }

        def fake_metadata_lookup():
            return {
                "groups": [{"id": 1, "name": "Platform"}],
                "workTypes": [{"id": 10, "name": "Feature"}],
            }

        def fake_add_group(name):  # noqa: ANN001
            self.group_create_calls.append(name)
            return {"id": 2, "name": name}

        def fake_add_work_type(name):  # noqa: ANN001
            self.work_type_create_calls.append(name)
            return {"id": 11, "name": name}

        def fake_update_group(lookup_id, name):  # noqa: ANN001
            self.group_update_calls.append((lookup_id, name))
            return {"id": lookup_id, "name": name}

        def fake_update_work_type(lookup_id, name):  # noqa: ANN001
            self.work_type_update_calls.append((lookup_id, name))
            return {"id": lookup_id, "name": name}

        def fake_delete_group(lookup_id):  # noqa: ANN001
            self.group_delete_calls.append(lookup_id)
            return {"id": lookup_id, "deleted": True, "removedMappings": 1, "removedLookupRows": 1}

        def fake_delete_work_type(lookup_id):  # noqa: ANN001
            self.work_type_delete_calls.append(lookup_id)
            return {"id": lookup_id, "deleted": True, "removedMappings": 1, "removedLookupRows": 1}

        def fake_read_epics(epic_key=None, limit=50):  # noqa: ANN001
            _ = limit
            if epic_key:
                return {
                    "epics": [
                        {
                            "epicKey": epic_key,
                            "epicTitle": "Enable offline initiative scoring",
                            "successCriteria": ["Zero blocker defects"],
                            "timelineEnabled": False,
                            "timelineStartDate": None,
                            "targetCompletionDate": None,
                            "groupIds": [1],
                            "groups": [{"id": 1, "name": "Platform"}],
                            "workTypeIds": [10],
                            "workTypes": [{"id": 10, "name": "Feature"}],
                            "updatedAt": "2026-03-25T00:00:00+00:00",
                        }
                    ]
                }
            return {"epics": []}

        def fake_search_epics(query=None, limit=20):  # noqa: ANN001
            self.epic_candidate_calls.append((query, limit))
            return {
                "epics": [
                    {
                        "epicKey": "CEGBUPOL-5000",
                        "epicName": "Unified Engineering Pulse",
                    }
                ]
            }

        def fake_epic_summary(limit=50, period_start=None, period_end=None, timezone_name=None):  # noqa: ANN001
            self.epic_summary_calls.append((limit, period_start, period_end, timezone_name))
            return {
                "epics": [
                    {
                        "epicKey": "CEGBUPOL-4482",
                        "epicName": "Enable offline initiative scoring",
                        "completedCards": 8,
                        "totalCards": 10,
                        "completionPercent": 80.0,
                        "completedInPeriod": 2,
                        "completedLastWeek": 2,
                        "deltaPercentInPeriod": 20.0,
                        "deltaPercent": 20.0,
                        "groups": [{"id": 1, "name": "Platform"}],
                        "workTypes": [{"id": 10, "name": "Feature"}],
                        "successCriteria": ["Zero blocker defects"],
                        "timelineEnabled": True,
                        "timelineStartDate": "2026-04-01",
                        "targetCompletionDate": "2026-04-15",
                        "ragScore": None,
                        "insightComment": None,
                        "updatedAt": "2026-03-25T00:00:00+00:00",
                    }
                ]
                ,
                "reportingPeriod": {
                    "startDate": "2026-03-01",
                    "endDate": "2026-03-30",
                    "days": 30,
                    "timezone": "Australia/Melbourne",
                },
            }

        def fake_epic_completed_cards(
            epic_key,
            limit=200,
            period_start=None,
            period_end=None,
            timezone_name=None,
        ):  # noqa: ANN001
            self.epic_completed_cards_calls.append((epic_key, limit, period_start, period_end, timezone_name))
            return {
                "source": "local",
                "epicKey": epic_key,
                "epicName": "Enable offline initiative scoring",
                "count": 2,
                "limit": limit,
                "truncated": False,
                "completedCards": [
                    {
                        "issueKey": "CEGBUPOL-6001",
                        "summary": "Completed migration",
                        "status": "Done",
                        "statusCategory": "Done",
                        "storyPoints": 8.0,
                        "assigneeAccountId": "user-dev",
                        "completedAt": "2026-03-25T00:00:00+00:00",
                    },
                    {
                        "issueKey": "CEGBUPOL-6007",
                        "summary": "Cutover cleanup",
                        "status": "Closed",
                        "statusCategory": "Done",
                        "storyPoints": 3.0,
                        "assigneeAccountId": "user-qa",
                        "completedAt": "2026-03-26T00:00:00+00:00",
                    },
                ],
                "reportingPeriod": {
                    "startDate": "2026-03-01",
                    "endDate": "2026-03-30",
                    "days": 30,
                    "timezone": timezone_name or "UTC",
                },
            }

        def fake_configured_completed_cards(limit=300, period_start=None, period_end=None, timezone_name=None):  # noqa: ANN001
            self.configured_completed_cards_calls.append((limit, period_start, period_end, timezone_name))
            return {
                "source": "local",
                "scope": "configured",
                "count": 3,
                "limit": limit,
                "truncated": False,
                "completedCards": [
                    {
                        "issueKey": "CEGBUPOL-7001",
                        "summary": "Harden notification retries",
                        "status": "Done",
                        "statusCategory": "Done",
                        "storyPoints": 5.0,
                        "assigneeAccountId": "user-dev",
                        "completedAt": "2026-03-24T00:00:00+00:00",
                        "epicKey": "CEGBUPOL-4482",
                        "epicName": "Enable offline initiative scoring",
                    },
                    {
                        "issueKey": "CEGBUPOL-7002",
                        "summary": "Reduce flaky e2e checks",
                        "status": "Done",
                        "statusCategory": "Done",
                        "storyPoints": 3.0,
                        "assigneeAccountId": "user-qa",
                        "completedAt": "2026-03-25T00:00:00+00:00",
                        "epicKey": "CEGBUPOL-3553",
                        "epicName": "Domain Support Q4",
                    },
                    {
                        "issueKey": "CEGBUPOL-7003",
                        "summary": "Tighten rollout guardrails",
                        "status": "Closed",
                        "statusCategory": "Done",
                        "storyPoints": 2.0,
                        "assigneeAccountId": "user-dev",
                        "completedAt": "2026-03-26T00:00:00+00:00",
                        "epicKey": "CEGBUPOL-3553",
                        "epicName": "Domain Support Q4",
                    },
                ],
                "perEpicCounts": {"CEGBUPOL-4482": 1, "CEGBUPOL-3553": 2},
                "reportingPeriod": {
                    "startDate": "2026-03-01",
                    "endDate": "2026-03-30",
                    "days": 30,
                    "timezone": timezone_name or "UTC",
                },
            }

        def fake_upsert_epic(**kwargs):  # noqa: ANN003
            self.epic_upsert_calls.append(kwargs)
            return {
                "epicKey": kwargs["epic_key"],
                "successCriteria": kwargs.get("success_criteria") or [],
                "timelineEnabled": bool(kwargs.get("timeline_enabled")),
                "timelineStartDate": kwargs.get("timeline_start_date"),
                "targetCompletionDate": kwargs.get("target_completion_date"),
                "groupIds": kwargs.get("group_ids") or [],
                "groups": [{"id": 1, "name": "Platform"}],
                "workTypeIds": kwargs.get("work_type_ids") or [],
                "workTypes": [{"id": 10, "name": "Feature"}],
                "updatedAt": "2026-03-25T00:00:00+00:00",
            }

        def fake_delete_epic(epic_key):  # noqa: ANN001
            self.epic_delete_calls.append(epic_key)
            return {
                "epicKey": epic_key,
                "deleted": True,
                "removedGroupMappings": 1,
                "removedWorkTypeMappings": 1,
                "removedMetadataRows": 1,
            }

        handler_cls = build_handler(
            jira_status_provider=fake_status,
            jira_sync_status_provider=fake_sync_status,
            jira_sync_start_provider=fake_sync_start,
            jira_sync_history_provider=fake_sync_history,
            issue_search_provider=fake_issue_search,
            current_sprint_provider=fake_current_sprint,
            current_sprint_changes_provider=fake_current_sprint_changes,
            current_sprint_work_provider=fake_current_sprint_work,
            team_insights_provider=fake_team_insights,
            release_insights_provider=fake_release_insights,
            metadata_lookup_provider=fake_metadata_lookup,
            metadata_add_group_provider=fake_add_group,
            metadata_add_work_type_provider=fake_add_work_type,
            metadata_update_group_provider=fake_update_group,
            metadata_delete_group_provider=fake_delete_group,
            metadata_update_work_type_provider=fake_update_work_type,
            metadata_delete_work_type_provider=fake_delete_work_type,
            metadata_read_epics_provider=fake_read_epics,
            metadata_summary_provider=fake_epic_summary,
            metadata_completed_cards_provider=fake_epic_completed_cards,
            metadata_configured_completed_cards_provider=fake_configured_completed_cards,
            metadata_search_epics_provider=fake_search_epics,
            metadata_upsert_epic_provider=fake_upsert_epic,
            metadata_delete_epic_provider=fake_delete_epic,
            confluence_status_provider=fake_confluence_status,
            ai_status_provider=fake_ai_status,
            ai_chat_provider=fake_ai_chat,
            oci_genai_status_provider=fake_oci_status,
            release_refresh_status_provider=fake_release_refresh_status,
            release_refresh_result_provider=fake_release_refresh_result,
            release_refresh_start_provider=fake_release_refresh_start,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_health_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/health", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["status"], "ok")

    def test_openapi_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/openapi.json", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            self.assertIn("application/json", response.headers.get("Content-Type", ""))
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["openapi"], "3.0.3")
        self.assertEqual(body["info"]["title"], "TeamBeacon Local API")
        self.assertIn("/api/ai/chat", body["paths"])
        self.assertIn("/api/integrations/ai/status", body["paths"])
        self.assertIn("/api/integrations/confluence/status", body["paths"])
        self.assertIn("/api/releases/insights", body["paths"])
        self.assertIn("/api/releases/refresh/start", body["paths"])
        self.assertIn("/api/releases/refresh/status", body["paths"])
        self.assertIn("/api/releases/refresh/result", body["paths"])
        self.assertIn("/api/team/insights", body["paths"])
        self.assertIn("/api/metadata/epics/summary", body["paths"])
        self.assertIn("/api/metadata/epics/completed-cards", body["paths"])
        self.assertIn("/api/metadata/epics/completed-cards/configured", body["paths"])
        self.assertEqual(body["servers"][0]["url"], self.base_url)

        team_insights_get = body["paths"]["/api/team/insights"]["get"]
        sprint_limit_param = next(
            (parameter for parameter in team_insights_get.get("parameters", []) if parameter.get("name") == "sprintLimit"),
            None,
        )
        cycle_time_mode_param = next(
            (parameter for parameter in team_insights_get.get("parameters", []) if parameter.get("name") == "cycleTimeStatusMode"),
            None,
        )
        cycle_time_status_param = next(
            (parameter for parameter in team_insights_get.get("parameters", []) if parameter.get("name") == "cycleTimeStatus"),
            None,
        )
        self.assertIsNotNone(sprint_limit_param)
        self.assertIsNotNone(cycle_time_mode_param)
        self.assertIsNotNone(cycle_time_status_param)
        sprint_limit_schema = sprint_limit_param["schema"]
        self.assertEqual(sprint_limit_schema["type"], "integer")
        self.assertEqual(sprint_limit_schema["minimum"], 1)
        self.assertEqual(sprint_limit_schema["maximum"], 12)
        self.assertEqual(sprint_limit_schema["default"], 6)
        self.assertIn("UI presets are 1, 2, 3, 4, 6, 8, 10, and 12.", sprint_limit_param["description"])

    def test_docs_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/docs", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers.get("Content-Type", ""))
            body = response.read().decode("utf-8")

        self.assertIn("TeamBeacon Local API - Swagger UI", body)
        self.assertIn("SwaggerUIBundle", body)
        self.assertIn("/openapi.json", body)

    def test_docs_alias_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/docs", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers.get("Content-Type", ""))

    def test_jira_status_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/integrations/jira/status", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertTrue(body["connected"])
        self.assertEqual(body["sampleIssueKey"], "CEGBUPOL-1")
        self.assertEqual(body["metrics"]["boardCount"], 1)

    def test_jira_sync_status_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/integrations/jira/sync/status", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["state"], "idle")
        self.assertEqual(body["downloadedIssues"], 0)
        self.assertEqual(body["lastSyncedAt"], "2026-03-25T00:00:00+00:00")

    def test_jira_sync_start_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/integrations/jira/sync/start",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"mode": "since_last"}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 202)
            body = json.loads(response.read().decode("utf-8"))
        self.assertTrue(body["started"])
        self.assertEqual(body["state"], "running")
        self.assertEqual(body["syncMode"], "since_last")
        self.assertEqual(body["downloadedIssues"], 12)
        self.assertEqual(body["totalIssues"], 5000)
        self.assertEqual(self.sync_start_calls[-1], ("since_last", None))

    def test_jira_sync_start_endpoint_since_date_mode(self) -> None:
        request = Request(
            f"{self.base_url}/api/integrations/jira/sync/start",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"mode": "since_date", "sinceDate": "2026-03-01"}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 202)
            body = json.loads(response.read().decode("utf-8"))
        self.assertTrue(body["started"])
        self.assertEqual(body["syncMode"], "since_date")
        self.assertEqual(body["requestedSince"], "2026-03-01")
        self.assertEqual(self.sync_start_calls[-1], ("since_date", "2026-03-01"))

    def test_jira_sync_start_endpoint_rejects_invalid_mode(self) -> None:
        request = Request(
            f"{self.base_url}/api/integrations/jira/sync/start",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"mode": "invalid"}).encode("utf-8"),
        )
        with self.assertRaises(HTTPError) as exc_ctx:
            urlopen(request, timeout=5)  # noqa: S310
        self.assertEqual(exc_ctx.exception.code, 400)

    def test_jira_sync_history_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/integrations/jira/sync/history?limit=10", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["source"], "jira")
        self.assertEqual(len(body["history"]), 1)
        self.assertEqual(body["history"][0]["boardName"], "CEGBU Polaris")
        self.assertEqual(body["history"][0]["syncMode"], "since_last")
        self.assertEqual(body["history"][0]["issuesSynced"], 5000)

    def test_oci_genai_status_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/integrations/oci-genai/status", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["source"], "oci_genai")
        self.assertTrue(body["connected"])
        self.assertEqual(body["config"]["modelId"], "cohere.command-r-08-2024")
        self.assertEqual(len(body["checks"]), 2)

    def test_ai_status_endpoint_uses_configured_provider_by_default(self) -> None:
        with urlopen(f"{self.base_url}/api/integrations/ai/status", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["source"], "oci_genai")
        self.assertEqual(body["provider"], "oci")
        self.assertEqual(self.ai_status_calls[-1], None)

    def test_ai_status_endpoint_supports_provider_override(self) -> None:
        with urlopen(f"{self.base_url}/api/integrations/ai/status?provider=ollama", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["source"], "ollama")
        self.assertEqual(body["provider"], "ollama")
        self.assertEqual(self.ai_status_calls[-1], "ollama")

    def test_confluence_status_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/integrations/confluence/status", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["source"], "confluence")
        self.assertTrue(body["connected"])
        self.assertEqual(body["config"]["baseUrl"], "https://gbuconfluence.oraclecorp.com")
        self.assertEqual(body["metrics"]["spaceCount"], 1)

    def test_release_refresh_status_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/releases/refresh/status", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["source"], "releases")
        self.assertEqual(body["state"], "completed")
        self.assertEqual(body["percent"], 100.0)
        self.assertEqual(len(body["sources"]), 1)

    def test_release_insights_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/releases/insights?releaseLimit=6&projectKey=CEGBUPOL", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["source"], "local")
        self.assertEqual(body["projectKey"], "CEGBUPOL")
        self.assertEqual(body["metrics"]["ongoingCount"], 1)
        self.assertEqual(body["metrics"]["avgCycleTimeDays"], 25.0)
        self.assertEqual(self.release_insights_calls[-1], (6, "CEGBUPOL"))

    def test_release_refresh_result_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/releases/refresh/result", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["source"], "releases")
        self.assertEqual(body["state"], "completed")
        self.assertIn("<h4>Summary</h4>", body["html"])
        self.assertEqual(body["sources"][0]["title"], "Release Notes")

    def test_release_refresh_start_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/releases/refresh/start",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "sources": [
                        {
                            "confluenceUrl": "https://gbuconfluence.oraclecorp.com/display/SEN/Release+Notes",
                            "prompt": "Summarize release scope and risks.",
                        }
                    ],
                    "overallPrompt": "Generate release narrative for engineering leaders.",
                }
            ).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 202)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "releases")
        self.assertTrue(body["started"])
        self.assertEqual(body["state"], "running")
        self.assertEqual(len(self.release_refresh_start_calls), 1)
        self.assertEqual(
            self.release_refresh_start_calls[0]["overall_prompt"],
            "Generate release narrative for engineering leaders.",
        )

    def test_release_refresh_start_endpoint_rejects_missing_sources(self) -> None:
        request = Request(
            f"{self.base_url}/api/releases/refresh/start",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "overallPrompt": "Generate release narrative for engineering leaders.",
                }
            ).encode("utf-8"),
        )
        with self.assertRaises(HTTPError) as exc_ctx:
            urlopen(request, timeout=5)  # noqa: S310
        self.assertEqual(exc_ctx.exception.code, 400)

    def test_oci_genai_chat_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/ai/chat",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "message": "Summarize blockers from this sprint.",
                    "maxTokens": 300,
                    "temperature": 0.3,
                    "topP": 0.8,
                    "topK": 5,
                    "frequencyPenalty": 0.2,
                }
            ).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "oci_genai")
        self.assertIn("TeamBeacon", body["response"]["text"])
        self.assertEqual(self.oci_chat_calls[-1]["message"], "Summarize blockers from this sprint.")
        self.assertEqual(self.oci_chat_calls[-1]["max_tokens"], 300)
        self.assertEqual(self.oci_chat_calls[-1]["temperature"], 0.3)
        self.assertEqual(self.oci_chat_calls[-1]["top_p"], 0.8)
        self.assertEqual(self.oci_chat_calls[-1]["top_k"], 5)
        self.assertEqual(self.oci_chat_calls[-1]["frequency_penalty"], 0.2)
        self.assertEqual(self.oci_chat_calls[-1]["provider"], None)

    def test_ai_chat_endpoint_supports_provider_override(self) -> None:
        request = Request(
            f"{self.base_url}/api/ai/chat",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "provider": "ollama",
                    "message": "Summarize blockers from this sprint.",
                }
            ).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "ollama")
        self.assertEqual(body["provider"], "ollama")
        self.assertEqual(self.oci_chat_calls[-1]["provider"], "ollama")

    def test_oci_genai_chat_endpoint_rejects_non_numeric_temperature(self) -> None:
        request = Request(
            f"{self.base_url}/api/ai/chat",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "message": "Summarize blockers from this sprint.",
                    "temperature": "hot",
                }
            ).encode("utf-8"),
        )
        with self.assertRaises(HTTPError) as exc_ctx:
            urlopen(request, timeout=5)  # noqa: S310
        self.assertEqual(exc_ctx.exception.code, 400)

    def test_issue_search_endpoint(self) -> None:
        with urlopen(
            f"{self.base_url}/api/issues/search?epicKey=CEGBUPOL-4482&workedBy=user-qa&limit=25",
            timeout=5,
        ) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "local")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["issues"][0]["issueKey"], "CEGBUPOL-101")
        self.assertEqual(body["issues"][0]["contributors"], ["user-dev", "user-qa"])

        self.assertEqual(len(self.issue_search_calls), 1)
        call = self.issue_search_calls[0]
        self.assertEqual(call["epic_key"], "CEGBUPOL-4482")
        self.assertEqual(call["worked_by"], "user-qa")
        self.assertEqual(call["limit"], 25)

    def test_current_sprint_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/sprints/current", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "local")
        self.assertEqual(body["sprint"]["id"], 55421)
        self.assertEqual(body["sprint"]["boardId"], 27193)
        self.assertEqual(body["sprint"]["name"], "CEGBU Polaris Sprint 45")
        self.assertEqual(body["sprint"]["state"], "active")
        self.assertEqual(body["sprint"]["remainingDays"], 5)
        self.assertEqual(len(self.current_sprint_calls), 1)

    def test_current_sprint_work_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/sprints/current/work", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "local")
        self.assertEqual(body["sprint"]["id"], 55421)
        self.assertEqual(body["work"]["totals"]["done"], 1)
        self.assertEqual(body["work"]["totals"]["inProgress"], 1)
        self.assertEqual(body["work"]["totals"]["planned"], 1)
        self.assertEqual(body["work"]["totals"]["total"], 3)
        self.assertEqual(body["work"]["totals"]["storyPoints"]["done"], 8.0)
        self.assertEqual(body["work"]["totals"]["storyPoints"]["inProgress"], 5.0)
        self.assertEqual(body["work"]["totals"]["storyPoints"]["planned"], 3.0)
        self.assertEqual(body["work"]["totals"]["storyPoints"]["total"], 16.0)
        self.assertEqual(body["work"]["done"][0]["issueKey"], "CEGBUPOL-6001")
        self.assertEqual(body["work"]["done"][0]["storyPoints"], 8.0)
        self.assertEqual(body["work"]["done"][0]["epicName"], "Platform Reliability Epic")
        self.assertEqual(body["work"]["inProgress"][0]["issueKey"], "CEGBUPOL-6002")
        self.assertEqual(body["work"]["inProgress"][0]["storyPoints"], 5.0)
        self.assertEqual(body["work"]["inProgress"][0]["epicName"], "Platform Reliability Epic")
        self.assertEqual(body["work"]["planned"][0]["issueKey"], "CEGBUPOL-6003")
        self.assertEqual(body["work"]["planned"][0]["storyPoints"], 3.0)
        self.assertEqual(body["work"]["planned"][0]["epicName"], "Platform Reliability Epic")
        self.assertEqual(len(self.current_sprint_work_calls), 1)

    def test_current_sprint_changes_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/sprints/current/changes", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "local")
        self.assertEqual(body["sprint"]["id"], 55421)
        self.assertEqual(body["changes"]["addedAfterStart"]["count"], 4)
        self.assertEqual(body["changes"]["addedAfterStart"]["storyPointsTotal"], 11.0)
        self.assertEqual(body["changes"]["addedAfterStart"]["issueKeys"], ["CEGBUPOL-6101", "CEGBUPOL-6102"])
        self.assertEqual(body["changes"]["addedAfterStart"]["issueCards"][0]["issueKey"], "CEGBUPOL-6101")
        self.assertEqual(body["changes"]["addedAfterStart"]["issueCards"][0]["summary"], "Added card 1")
        self.assertEqual(body["changes"]["addedAfterStart"]["issueCards"][0]["epicName"], "Domain Support Q4")
        self.assertEqual(body["changes"]["addedAfterStart"]["issueCards"][0]["storyPoints"], 2.0)
        self.assertEqual(body["changes"]["addedAfterStart"]["issueCards"][0]["status"], "In Progress")
        self.assertEqual(body["changes"]["addedAfterStart"]["issueCards"][0]["statusCategory"], "In Progress")
        self.assertEqual(body["changes"]["removedAfterStart"]["count"], 1)
        self.assertEqual(body["changes"]["removedAfterStart"]["storyPointsTotal"], 3.0)
        self.assertEqual(body["changes"]["removedAfterStart"]["issueKeys"], ["CEGBUPOL-6103"])
        self.assertEqual(body["changes"]["removedAfterStart"]["issueCards"][0]["issueKey"], "CEGBUPOL-6103")
        self.assertEqual(body["changes"]["removedAfterStart"]["issueCards"][0]["epicName"], "Domain Support Q4")
        self.assertEqual(body["changes"]["removedAfterStart"]["issueCards"][0]["storyPoints"], 3.0)
        self.assertEqual(body["changes"]["removedAfterStart"]["issueCards"][0]["status"], "Done")
        self.assertEqual(body["changes"]["blockedCards"]["count"], 2)
        self.assertEqual(body["changes"]["blockedCards"]["storyPointsTotal"], 8.0)
        self.assertEqual(body["changes"]["blockedCards"]["issueKeys"], ["CEGBUPOL-6104", "CEGBUPOL-6105"])
        self.assertEqual(body["changes"]["blockedCards"]["issueCards"][0]["issueKey"], "CEGBUPOL-6104")
        self.assertEqual(body["changes"]["blockedCards"]["issueCards"][0]["epicName"], "Domain Support Q4")
        self.assertEqual(body["changes"]["blockedCards"]["issueCards"][0]["storyPoints"], 5.0)
        self.assertEqual(body["changes"]["blockedCards"]["issueCards"][0]["status"], "Blocked")
        self.assertEqual(body["changes"]["blockedCards"]["issueCards"][0]["statusCategory"], "In Progress")
        self.assertEqual(len(self.current_sprint_changes_calls), 1)

    def test_team_insights_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/team/insights", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "local")
        self.assertEqual(body["windowSize"], 6)
        self.assertEqual(body["metrics"]["avgCommittedStoryPoints"], 84.0)
        self.assertEqual(body["metrics"]["avgCycleTimeDays"], 4.2)
        self.assertEqual(body["metrics"]["cycleTimeStdDevDays"], 4.6)
        self.assertEqual(body["statusCycleTime"]["trackedIssues"], 18)
        self.assertEqual(body["statusCycleTime"]["rows"][0]["status"], "In Progress")
        self.assertEqual(body["workMix"]["sprintId"], 55421)
        self.assertEqual(body["trend"][0]["sprintName"], "CEGBU Polaris Sprint 43")
        self.assertEqual(body["trend"][0]["avgCycleTimeDays"], 3.6)
        self.assertEqual(self.team_insights_calls[-1], (6, None))

    def test_team_insights_endpoint_supports_sprint_limit(self) -> None:
        with urlopen(f"{self.base_url}/api/team/insights?sprintLimit=4", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["windowSize"], 4)
        self.assertEqual(self.team_insights_calls[-1], (4, None))

    def test_metadata_lookup_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/metadata/lookup", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["groups"][0]["name"], "Platform")
        self.assertEqual(body["workTypes"][0]["name"], "Feature")

    def test_metadata_add_group_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/lookup/groups",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"name": "Operations"}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["name"], "Operations")
        self.assertEqual(self.group_create_calls[-1], "Operations")

    def test_metadata_add_work_type_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/lookup/work-types",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"name": "Run"}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["name"], "Run")
        self.assertEqual(self.work_type_create_calls[-1], "Run")

    def test_metadata_update_group_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/lookup/groups/update",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"id": 1, "name": "Platform Core"}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["id"], 1)
        self.assertEqual(body["name"], "Platform Core")
        self.assertEqual(self.group_update_calls[-1], (1, "Platform Core"))

    def test_metadata_delete_group_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/lookup/groups/delete",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"id": 1}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["id"], 1)
        self.assertTrue(body["deleted"])
        self.assertEqual(self.group_delete_calls[-1], 1)

    def test_metadata_update_work_type_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/lookup/work-types/update",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"id": 10, "name": "Feature+Run"}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["id"], 10)
        self.assertEqual(body["name"], "Feature+Run")
        self.assertEqual(self.work_type_update_calls[-1], (10, "Feature+Run"))

    def test_metadata_delete_work_type_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/lookup/work-types/delete",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"id": 10}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["id"], 10)
        self.assertTrue(body["deleted"])
        self.assertEqual(self.work_type_delete_calls[-1], 10)

    def test_metadata_upsert_epic_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/epics",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "epicKey": "CEGBUPOL-4482",
                    "successCriteria": ["Zero blocker defects"],
                    "timelineEnabled": True,
                    "timelineStartDate": "2026-04-01",
                    "targetCompletionDate": "2026-04-15",
                    "groupIds": [1],
                    "workTypeIds": [10],
                }
            ).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["epicKey"], "CEGBUPOL-4482")
        self.assertTrue(body["timelineEnabled"])
        self.assertEqual(body["timelineStartDate"], "2026-04-01")
        self.assertEqual(body["targetCompletionDate"], "2026-04-15")
        self.assertEqual(body["groupIds"], [1])
        self.assertEqual(body["workTypeIds"], [10])
        self.assertEqual(self.epic_upsert_calls[-1]["epic_key"], "CEGBUPOL-4482")
        self.assertTrue(self.epic_upsert_calls[-1]["timeline_enabled"])
        self.assertEqual(self.epic_upsert_calls[-1]["timeline_start_date"], "2026-04-01")
        self.assertEqual(self.epic_upsert_calls[-1]["target_completion_date"], "2026-04-15")

    def test_metadata_upsert_epic_endpoint_rejects_non_boolean_timeline_flag(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/epics",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "epicKey": "CEGBUPOL-4482",
                    "successCriteria": ["Zero blocker defects"],
                    "timelineEnabled": "yes",
                    "groupIds": [1],
                    "workTypeIds": [10],
                }
            ).encode("utf-8"),
        )
        with self.assertRaises(HTTPError) as exc_ctx:
            urlopen(request, timeout=5)  # noqa: S310
        self.assertEqual(exc_ctx.exception.code, 400)

    def test_metadata_completed_cards_endpoint(self) -> None:
        with urlopen(
            f"{self.base_url}/api/metadata/epics/completed-cards?epicKey=CEGBUPOL-4482&limit=25&periodStart=2026-03-01&periodEnd=2026-03-30&timezone=Australia/Melbourne",
            timeout=5,
        ) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "local")
        self.assertEqual(body["epicKey"], "CEGBUPOL-4482")
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["completedCards"]), 2)
        self.assertEqual(body["completedCards"][0]["issueKey"], "CEGBUPOL-6001")
        self.assertEqual(
            self.epic_completed_cards_calls[-1],
            ("CEGBUPOL-4482", 25, "2026-03-01", "2026-03-30", "Australia/Melbourne"),
        )

    def test_metadata_completed_cards_endpoint_requires_epic_key(self) -> None:
        with self.assertRaises(HTTPError) as exc_ctx:
            urlopen(f"{self.base_url}/api/metadata/epics/completed-cards", timeout=5)  # noqa: S310
        self.assertEqual(exc_ctx.exception.code, 400)

    def test_metadata_completed_cards_configured_endpoint(self) -> None:
        with urlopen(
            f"{self.base_url}/api/metadata/epics/completed-cards/configured?limit=50&periodStart=2026-03-01&periodEnd=2026-03-30&timezone=Australia/Melbourne",
            timeout=5,
        ) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(body["source"], "local")
        self.assertEqual(body["scope"], "configured")
        self.assertEqual(body["count"], 3)
        self.assertEqual(len(body["completedCards"]), 3)
        self.assertEqual(body["perEpicCounts"]["CEGBUPOL-3553"], 2)
        self.assertEqual(
            self.configured_completed_cards_calls[-1],
            (50, "2026-03-01", "2026-03-30", "Australia/Melbourne"),
        )

    def test_metadata_upsert_epic_endpoint_rejects_non_string_timeline_start_date(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/epics",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "epicKey": "CEGBUPOL-4482",
                    "successCriteria": ["Zero blocker defects"],
                    "timelineEnabled": True,
                    "timelineStartDate": 20260401,
                    "targetCompletionDate": "2026-04-15",
                    "groupIds": [1],
                    "workTypeIds": [10],
                }
            ).encode("utf-8"),
        )
        with self.assertRaises(HTTPError) as exc_ctx:
            urlopen(request, timeout=5)  # noqa: S310
        self.assertEqual(exc_ctx.exception.code, 400)

    def test_metadata_upsert_epic_endpoint_rejects_multiple_groups(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/epics",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "epicKey": "CEGBUPOL-4482",
                    "successCriteria": ["Zero blocker defects"],
                    "groupIds": [1, 2],
                    "workTypeIds": [10],
                }
            ).encode("utf-8"),
        )
        with self.assertRaises(HTTPError) as exc_ctx:
            urlopen(request, timeout=5)  # noqa: S310
        self.assertEqual(exc_ctx.exception.code, 400)

    def test_metadata_upsert_epic_endpoint_rejects_multiple_work_types(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/epics",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "epicKey": "CEGBUPOL-4482",
                    "successCriteria": ["Zero blocker defects"],
                    "groupIds": [1],
                    "workTypeIds": [10, 11],
                }
            ).encode("utf-8"),
        )
        with self.assertRaises(HTTPError) as exc_ctx:
            urlopen(request, timeout=5)  # noqa: S310
        self.assertEqual(exc_ctx.exception.code, 400)

    def test_metadata_delete_epic_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/metadata/epics/delete",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"epicKey": "CEGBUPOL-4482"}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["epicKey"], "CEGBUPOL-4482")
        self.assertTrue(body["deleted"])
        self.assertEqual(body["removedMetadataRows"], 1)
        self.assertEqual(self.epic_delete_calls[-1], "CEGBUPOL-4482")

    def test_metadata_read_epic_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/metadata/epics?epicKey=CEGBUPOL-4482", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(len(body["epics"]), 1)
        self.assertEqual(body["epics"][0]["epicKey"], "CEGBUPOL-4482")
        self.assertEqual(body["epics"][0]["epicTitle"], "Enable offline initiative scoring")
        self.assertFalse(body["epics"][0]["timelineEnabled"])
        self.assertIsNone(body["epics"][0]["timelineStartDate"])
        self.assertIsNone(body["epics"][0]["targetCompletionDate"])

    def test_metadata_search_epic_candidates_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/metadata/epics/candidates?q=pulse&limit=12", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(len(body["epics"]), 1)
        self.assertEqual(body["epics"][0]["epicKey"], "CEGBUPOL-5000")
        self.assertEqual(body["epics"][0]["epicName"], "Unified Engineering Pulse")
        self.assertEqual(self.epic_candidate_calls[-1], ("pulse", 12))

    def test_metadata_epic_summary_endpoint(self) -> None:
        with urlopen(  # noqa: S310
            f"{self.base_url}/api/metadata/epics/summary?limit=30&periodStart=2026-03-01&periodEnd=2026-03-30&timezone=Australia%2FMelbourne",
            timeout=5,
        ) as response:
            self.assertEqual(response.status, 200)
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(len(body["epics"]), 1)
        self.assertEqual(body["epics"][0]["epicKey"], "CEGBUPOL-4482")
        self.assertEqual(body["epics"][0]["completionPercent"], 80.0)
        self.assertEqual(body["epics"][0]["groups"][0]["name"], "Platform")
        self.assertEqual(body["epics"][0]["workTypes"][0]["name"], "Feature")
        self.assertEqual(body["epics"][0]["successCriteria"][0], "Zero blocker defects")
        self.assertTrue(body["epics"][0]["timelineEnabled"])
        self.assertEqual(body["epics"][0]["timelineStartDate"], "2026-04-01")
        self.assertEqual(body["epics"][0]["targetCompletionDate"], "2026-04-15")
        self.assertEqual(body["epics"][0]["completedInPeriod"], 2)
        self.assertEqual(body["epics"][0]["completedLastWeek"], 2)
        self.assertEqual(body["epics"][0]["deltaPercentInPeriod"], 20.0)
        self.assertEqual(body["epics"][0]["deltaPercent"], 20.0)
        self.assertEqual(body["reportingPeriod"]["startDate"], "2026-03-01")
        self.assertEqual(body["reportingPeriod"]["endDate"], "2026-03-30")
        self.assertEqual(body["reportingPeriod"]["timezone"], "Australia/Melbourne")
        self.assertIsNone(body["epics"][0]["ragScore"])
        self.assertEqual(
            self.epic_summary_calls[-1],
            (30, "2026-03-01", "2026-03-30", "Australia/Melbourne"),
        )


class LocalApiStaticWebIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.web_root = Path(self._temp_dir.name)
        (self.web_root / "index.html").write_text(
            "<!doctype html><html><body><app-root>TeamBeacon</app-root></body></html>",
            encoding="utf-8",
        )
        assets_dir = self.web_root / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / "app.js").write_text("console.log('teambeacon');", encoding="utf-8")

        handler = build_handler(web_dir=self.web_root)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server_port = self.httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.server_port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self._temp_dir.cleanup()

    def test_serves_index_at_root(self) -> None:
        with urlopen(f"{self.base_url}/", timeout=5) as response:  # noqa: S310
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("<app-root>TeamBeacon</app-root>", body)

    def test_serves_static_asset(self) -> None:
        with urlopen(f"{self.base_url}/assets/app.js", timeout=5) as response:  # noqa: S310
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("teambeacon", body)

    def test_spa_fallback_serves_index_html(self) -> None:
        with urlopen(f"{self.base_url}/initiative-insights", timeout=5) as response:  # noqa: S310
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("<app-root>TeamBeacon</app-root>", body)

    def test_unknown_api_path_still_returns_404(self) -> None:
        with self.assertRaises(HTTPError) as exc_ctx:
            urlopen(f"{self.base_url}/api/unknown", timeout=5)  # noqa: S310
        self.assertEqual(exc_ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
