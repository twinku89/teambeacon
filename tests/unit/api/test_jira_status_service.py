from __future__ import annotations

import unittest
from unittest.mock import patch

from packages.connectors.jira_rest_stub import JiraAPIError
from services.api.integrations.jira_status import get_jira_status


class JiraStatusServiceUnitTests(unittest.TestCase):
    def test_returns_configuration_error_when_env_missing(self) -> None:
        with patch("services.api.integrations.jira_status.load_env_files"), patch(
            "services.api.integrations.jira_status.JiraRuntimeConfig.from_env",
            side_effect=ValueError("missing required environment variables: JIRA_BASE_URL, JIRA_PAT"),
        ):
            payload = get_jira_status()

        self.assertFalse(payload["connected"])
        self.assertIn("missing required environment variables", payload["error"])
        self.assertEqual(payload["source"], "jira")
        self.assertTrue(payload["checks"])

    def test_returns_connected_payload_when_checks_succeed(self) -> None:
        class RuntimeStub:
            base_url = "https://jira.example.com"
            project_key = "CEGBUPOL"
            board_id = 27193
            story_points_field = "customfield_10004"
            epic_link_field = "customfield_10902"
            sprint_field_candidates = ("customfield_10901",)
            auth_mode = "pat_bearer"

            def to_connector_config(self):  # noqa: D401
                return object()

        class ConnectorStub:
            def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
                pass

            def get_board(self, board_id):  # noqa: ANN001
                Board = type("Board", (), {})
                board = Board()
                board.external_board_id = board_id
                board.name = "CEGBU Delivery Board"
                return board

            def search_issues(self, jql, max_results):  # noqa: ANN001
                Issue = type("Issue", (), {})
                issue = Issue()
                issue.issue_key = "CEGBUPOL-123"
                return [issue], None

        with patch("services.api.integrations.jira_status.load_env_files"), patch(
            "services.api.integrations.jira_status.JiraRuntimeConfig.from_env",
            return_value=RuntimeStub(),
        ), patch(
            "services.api.integrations.jira_status.JiraRestConnector",
            ConnectorStub,
        ):
            payload = get_jira_status()

        self.assertTrue(payload["connected"])
        self.assertEqual(payload["sampleIssueKey"], "CEGBUPOL-123")
        self.assertEqual(payload["metrics"]["projectSampleIssueCount"], 1)
        self.assertEqual(payload["config"]["projectKey"], "CEGBUPOL")
        self.assertEqual(payload["config"]["epicLinkField"], "customfield_10902")
        self.assertEqual(payload["config"]["sprintFields"], ["customfield_10901"])
        self.assertEqual(payload["sampleIssueUrl"], "https://jira.example.com/browse/CEGBUPOL-123")
        self.assertEqual(payload["configuredProjectUrl"], "https://jira.example.com/projects/CEGBUPOL")
        self.assertEqual(payload["configuredBoard"]["name"], "CEGBU Delivery Board")
        self.assertEqual(
            payload["configuredBoard"]["url"],
            "https://jira.example.com/secure/RapidBoard.jspa?rapidView=27193",
        )
        self.assertEqual(len(payload["checks"]), 2)

    def test_returns_actionable_message_for_certificate_failure(self) -> None:
        class RuntimeStub:
            base_url = "https://jira.example.com"
            project_key = "CEGBUPOL"
            board_id = 27193
            story_points_field = "customfield_10004"
            epic_link_field = "customfield_10902"
            sprint_field_candidates = ("customfield_10901",)
            auth_mode = "pat_bearer"
            ca_bundle_path = None

            def to_connector_config(self):  # noqa: D401
                return object()

        class ConnectorStub:
            def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
                pass

            def get_board(self, board_id):  # noqa: ANN001
                raise JiraAPIError(
                    "JIRA request failed for /rest/agile/1.0/board/27193: "
                    "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>"
                )

            def search_issues(self, jql, max_results):  # noqa: ANN001
                raise JiraAPIError(
                    "JIRA request failed for /rest/api/2/search: "
                    "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>"
                )

        with patch("services.api.integrations.jira_status.load_env_files"), patch(
            "services.api.integrations.jira_status.JiraRuntimeConfig.from_env",
            return_value=RuntimeStub(),
        ), patch(
            "services.api.integrations.jira_status.JiraRestConnector",
            ConnectorStub,
        ):
            payload = get_jira_status()

        self.assertFalse(payload["connected"])
        self.assertIn("Set JIRA_CA_BUNDLE or ATLASSIAN_CA_BUNDLE", payload["error"])
        self.assertIn("restart the API", payload["error"])


if __name__ == "__main__":
    unittest.main()
