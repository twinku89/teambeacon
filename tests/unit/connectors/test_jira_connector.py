from __future__ import annotations

from io import BytesIO
import unittest
from datetime import datetime, timezone
from urllib.error import HTTPError
from unittest.mock import patch

from packages.connectors.interfaces import ConnectorConfig
from packages.connectors.jira_rest_stub import JiraAPIError, JiraRestConnector
from packages.connectors.models import SyncBatch


class FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:  # noqa: ANN001
        return False

    def read(self) -> bytes:
        return self.body


def make_http_error(status_code: int, body: bytes = b"") -> HTTPError:
    return HTTPError(
        "https://jira.example.com/rest/api/2/search",
        status_code,
        "HTTP failure",
        hdrs=None,
        fp=BytesIO(body),
    )


class JiraConnectorUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = JiraRestConnector(
            config=ConnectorConfig(base_url="https://jira.example.com", pat_token="token-123"),
            project_key="CEGBUPOL",
            story_points_field="customfield_10004",
        )

    def test_search_issues_maps_fields_and_paginates(self) -> None:
        payload = {
            "startAt": 0,
            "maxResults": 1,
            "total": 2,
            "issues": [
                {
                    "id": "101",
                    "key": "CEGBUPOL-101",
                    "fields": {
                        "project": {"key": "CEGBUPOL"},
                        "issuetype": {"name": "Story"},
                        "summary": "Add retry logic",
                        "status": {"name": "In Progress", "statusCategory": {"name": "In Progress"}},
                        "priority": {"name": "High"},
                        "assignee": {"accountId": "abc123"},
                        "reporter": {"accountId": "xyz999"},
                        "labels": ["ops", "release"],
                        "components": [{"name": "api"}],
                        "fixVersions": [
                            {
                                "id": "26000",
                                "name": "Search 26.3",
                                "archived": False,
                                "released": True,
                                "releaseDate": "2026-03-31",
                            }
                        ],
                        "created": "2026-03-20T10:00:00.000+0000",
                        "updated": "2026-03-21T11:00:00.000+0000",
                        "resolutiondate": None,
                        "customfield_10004": "8",
                        "sprint": {"id": 555},
                        "customfield_10014": "CEGBUPOL-1",
                        "parent": {"key": "CEGBUPOL-100"},
                    },
                }
            ],
        }
        with patch.object(self.connector, "_request_json", return_value=payload) as mocked:
            issues, batch = self.connector.search_issues(
                jql="project = CEGBUPOL ORDER BY updated DESC",
                start_at=0,
                max_results=1,
            )

        self.assertEqual(mocked.call_count, 1)
        call_args = mocked.call_args
        self.assertEqual(call_args.args[0], "/rest/api/2/search")
        self.assertEqual(call_args.kwargs["params"]["startAt"], 0)
        self.assertEqual(call_args.kwargs["params"]["maxResults"], 1)

        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.issue_key, "CEGBUPOL-101")
        self.assertEqual(issue.story_points, 8.0)
        self.assertEqual(issue.sprint_external_id, 555)
        self.assertEqual(issue.epic_key, "CEGBUPOL-1")
        self.assertEqual(issue.parent_issue_key, "CEGBUPOL-100")
        self.assertEqual(issue.components, ["api"])
        self.assertEqual(issue.labels, ["ops", "release"])
        self.assertEqual(len(issue.fix_versions), 1)
        self.assertEqual(issue.fix_versions[0].version_id, "26000")
        self.assertEqual(issue.fix_versions[0].name, "Search 26.3")
        self.assertTrue(issue.fix_versions[0].released)
        self.assertTrue(batch.has_more)
        self.assertEqual(batch.next_cursor, "1")

    def test_search_issues_extracts_sprint_id_from_custom_sprint_field(self) -> None:
        payload = {
            "startAt": 0,
            "maxResults": 1,
            "total": 1,
            "issues": [
                {
                    "id": "102",
                    "key": "CEGBUPOL-102",
                    "fields": {
                        "project": {"key": "CEGBUPOL"},
                        "issuetype": {"name": "Story"},
                        "summary": "Sprint custom field mapping",
                        "status": {"name": "To Do", "statusCategory": {"name": "To Do"}},
                        "priority": {"name": "Medium"},
                        "assignee": {"accountId": "abc123"},
                        "reporter": {"accountId": "xyz999"},
                        "customfield_10004": "5",
                        "customfield_10901": [
                            "com.atlassian.greenhopper.service.sprint.Sprint@abcd[id=106412,rapidViewId=27193,state=ACTIVE,name=Sprint 2]"
                        ],
                        "customfield_10014": "CEGBUPOL-1",
                    },
                }
            ],
        }

        with patch.object(self.connector, "_request_json", return_value=payload):
            issues, batch = self.connector.search_issues(
                jql="project = CEGBUPOL ORDER BY updated DESC",
                start_at=0,
                max_results=1,
            )

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].sprint_external_id, 106412)
        self.assertFalse(batch.has_more)

    def test_incremental_issues_builds_project_scoped_jql(self) -> None:
        expected = ([], SyncBatch(next_cursor=None, has_more=False))
        with patch.object(self.connector, "search_issues", return_value=expected) as mocked:
            self.connector.incremental_issues(
                updated_since=datetime(2026, 3, 22, 14, 30, tzinfo=timezone.utc),
                start_at=5,
                max_results=25,
            )

        self.assertEqual(mocked.call_count, 1)
        jql = mocked.call_args.kwargs["jql"]
        self.assertIn("project = CEGBUPOL", jql)
        self.assertIn("updated >=", jql)
        self.assertTrue(jql.endswith("ORDER BY updated ASC"))
        self.assertEqual(mocked.call_args.kwargs["start_at"], 5)
        self.assertEqual(mocked.call_args.kwargs["max_results"], 25)

    def test_count_incremental_issues_returns_total(self) -> None:
        with patch.object(self.connector, "_request_json", return_value={"total": 123}) as mocked:
            total = self.connector.count_incremental_issues(
                updated_since=datetime(2026, 3, 22, 14, 30, tzinfo=timezone.utc),
            )

        self.assertEqual(total, 123)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(mocked.call_args.args[0], "/rest/api/2/search")
        params = mocked.call_args.kwargs["params"]
        self.assertEqual(params["startAt"], 0)
        self.assertEqual(params["maxResults"], 0)
        self.assertIn("project = CEGBUPOL", params["jql"])
        self.assertIn("updated >=", params["jql"])

    def test_get_boards_handles_pagination(self) -> None:
        page_1 = {
            "isLast": False,
            "total": 3,
            "values": [
                {"id": 1, "name": "Team A", "type": "scrum", "location": {"projectKey": "AAA"}},
                {"id": 2, "name": "Team B", "type": "kanban", "location": {"projectKey": "BBB"}},
            ],
        }
        page_2 = {
            "isLast": True,
            "total": 3,
            "values": [
                {"id": 3, "name": "Team C", "type": "scrum", "location": {"projectKey": "CCC"}},
            ],
        }
        with patch.object(self.connector, "_request_json", side_effect=[page_1, page_2]) as mocked:
            boards = self.connector.get_boards()

        self.assertEqual(len(boards), 3)
        self.assertEqual(boards[0].external_board_id, 1)
        self.assertEqual(boards[2].project_key, "CCC")
        self.assertEqual(mocked.call_count, 2)

    def test_get_board_maps_configured_board(self) -> None:
        payload = {
            "id": 27193,
            "name": "CEGBU Polaris",
            "type": "scrum",
            "location": {"projectKey": "CEGBUPOL"},
        }
        with patch.object(self.connector, "_request_json", return_value=payload) as mocked:
            board = self.connector.get_board(27193)

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(mocked.call_args.args[0], "/rest/agile/1.0/board/27193")
        self.assertEqual(board.external_board_id, 27193)
        self.assertEqual(board.name, "CEGBU Polaris")
        self.assertEqual(board.project_key, "CEGBUPOL")

    def test_get_project_versions_maps_jira_versions(self) -> None:
        payload = [
            {
                "id": "26000",
                "name": "Search 26.3",
                "description": "Quarterly release",
                "archived": False,
                "released": True,
                "startDate": "2026-03-01",
                "releaseDate": "2026-03-31",
            },
            {
                "id": "26001",
                "name": "Q4 FY26 - Tech",
                "archived": False,
                "released": False,
                "startDate": "2026-04-01",
                "releaseDate": "2026-05-30",
            },
        ]
        with patch.object(self.connector, "_request_json", return_value=payload) as mocked:
            versions = self.connector.get_project_versions("CEGBUPOL")

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(mocked.call_args.args[0], "/rest/api/2/project/CEGBUPOL/versions")
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].version_id, "26000")
        self.assertEqual(versions[0].project_key, "CEGBUPOL")
        self.assertEqual(versions[0].name, "Search 26.3")
        self.assertTrue(versions[0].released)
        self.assertIsNotNone(versions[0].start_date)
        self.assertIsNotNone(versions[0].release_date)

    def test_get_issue_changelog_maps_items(self) -> None:
        payload = {
            "changelog": {
                "histories": [
                    {
                        "id": "12",
                        "created": "2026-03-21T03:00:00.000+0000",
                        "author": {"accountId": "user-1"},
                        "items": [
                            {
                                "field": "status",
                                "fromString": "To Do",
                                "toString": "In Progress",
                            },
                            {
                                "field": "assignee",
                                "fromString": "SE 1",
                                "toString": "SE 2",
                            },
                        ],
                    }
                ]
            }
        }
        with patch.object(self.connector, "_request_json", return_value=payload):
            changes = self.connector.get_issue_changelog("CEGBUPOL-101")

        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0].issue_key, "CEGBUPOL-101")
        self.assertEqual(changes[0].field_name, "status")
        self.assertEqual(changes[0].to_value, "In Progress")
        self.assertEqual(changes[1].field_name, "assignee")

    def test_get_board_issues_maps_payload(self) -> None:
        payload = {
            "startAt": 0,
            "maxResults": 1,
            "total": 2,
            "isLast": False,
            "issues": [
                {
                    "id": "301",
                    "key": "CEGBUPOL-301",
                    "fields": {
                        "project": {"key": "CEGBUPOL"},
                        "issuetype": {"name": "Task"},
                        "summary": "Board issue sample",
                        "status": {"name": "To Do", "statusCategory": {"name": "To Do"}},
                        "priority": {"name": "Low"},
                        "assignee": {"accountId": "u1"},
                        "reporter": {"accountId": "u2"},
                        "labels": [],
                        "components": [],
                        "created": "2026-03-20T10:00:00.000+0000",
                        "updated": "2026-03-21T11:00:00.000+0000",
                        "resolutiondate": None,
                        "customfield_10004": "1",
                        "sprint": {"id": 700},
                        "customfield_10014": "CEGBUPOL-1",
                    },
                }
            ],
        }
        with patch.object(self.connector, "_request_json", return_value=payload) as mocked:
            issues, batch, total = self.connector.get_board_issues(board_id=27193, start_at=0, max_results=1)

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(mocked.call_args.args[0], "/rest/agile/1.0/board/27193/issue")
        self.assertEqual(total, 2)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_key, "CEGBUPOL-301")
        self.assertEqual(issues[0].parent_issue_key, "CEGBUPOL-1")
        self.assertTrue(batch.has_more)
        self.assertEqual(batch.next_cursor, "1")

    def test_get_board_issues_accepts_jql_filter(self) -> None:
        payload = {
            "startAt": 0,
            "maxResults": 1,
            "total": 1,
            "isLast": True,
            "issues": [],
        }
        with patch.object(self.connector, "_request_json", return_value=payload) as mocked:
            issues, batch, total = self.connector.get_board_issues(
                board_id=27193,
                start_at=0,
                max_results=1,
                jql='updated >= "2026-03-23 12:00"',
            )

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(
            mocked.call_args.kwargs["params"]["jql"],
            'updated >= "2026-03-23 12:00"',
        )
        self.assertEqual(issues, [])
        self.assertFalse(batch.has_more)
        self.assertEqual(total, 1)

    def test_basic_auth_header_uses_username_and_pat(self) -> None:
        connector = JiraRestConnector(
            config=ConnectorConfig(
                base_url="https://jira.example.com",
                pat_token="secret",
                auth_mode="basic",
                username="user@example.com",
            )
        )
        headers = connector._auth_headers()
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Basic "))

    def test_request_json_retries_transient_http_errors(self) -> None:
        with patch(
            "packages.connectors.jira_rest_stub.urlopen",
            side_effect=[
                make_http_error(503, b'{"errorMessages":["temporary unavailable"]}'),
                FakeHttpResponse(b'{"ok": true}'),
            ],
        ) as mocked_urlopen, patch("packages.connectors.jira_rest_stub.time.sleep") as mocked_sleep:
            payload = self.connector._request_json("/rest/api/2/search")

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(mocked_urlopen.call_count, 2)
        mocked_sleep.assert_called_once_with(0.25)

    def test_request_json_does_not_retry_permission_errors(self) -> None:
        with patch(
            "packages.connectors.jira_rest_stub.urlopen",
            side_effect=make_http_error(401, b'{"errorMessages":["unauthorized"]}'),
        ) as mocked_urlopen, patch("packages.connectors.jira_rest_stub.time.sleep") as mocked_sleep:
            with self.assertRaises(JiraAPIError) as exc_ctx:
                self.connector._request_json("/rest/api/2/search")

        self.assertEqual(exc_ctx.exception.status_code, 401)
        self.assertIn("unauthorized", exc_ctx.exception.body or "")
        self.assertEqual(mocked_urlopen.call_count, 1)
        mocked_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
