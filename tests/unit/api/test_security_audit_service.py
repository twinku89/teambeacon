from __future__ import annotations

import gzip
import json
import unittest
from unittest.mock import patch

from packages.connectors.jenkins_config import JenkinsRuntimeConfig
from packages.connectors.jira_config import JiraRuntimeConfig
from services.api.integrations import security_audit
from services.api.integrations.security_audit import _http_json_get, get_security_audit


class SecurityAuditServiceUnitTests(unittest.TestCase):
    def test_http_json_get_requests_and_decodes_gzip_payloads(self) -> None:
        runtime = JenkinsRuntimeConfig(
            job_url="https://jenkins.example.com/job/security-audit/",
            username="teambeacon@example.com",
            api_token="token",
        )
        payload = {"status": "ok", "count": 4}
        compressed_payload = gzip.compress(json.dumps(payload).encode("utf-8"))

        class FakeResponse:
            headers = {"Content-Encoding": "gzip"}

            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return compressed_payload

        captured_requests = []

        def fake_urlopen(request, timeout=None, context=None):  # noqa: ANN001
            captured_requests.append(request)
            return FakeResponse()

        with patch("services.api.integrations.security_audit.urlopen", side_effect=fake_urlopen), patch(
            "services.api.integrations.security_audit.create_ssl_context",
            return_value=None,
        ):
            result = _http_json_get("https://jenkins.example.com/api/json", runtime)

        self.assertEqual(result, payload)
        self.assertEqual(captured_requests[0].headers["Accept-encoding"], "gzip")

    def test_trend_findings_are_cached_by_build_url(self) -> None:
        runtime = JenkinsRuntimeConfig(
            job_url="https://jenkins.example.com/job/security-audit/",
            username="teambeacon@example.com",
            api_token="token",
        )
        test_report = {
            "suites": [
                {
                    "name": "commons-configuration2-2.11.0.jar",
                    "cases": [
                        {
                            "name": "CVE-2026-45205 pkg:maven/org.apache.commons/commons-configuration2@2.11.0",
                            "status": "FAILED",
                            "errorDetails": "cvssV3: MEDIUM, score: 5.3",
                            "stdout": "Uncontrolled Recursion vulnerability in Apache Commons.",
                        },
                    ],
                }
            ]
        }
        requested_urls: list[str] = []

        def fake_jenkins_request(url: str, runtime: JenkinsRuntimeConfig) -> object:
            requested_urls.append(url)
            if "/testReport/api/json" in url:
                return test_report
            if "/wfapi/artifacts" in url:
                return []
            return {}

        with security_audit._trend_findings_cache_lock:
            security_audit._trend_findings_cache.clear()
            security_audit._trend_findings_cache_order.clear()

        with patch.dict("os.environ", {"SECURITY_AUDIT_CACHE_SECONDS": "30"}), patch(
            "services.api.integrations.security_audit._http_json_get",
            side_effect=fake_jenkins_request,
        ):
            first_result = security_audit._build_findings_for_trend(
                "https://jenkins.example.com/job/security-audit/9/",
                runtime,
            )
            second_result = security_audit._build_findings_for_trend(
                "https://jenkins.example.com/job/security-audit/9/",
                runtime,
            )

        self.assertEqual(first_result, second_result)
        self.assertEqual(len(first_result), 1)
        self.assertEqual(len(requested_urls), 3)

    def test_latest_trivy_report_uses_timestamped_artifact_not_lexical_name_order(self) -> None:
        runtime = JenkinsRuntimeConfig(
            job_url="https://jenkins.example.com/job/security-audit/",
            username="teambeacon@example.com",
            api_token="token",
        )
        artifacts = [
            {
                "name": "reviews_7b14674da_20262805004524.json",
                "url": "/job/security-audit/11/artifact/reviews_7b14674da_20262805004524.json",
            },
            {
                "name": "reviews_840ffc28a_20262705202521.json",
                "url": "/job/security-audit/11/artifact/reviews_840ffc28a_20262705202521.json",
            },
        ]
        newer_report = {
            "ArtifactName": "reviews:newer",
            "Results": [
                {
                    "Target": "reviews:newer (oracle 9.7)",
                    "Vulnerabilities": [
                        {"VulnerabilityID": "CVE-2026-33416", "Severity": "HIGH", "PkgName": "libpng"},
                    ],
                },
            ],
        }
        older_report = {
            "ArtifactName": "reviews:older",
            "Results": [
                {
                    "Target": "Java",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2026-45205",
                            "Severity": "MEDIUM",
                            "PkgName": "commons-configuration2",
                        },
                    ],
                },
            ],
        }

        def fake_jenkins_request(url: str, runtime: JenkinsRuntimeConfig) -> object:
            if url.endswith("/wfapi/artifacts"):
                return artifacts
            if "reviews_7b14674da" in url:
                return newer_report
            if "reviews_840ffc28a" in url:
                return older_report
            return {}

        with patch(
            "services.api.integrations.security_audit._http_json_get",
            side_effect=fake_jenkins_request,
        ):
            report, artifact_name = security_audit._latest_trivy_report_for_build(
                "https://jenkins.example.com/job/security-audit/11/",
                runtime,
            )

        self.assertEqual(report, newer_report)
        self.assertEqual(artifact_name, "reviews:newer")

    def test_successful_ui_audit_log_does_not_report_allowlisted_findings(self) -> None:
        report = {
            "advisories": {
                "@gbu/rapid-routing": {
                    "name": "@gbu/rapid-routing",
                    "severity": "high",
                    "via": ["react-router-dom"],
                    "nodes": ["node_modules/@gbu/rapid-routing"],
                },
                "@remix-run/router": {
                    "name": "@remix-run/router",
                    "severity": "high",
                    "via": [
                        {
                            "source": 1112052,
                            "name": "@remix-run/router",
                            "dependency": "@remix-run/router",
                            "title": "React Router vulnerable to XSS via Open Redirects",
                            "url": "https://github.com/advisories/GHSA-2w69-qvjg-hvjx",
                            "severity": "high",
                            "cvss": {"score": 8.0},
                        }
                    ],
                    "nodes": ["node_modules/@remix-run/router"],
                },
            }
        }
        log_text = (
            "NPM audit report results:\n"
            f"{json.dumps(report, indent=2)}\n"
            "Found vulnerable allowlisted advisories: GHSA-2w69-qvjg-hvjx.\n"
            "Consider not allowlisting advisory: GHSA-rhx6-c78j-4q9w.\n"
            "BUILD SUCCESSFUL\n"
        )

        findings = security_audit._parse_npm_audit_log_findings(log_text)

        self.assertEqual(findings, [])

    def test_failed_ui_audit_log_reports_only_explicit_vulnerable_advisories(self) -> None:
        report = {
            "advisories": {
                "@gbu/rapid-routing": {
                    "name": "@gbu/rapid-routing",
                    "severity": "high",
                    "via": ["@remix-run/router"],
                    "nodes": ["node_modules/@gbu/rapid-routing"],
                },
                "@remix-run/router": {
                    "name": "@remix-run/router",
                    "severity": "high",
                    "via": [
                        {
                            "source": 1112052,
                            "name": "@remix-run/router",
                            "dependency": "@remix-run/router",
                            "title": "React Router vulnerable to XSS via Open Redirects",
                            "url": "https://github.com/advisories/GHSA-2w69-qvjg-hvjx",
                            "severity": "high",
                            "cvss": {"score": 8.0},
                        }
                    ],
                    "nodes": ["node_modules/@remix-run/router"],
                },
                "tmp": {
                    "name": "tmp",
                    "severity": "high",
                    "via": [
                        {
                            "source": 1119610,
                            "name": "tmp",
                            "dependency": "tmp",
                            "title": "tmp has Path Traversal via unsanitized prefix/postfix",
                            "url": "https://github.com/advisories/GHSA-ph9p-34f9-6g65",
                            "severity": "high",
                            "cvss": {"score": 8.1},
                        }
                    ],
                    "nodes": ["node_modules/tmp"],
                },
            }
        }
        log_text = (
            "NPM audit report results:\n"
            f"{json.dumps(report, indent=2)}\n"
            "Failed security audit due to high vulnerabilities.\n"
            "Vulnerable advisories are:\n"
            "https://github.com/advisories/GHSA-ph9p-34f9-6g65\n"
            "Exiting...\n"
        )

        findings = security_audit._parse_npm_audit_log_findings(log_text)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "GHSA-ph9p-34f9-6g65")
        self.assertEqual(findings[0]["packageName"], "tmp")

    def test_attach_jira_cards_templates_create_url_from_sample_issue_and_current_sprint(self) -> None:
        findings = [
            {
                "layer": "Backend",
                "id": "CVE-2026-45205",
                "severity": "MEDIUM",
                "packageName": "org.apache.commons/commons-configuration2",
                "installedVersion": "2.11.0",
                "title": "Uncontrolled Recursion vulnerability in Apache Commons.",
                "status": "FAILED",
            }
        ]
        jira_config = JiraRuntimeConfig(
            base_url="https://jira.example.com",
            pat_token="jira-token",
            project_key="REV",
            board_id=27191,
            story_points_field="customfield_10016",
        )
        jira_sample_issue = {
            "fields": {
                "project": {"id": "19824", "key": "REV"},
                "issuetype": {"id": "7", "name": "Story"},
                "labels": ["security-template"],
                "components": [{"id": "44556", "name": "Security"}],
                "customfield_11901": {"id": "90001", "value": "Dependency - Other"},
                "customfield_17971": {"id": "90002", "value": "Feature"},
                "customfield_14504": {"id": "90003", "value": "Planned"},
                "customfield_18820": {"id": "90004", "value": "Aconex"},
                "customfield_10902": "REV-4829",
                "customfield_10901": [{"id": 999999, "name": "Template Sprint"}],
            }
        }

        def fake_jira_request(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
            if path == "/rest/api/2/issue/REV-5404":
                return jira_sample_issue
            if path == "/rest/agile/1.0/board/27191/sprint":
                return {"values": [{"id": 121648, "name": "Current Sprint", "state": "active"}]}
            if path == "/rest/api/2/search":
                return {"issues": []}
            return {}

        with patch.dict("os.environ", {}, clear=True), patch(
            "services.api.integrations.security_audit.JiraRuntimeConfig.from_env",
            return_value=jira_config,
        ), patch("services.api.integrations.security_audit.JiraRestConnector") as connector_cls:
            connector_cls.return_value._request_json.side_effect = fake_jira_request

            security_audit._attach_jira_cards(findings)  # noqa: SLF001

        create_url = findings[0]["jiraCreateUrl"]
        self.assertIsNone(findings[0]["jiraCard"])
        self.assertIn("CreateIssueDetails!init.jspa", create_url)
        self.assertIn("pid=19824", create_url)
        self.assertIn("issuetype=7", create_url)
        self.assertIn("labels=security-template", create_url)
        self.assertIn("components=44556", create_url)
        self.assertIn("customfield_11901=90001", create_url)
        self.assertIn("customfield_17971=90002", create_url)
        self.assertIn("customfield_14504=90003", create_url)
        self.assertIn("customfield_18820=90004", create_url)
        self.assertIn("customfield_10902=REV-4829", create_url)
        self.assertIn("customfield_10901=121648", create_url)
        self.assertNotIn("999999", create_url)

    def test_attach_jira_cards_builds_create_url_when_sample_issue_is_missing(self) -> None:
        findings = [
            {
                "layer": "Backend",
                "id": "CVE-2026-45205",
                "severity": "MEDIUM",
                "packageName": "org.apache.commons/commons-configuration2",
                "installedVersion": "2.11.0",
                "title": "Uncontrolled Recursion vulnerability in Apache Commons.",
                "status": "FAILED",
            }
        ]
        jira_config = JiraRuntimeConfig(
            base_url="https://jira.example.com",
            pat_token="jira-token",
            project_key="SEC",
            board_id=27191,
            story_points_field="customfield_10016",
        )

        def fake_jira_request(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
            if path == "/rest/api/2/issue/REV-5404":
                raise security_audit.JiraAPIError("sample issue not found", status_code=404)
            if path == "/rest/api/2/project/SEC":
                return {
                    "id": "19824",
                    "key": "SEC",
                    "issueTypes": [
                        {"id": "5", "name": "Sub-task", "subtask": True},
                        {"id": "7", "name": "Story", "subtask": False},
                    ],
                }
            if path == "/rest/agile/1.0/board/27191/sprint":
                return {"values": [{"id": 121648, "name": "Active Sprint", "state": "active"}]}
            if path == "/rest/api/2/search":
                return {"issues": []}
            return {}

        with patch.dict("os.environ", {}, clear=True), patch(
            "services.api.integrations.security_audit.JiraRuntimeConfig.from_env",
            return_value=jira_config,
        ), patch("services.api.integrations.security_audit.JiraRestConnector") as connector_cls:
            connector_cls.return_value._request_json.side_effect = fake_jira_request

            security_audit._attach_jira_cards(findings)  # noqa: SLF001

        self.assertIsNone(findings[0]["jiraCard"])
        self.assertIn("CreateIssueDetails!init.jspa", findings[0]["jiraCreateUrl"])
        self.assertIn("pid=19824", findings[0]["jiraCreateUrl"])
        self.assertIn("issuetype=7", findings[0]["jiraCreateUrl"])
        self.assertIn("assignee=-1", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_11901=82266", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_17971=77085", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_14504=76800", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_18820=65005", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_10902=REV-4829", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_10901=121648", findings[0]["jiraCreateUrl"])

    def test_attach_jira_cards_uses_create_meta_when_project_issue_types_are_missing(self) -> None:
        findings = [
            {
                "layer": "Trivy Scan",
                "id": "CVE-2026-33416",
                "severity": "HIGH",
                "packageName": "libpng",
                "installedVersion": "2:1.6.37-12.el9_7.3",
                "title": "libpng vulnerability",
                "status": "FAILED",
            }
        ]
        jira_config = JiraRuntimeConfig(
            base_url="https://jira.example.com",
            pat_token="jira-token",
            project_key="SEC",
            board_id=None,
            story_points_field="customfield_10016",
        )

        def fake_jira_request(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
            if path == "/rest/api/2/issue/REV-5404":
                raise security_audit.JiraAPIError("sample issue not found", status_code=404)
            if path == "/rest/api/2/project/SEC":
                return {"id": "19824", "key": "SEC"}
            if path == "/rest/api/2/issue/createmeta":
                return {
                    "projects": [
                        {
                            "id": "19824",
                            "key": "SEC",
                            "issuetypes": [
                                {"id": "3", "name": "Task", "subtask": False},
                                {"id": "7", "name": "Story", "subtask": False},
                            ],
                        }
                    ]
                }
            if path == "/rest/api/2/search":
                return {"issues": []}
            return {}

        with patch.dict("os.environ", {}, clear=True), patch(
            "services.api.integrations.security_audit.JiraRuntimeConfig.from_env",
            return_value=jira_config,
        ), patch("services.api.integrations.security_audit.JiraRestConnector") as connector_cls:
            connector_cls.return_value._request_json.side_effect = fake_jira_request

            security_audit._attach_jira_cards(findings)  # noqa: SLF001

        self.assertIsNone(findings[0]["jiraCard"])
        self.assertIn("CreateIssueDetails!init.jspa", findings[0]["jiraCreateUrl"])
        self.assertIn("pid=19824", findings[0]["jiraCreateUrl"])
        self.assertIn("issuetype=7", findings[0]["jiraCreateUrl"])

    def test_attach_jira_cards_falls_back_to_default_create_link_when_metadata_is_blocked(self) -> None:
        findings = [
            {
                "layer": "UI",
                "id": "GHSA-ph9p-34f9-6g65",
                "severity": "HIGH",
                "packageName": "tmp",
                "installedVersion": "<0.2.6",
                "title": "tmp has Path Traversal via unsanitized prefix/postfix",
                "status": "FAILED",
            }
        ]
        jira_config = JiraRuntimeConfig(
            base_url="https://jira.example.com",
            pat_token="jira-token",
            project_key="SEC",
            board_id=None,
            story_points_field="customfield_10016",
        )

        def fake_jira_request(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
            if path == "/rest/api/2/search":
                raise security_audit.JiraAPIError("search unauthorized", status_code=401)
            raise security_audit.JiraAPIError("metadata unavailable", status_code=401)

        with patch.dict("os.environ", {}, clear=True), patch(
            "services.api.integrations.security_audit.JiraRuntimeConfig.from_env",
            return_value=jira_config,
        ), patch("services.api.integrations.security_audit.JiraRestConnector") as connector_cls:
            connector_cls.return_value._request_json.side_effect = fake_jira_request

            security_audit._attach_jira_cards(findings)  # noqa: SLF001

        self.assertIsNone(findings[0]["jiraCard"])
        self.assertIn("CreateIssueDetails!init.jspa", findings[0]["jiraCreateUrl"])
        self.assertIn("pid=19824", findings[0]["jiraCreateUrl"])
        self.assertIn("issuetype=7", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_11901=82266", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_17971=77085", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_14504=76800", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_18820=65005", findings[0]["jiraCreateUrl"])
        self.assertIn("customfield_10902=REV-4829", findings[0]["jiraCreateUrl"])
        self.assertIn("summary=Remediate+High+severity+UI+vulnerability+GHSA-ph9p-34f9-6g65", findings[0]["jiraCreateUrl"])
        self.assertIn("assignee=-1", findings[0]["jiraCreateUrl"])

    def test_attach_jira_cards_reuses_package_card_for_related_cves(self) -> None:
        findings = [
            {
                "layer": "Trivy Scan",
                "id": "CVE-2026-47162",
                "severity": "HIGH",
                "packageName": "pkg:rpm/oracle/libpng@1.6.37-12.el9_7.3?arch=x86_64",
                "installedVersion": "2:1.6.37-12.el9_7.3",
                "status": "FAILED",
            },
            {
                "layer": "Trivy Scan",
                "id": "CVE-2026-47167",
                "severity": "HIGH",
                "packageName": "pkg:rpm/oracle/libpng@1.6.37-12.el9_7.3?arch=x86_64",
                "installedVersion": "2:1.6.37-12.el9_7.3",
                "status": "FAILED",
            },
        ]
        jira_config = JiraRuntimeConfig(
            base_url="https://jira.example.com",
            pat_token="jira-token",
            project_key="SEC",
            board_id=None,
            story_points_field="customfield_10016",
        )
        jira_issue = {
            "key": "SEC-471",
            "fields": {
                "summary": "Remediate libpng vulnerabilities",
                "status": {"name": "In Progress", "statusCategory": {"name": "In Progress"}},
                "assignee": {"displayName": "Security Owner"},
                "updated": "2026-07-15T10:00:00.000+0000",
                "comment": {"comments": []},
            },
        }

        def fake_jira_request(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
            if path == "/rest/api/2/issue/REV-5404":
                return {"fields": {"project": {"id": "19824"}, "issuetype": {"id": "7"}}}
            if path == "/rest/api/2/search" and params:
                jql = str(params.get("jql"))
                if "CVE-2026-47162" in jql:
                    return {"issues": [jira_issue]}
                return {"issues": []}
            return {}

        with patch.dict("os.environ", {}, clear=True), patch(
            "services.api.integrations.security_audit.JiraRuntimeConfig.from_env",
            return_value=jira_config,
        ), patch("services.api.integrations.security_audit.JiraRestConnector") as connector_cls:
            connector_cls.return_value._request_json.side_effect = fake_jira_request

            security_audit._attach_jira_cards(findings)  # noqa: SLF001

        self.assertEqual(findings[0]["jiraCard"]["issueKey"], "SEC-471")
        self.assertEqual(findings[1]["jiraCard"]["issueKey"], "SEC-471")
        self.assertIsNone(findings[0]["jiraCreateUrl"])
        self.assertIsNone(findings[1]["jiraCreateUrl"])

    def test_attach_jira_cards_finds_existing_card_by_package(self) -> None:
        findings = [
            {
                "layer": "Trivy Scan",
                "id": "CVE-2026-47167",
                "severity": "HIGH",
                "packageName": "pkg:rpm/oracle/libpng@1.6.37-12.el9_7.3?arch=x86_64",
                "installedVersion": "2:1.6.37-12.el9_7.3",
                "status": "FAILED",
            }
        ]
        jira_config = JiraRuntimeConfig(
            base_url="https://jira.example.com",
            pat_token="jira-token",
            project_key="SEC",
            board_id=None,
            story_points_field="customfield_10016",
        )
        jira_issue = {
            "key": "SEC-471",
            "fields": {
                "summary": "Remediate CVE-2026-47162 in libpng",
                "status": {"name": "To Do", "statusCategory": {"name": "To Do"}},
                "assignee": None,
                "updated": "2026-07-15T10:00:00.000+0000",
                "comment": {"comments": []},
            },
        }
        jira_queries: list[str] = []

        def fake_jira_request(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
            if path == "/rest/api/2/issue/REV-5404":
                return {"fields": {"project": {"id": "19824"}, "issuetype": {"id": "7"}}}
            if path == "/rest/api/2/search" and params:
                jql = str(params.get("jql"))
                jira_queries.append(jql)
                if "oracle/libpng" in jql:
                    return {"issues": [jira_issue]}
                return {"issues": []}
            return {}

        with patch.dict("os.environ", {}, clear=True), patch(
            "services.api.integrations.security_audit.JiraRuntimeConfig.from_env",
            return_value=jira_config,
        ), patch("services.api.integrations.security_audit.JiraRestConnector") as connector_cls:
            connector_cls.return_value._request_json.side_effect = fake_jira_request

            security_audit._attach_jira_cards(findings)  # noqa: SLF001

        self.assertEqual(findings[0]["jiraCard"]["issueKey"], "SEC-471")
        self.assertIsNone(findings[0]["jiraCreateUrl"])
        self.assertTrue(any("CVE-2026-47167" in jql for jql in jira_queries))
        self.assertTrue(any("oracle/libpng" in jql for jql in jira_queries))

    def test_returns_pipeline_layers_and_findings(self) -> None:
        runtime = JenkinsRuntimeConfig(
            job_url="https://jenkins.example.com/job/security-audit/",
            username="teambeacon@example.com",
            api_token="token",
        )
        job = {
            "fullName": "team/security-audit",
            "lastBuild": {"number": 10, "url": "https://jenkins.example.com/job/security-audit/10/"},
            "builds": [
                {
                    "number": 10,
                    "url": "https://jenkins.example.com/job/security-audit/10/",
                    "result": "FAILURE",
                    "timestamp": 1779671917801,
                },
                {
                    "number": 9,
                    "url": "https://jenkins.example.com/job/security-audit/9/",
                    "result": "SUCCESS",
                    "timestamp": 1779585517801,
                },
            ],
        }
        workflow = {
            "id": "10",
            "status": "FAILED",
            "startTimeMillis": 1779671917801,
            "durationMillis": 120000,
            "stages": [
                {"name": "Backend", "status": "SUCCESS", "durationMillis": 30000},
                {"name": "Frontend", "status": "SUCCESS", "durationMillis": 10000},
                {"name": "Trivy Scan", "status": "FAILED", "durationMillis": 50000},
                {
                    "_links": {
                        "self": {
                            "href": "/job/security-audit/10/execution/node/88/wfapi/describe",
                        },
                    },
                    "name": "UI",
                    "status": "FAILED",
                    "durationMillis": 30000,
                },
            ],
        }
        ui_stage_detail = {
            "id": "88",
            "name": "UI",
            "stageFlowNodes": [
                {
                    "_links": {
                        "log": {
                            "href": "/job/security-audit/10/execution/node/94/wfapi/log",
                        },
                    },
                    "id": "94",
                    "name": "Shell Script",
                    "status": "FAILED",
                    "parameterDescription": "./gradlew ui:securityAudit",
                }
            ],
        }
        ui_audit_log = {
            "text": (
                "NPM audit report results:\n"
                "{\n"
                '  "advisories": {\n'
                '    "@remix-run/router": {\n'
                '      "name": "@remix-run/router",\n'
                '      "severity": "high",\n'
                '      "isDirect": false,\n'
                '      "via": [\n'
                '        {\n'
                '          "source": 1112052,\n'
                '          "name": "@remix-run/router",\n'
                '          "dependency": "@remix-run/router",\n'
                '          "title": "React Router vulnerable to XSS via Open Redirects",\n'
                '          "url": "https://github.com/advisories/GHSA-2w69-qvjg-hvjx",\n'
                '          "severity": "high",\n'
                '          "cvss": {"score": 8.0},\n'
                '          "range": "<=1.23.1"\n'
                "        }\n"
                "      ],\n"
                '      "nodes": ["node_modules/@remix-run/router"],\n'
                '      "fixAvailable": false\n'
                "    },\n"
                '    "tmp": {\n'
                '      "name": "tmp",\n'
                '      "severity": "high",\n'
                '      "isDirect": false,\n'
                '      "via": [\n'
                "\u001b[31mFailed security audit due to high vulnerabilities.\u001b[0m\n"
                '        {\n'
                '          "source": 1119610,\n'
                '          "name": "tmp",\n'
                '          "dependency": "tmp",\n'
                '          "title": "tmp has Path Traversal via unsanitized prefix/postfix",\n'
                '          "url": "<a href=\'https://github.com/advisories/GHSA-ph9p-34f9-6g65\'>'
                "https://github.com/advisories/GHSA-ph9p-34f9-6g65</a>\",\n"
                '          "severity": "high",\n'
                '          "cvss": {"score": 8.1},\n'
                '          "range": "<0.2.6"\n'
                "        }\n"
                "      ],\n"
                '      "nodes": ["node_modules/tmp"],\n'
                '      "fixAvailable": true\n'
                "    }\n"
                "  },\n"
                '  "metadata": {"vulnerabilities": {"high": 1, "total": 1}}\n'
                "}\n"
                "Found vulnerable allowlisted advisories: GHSA-2w69-qvjg-hvjx.\n"
                "Failed security audit due to high vulnerabilities.\n"
                "Vulnerable advisories are:\n"
                "https://github.com/advisories/GHSA-ph9p-34f9-6g65\n"
                "Exiting...\n"
            )
        }
        test_report = {
            "suites": [
                {
                    "name": "commons-configuration2-2.11.0.jar",
                    "cases": [
                        {
                            "name": "CVE-2026-45205 pkg:maven/org.apache.commons/commons-configuration2@2.11.0",
                            "status": "FAILED",
                            "errorDetails": "cvssV3: MEDIUM, score: 5.3",
                            "stdout": "Uncontrolled Recursion vulnerability in Apache Commons.",
                        },
                        {
                            "name": "CVE-2026-22747 pkg:maven/org.springframework.security/spring-security-web@6.5.10",
                            "status": "SKIPPED",
                            "errorDetails": "",
                            "stdout": "Skipped due to scanner-specific advisory mismatch.",
                        }
                    ],
                }
            ]
        }
        artifacts = [
            {
                "name": "reviews.json",
                "url": "/job/security-audit/10/artifact/reviews.json",
            }
        ]
        trivy_report = {
            "CreatedAt": "2026-05-25T01:25:22Z",
            "ArtifactName": "reviews:latest",
            "Results": [
                {
                    "Target": "reviews:latest (oracle 9.7)",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2026-33416",
                            "Severity": "HIGH",
                            "PkgName": "libpng",
                            "PkgIdentifier": {
                                "PURL": "pkg:rpm/oracle/libpng@1.6.37-12.el9_7.3?arch=x86_64&distro=oracle-9.7&epoch=2",
                            },
                            "InstalledVersion": "2:1.6.37-12.el9_7.3",
                            "FixedVersion": "2:1.6.37-12.el9_7.4",
                            "Title": "libpng vulnerability",
                        }
                    ],
                }
            ],
        }
        jira_config = JiraRuntimeConfig(
            base_url="https://jira.example.com",
            pat_token="jira-token",
            project_key="SEC",
            board_id=27191,
            story_points_field="customfield_10016",
        )
        jira_search_with_matches = {
            "issues": [
                {
                    "key": "SEC-124",
                    "fields": {
                        "summary": "Newer unassigned CVE-2026-33416 card",
                        "status": {"name": "To Do", "statusCategory": {"name": "To Do"}},
                        "assignee": None,
                        "updated": "2026-05-25T10:00:00.000+0000",
                        "comment": {"comments": []},
                    },
                },
                {
                    "key": "SEC-123",
                    "fields": {
                        "summary": "Assigned CVE-2026-33416 card",
                        "status": {"name": "In Progress", "statusCategory": {"name": "In Progress"}},
                        "assignee": {"displayName": "Security Owner"},
                        "updated": "2026-05-24T10:00:00.000+0000",
                        "comment": {
                            "comments": [
                                {"updated": "2026-05-24T11:00:00.000+0000"},
                            ],
                        },
                    },
                },
                {
                    "key": "SEC-122",
                    "fields": {
                        "summary": "Older assigned CVE-2026-33416 card",
                        "status": {"name": "Blocked", "statusCategory": {"name": "In Progress"}},
                        "assignee": {"displayName": "Security Owner"},
                        "updated": "2026-05-23T10:00:00.000+0000",
                        "comment": {
                            "comments": [
                                {"updated": "2026-05-23T11:00:00.000+0000"},
                            ],
                        },
                    },
                },
            ],
        }
        jira_sample_issue = {
            "fields": {
                "project": {"id": "19824", "key": "SEC"},
                "issuetype": {"id": "7", "name": "Story"},
            },
        }
        jira_active_sprints = {"values": [{"id": 121648, "name": "Active Sprint", "state": "active"}]}

        def fake_jira_request(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
            if path == "/rest/api/2/issue/REV-5404":
                return jira_sample_issue
            if path == "/rest/agile/1.0/board/27191/sprint":
                return jira_active_sprints
            if path == "/rest/api/2/search" and params and "CVE-2026-33416" in str(params.get("jql")):
                return jira_search_with_matches
            if path == "/rest/api/2/search":
                return {"issues": []}
            return {}

        def fake_jenkins_request(url: str, runtime: JenkinsRuntimeConfig) -> object:
            if "/execution/node/88/wfapi/describe" in url:
                return ui_stage_detail
            if "/execution/node/94/wfapi/log" in url:
                return ui_audit_log
            if "/lastBuild/wfapi/describe" in url:
                return workflow
            if "/9/wfapi/describe" in url:
                return {"stages": []}
            if "/testReport/api/json" in url:
                return test_report
            if "/api/json?" in url:
                return job
            if "/9/wfapi/artifacts" in url:
                return []
            if "/wfapi/artifacts" in url:
                return artifacts
            if url.endswith("reviews.json"):
                return trivy_report
            return {}

        with patch.dict("os.environ", {"SECURITY_AUDIT_CACHE_SECONDS": "0"}), patch(
            "services.api.integrations.security_audit.load_env_files"
        ), patch(
            "services.api.integrations.security_audit._load_security_runtime",
            return_value=runtime,
        ), patch(
            "services.api.integrations.security_audit._http_json_get",
            side_effect=fake_jenkins_request,
        ), patch(
            "services.api.integrations.security_audit.JiraRuntimeConfig.from_env",
            return_value=jira_config,
        ), patch(
            "services.api.integrations.security_audit.JiraRestConnector"
        ) as connector_cls:
            connector_cls.return_value._request_json.side_effect = fake_jira_request
            payload = get_security_audit()

        self.assertIsNone(payload["error"])
        self.assertEqual(payload["pipeline"]["buildNumber"], "10")
        self.assertEqual(payload["summary"]["totalFindings"], 3)
        self.assertEqual(payload["summary"]["severityCounts"]["high"], 2)
        self.assertEqual(payload["summary"]["severityCounts"]["medium"], 1)
        self.assertEqual(payload["summary"]["failedLayers"], ["Backend", "Trivy Scan", "UI"])
        self.assertEqual(payload["layers"][0]["name"], "Backend")
        self.assertEqual(payload["layers"][0]["findingCount"], 1)
        self.assertEqual(payload["layers"][3]["name"], "UI")
        self.assertEqual(payload["layers"][3]["findingCount"], 1)
        self.assertEqual(payload["layers"][3]["severityCounts"]["high"], 1)
        self.assertEqual(payload["findings"][0]["id"], "CVE-2026-45205")
        self.assertEqual(payload["findings"][1]["id"], "CVE-2026-33416")
        self.assertEqual(payload["findings"][2]["layer"], "UI")
        self.assertEqual(payload["findings"][2]["id"], "GHSA-ph9p-34f9-6g65")
        self.assertEqual(payload["findings"][2]["packageName"], "tmp")
        self.assertEqual(payload["findings"][2]["score"], 8.1)
        self.assertNotIn("GHSA-2w69-qvjg-hvjx", [finding["id"] for finding in payload["findings"]])
        self.assertEqual(
            payload["findings"][1]["packageName"],
            "pkg:rpm/oracle/libpng@1.6.37-12.el9_7.3?arch=x86_64&distro=oracle-9.7&epoch=2",
        )
        self.assertIsNone(payload["findings"][0]["jiraCard"])
        self.assertIn("CreateIssueDetails!init.jspa", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("pid=19824", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("issuetype=7", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("assignee=-1", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("customfield_15812=", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("customfield_11901=82266", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("customfield_17971=77085", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("customfield_14504=76800", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("customfield_18820=65005", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("customfield_10902=REV-4829", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("customfield_10901=121648", payload["findings"][0]["jiraCreateUrl"])
        self.assertIn("CVE-2026-45205+is+remediated", payload["findings"][0]["jiraCreateUrl"])
        self.assertEqual(payload["findings"][1]["jiraCard"]["issueKey"], "SEC-123")
        self.assertEqual(payload["findings"][1]["jiraCard"]["issueUrl"], "https://jira.example.com/browse/SEC-123")
        self.assertIsNone(payload["findings"][1]["jiraCreateUrl"])
        self.assertEqual(payload["findings"][1]["jiraCard"]["assignee"], "Security Owner")
        self.assertEqual(payload["findings"][1]["jiraCard"]["latestCommentAt"], "2026-05-24T11:00:00+00:00")
        self.assertNotIn("CVE-2026-22747", [finding["id"] for finding in payload["findings"]])
        self.assertEqual([point["buildNumber"] for point in payload["trend"]], [9, 10])
        self.assertEqual(payload["trend"][0]["totalFindings"], 1)
        self.assertEqual(payload["trend"][1]["totalFindings"], 3)
        self.assertEqual(payload["trend"][1]["severityCounts"]["high"], 2)


if __name__ == "__main__":
    unittest.main()
