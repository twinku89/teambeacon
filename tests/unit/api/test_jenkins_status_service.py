from __future__ import annotations

import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from services.api.integrations.jenkins_status import get_jenkins_status


class _RuntimeStub:
    job_url = "https://jenkins.example.com/job/release"
    username = "teambeacon@example.com"
    api_token = "token"
    timeout_seconds = 30
    ca_bundle_path = None


class _ResponseStub:
    def __init__(self, body: str) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self) -> _ResponseStub:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:  # noqa: ANN001, ANN201
        _ = exc_type, exc_val, exc_tb
        return False


class JenkinsStatusServiceUnitTests(unittest.TestCase):
    def test_returns_configuration_error_when_env_missing(self) -> None:
        with patch("services.api.integrations.jenkins_status.load_env_files"), patch(
            "services.api.integrations.jenkins_status.JenkinsRuntimeConfig.from_env",
            side_effect=ValueError(
                "missing required environment variables: JENKINS_RELEASE_PIPELINE_URL, JENKINS_API_AUTH_TOKEN"
            ),
        ):
            payload = get_jenkins_status()

        self.assertFalse(payload["connected"])
        self.assertEqual(payload["source"], "jenkins")
        self.assertIn("missing required environment variables", payload["error"])
        self.assertEqual(payload["checks"][0]["name"], "configuration")

    def test_returns_connected_payload_when_job_api_succeeds(self) -> None:
        job_payload = json.dumps(
            {
                "displayName": "Release",
                "fullName": "blade-runners/reviews/release",
                "url": "https://jenkins.example.com/job/release/",
                "buildable": True,
                "lastBuild": {"number": 42, "result": "SUCCESS"},
                "lastSuccessfulBuild": {"number": 41},
            }
        )

        with patch("services.api.integrations.jenkins_status.load_env_files"), patch(
            "services.api.integrations.jenkins_status.JenkinsRuntimeConfig.from_env",
            return_value=_RuntimeStub(),
        ), patch(
            "services.api.integrations.jenkins_status.urlopen",
            return_value=_ResponseStub(job_payload),
        ):
            payload = get_jenkins_status()

        self.assertTrue(payload["connected"])
        self.assertEqual(payload["config"]["jobUrl"], "https://jenkins.example.com/job/release")
        self.assertEqual(payload["config"]["authUser"], "teambeacon@example.com")
        self.assertEqual(payload["metrics"]["jobName"], "blade-runners/reviews/release")
        self.assertEqual(payload["metrics"]["lastBuildNumber"], 42)
        self.assertEqual(payload["metrics"]["lastBuildResult"], "SUCCESS")
        self.assertEqual(payload["checks"][0]["name"], "job_api")
        self.assertTrue(payload["checks"][0]["ok"])

    def test_returns_error_when_job_api_is_unauthorized(self) -> None:
        unauthorized = HTTPError(
            url="https://jenkins.example.com/job/release/api/json",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

        with patch("services.api.integrations.jenkins_status.load_env_files"), patch(
            "services.api.integrations.jenkins_status.JenkinsRuntimeConfig.from_env",
            return_value=_RuntimeStub(),
        ), patch(
            "services.api.integrations.jenkins_status.urlopen",
            side_effect=unauthorized,
        ):
            payload = get_jenkins_status()

        self.assertFalse(payload["connected"])
        self.assertIn("HTTP 401", payload["error"])
        self.assertFalse(payload["checks"][0]["ok"])

    def test_returns_actionable_message_for_certificate_failure(self) -> None:
        certificate_failure = URLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

        with patch("services.api.integrations.jenkins_status.load_env_files"), patch(
            "services.api.integrations.jenkins_status.JenkinsRuntimeConfig.from_env",
            return_value=_RuntimeStub(),
        ), patch(
            "services.api.integrations.jenkins_status.urlopen",
            side_effect=certificate_failure,
        ):
            payload = get_jenkins_status()

        self.assertFalse(payload["connected"])
        self.assertIn("Set JENKINS_CA_BUNDLE or ATLASSIAN_CA_BUNDLE", payload["error"])


if __name__ == "__main__":
    unittest.main()
