from __future__ import annotations

import base64
import gzip
import html
import json
import os
import re
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from packages.connectors.jenkins_config import JenkinsRuntimeConfig
from packages.connectors.jira_config import JiraRuntimeConfig, load_env_files
from packages.connectors.jira_rest_stub import JiraAPIError, JiraRestConnector
from packages.connectors.tls import create_ssl_context
from services.api.integrations.jira_sync import _ensure_schema, _resolve_db_path

DEFAULT_SECURITY_AUDIT_PIPELINE_URL = (
    "https://ci-cloud.us.oracle.com/jenkins/aconex-core-ci-scm/job/blade-runners/job/reviews/"
    "job/reviews-security-audit-pipeline/"
)
SECURITY_LAYER_NAMES = ("Backend", "Frontend", "Trivy Scan", "UI")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
JIRA_CARD_SEARCH_LIMIT = 25
SECURITY_AUDIT_CACHE_SECONDS = 30
SECURITY_TREND_FINDINGS_CACHE_LIMIT = 20
DEFAULT_JIRA_CREATE_SAMPLE_ISSUE_KEY = "REV-5404"
DEFAULT_JIRA_CREATE_PROJECT_ID = "19824"
DEFAULT_JIRA_CREATE_ISSUE_TYPE_ID = "7"
DEFAULT_JIRA_CREATE_ISSUE_TYPE_NAME = "Story"
DEFAULT_JIRA_SECURITY_EPIC_LINK = "REV-4829"
DEFAULT_JIRA_EPIC_LINK_FIELD = "customfield_10902"
DEFAULT_JIRA_ACCEPTANCE_CRITERIA_FIELD = "customfield_15812"
DEFAULT_JIRA_DEPENDENCY_POSSIBILITIES_FIELD = "customfield_11901"
DEFAULT_JIRA_DEPENDENCY_OTHER_OPTION = "82266"
DEFAULT_JIRA_REQUIREMENT_CATEGORY_FIELD = "customfield_17971"
DEFAULT_JIRA_REQUIREMENT_FEATURE_OPTION = "77085"
DEFAULT_JIRA_ACTIVITY_TYPE_FIELD = "customfield_14504"
DEFAULT_JIRA_ACTIVITY_PLANNED_OPTION = "76800"
DEFAULT_JIRA_SPRINT_FIELD = "customfield_10901"
DEFAULT_JIRA_PRODUCT_FIELD = "customfield_18820"
DEFAULT_JIRA_PRODUCT_ACONEX_OPTION = "65005"
_security_audit_cache: dict[str, Any] | None = None
_trend_findings_cache: dict[str, list[dict[str, Any]]] = {}
_trend_findings_cache_order: list[str] = []
_trend_findings_cache_lock = Lock()
JiraCreateParamValue = str | list[str]


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _millis_to_iso(value: Any) -> str | None:
    if not isinstance(value, int):
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _cached_security_audit() -> dict[str, Any] | None:
    if os.environ.get("SECURITY_AUDIT_CACHE_SECONDS") == "0":
        return None
    if not _security_audit_cache:
        return None
    generated_at = _security_audit_cache.get("generatedAt")
    if not isinstance(generated_at, str):
        return None
    try:
        parsed = datetime.fromisoformat(generated_at)
    except ValueError:
        return None
    ttl = int(os.environ.get("SECURITY_AUDIT_CACHE_SECONDS", str(SECURITY_AUDIT_CACHE_SECONDS)))
    if (_utc_now() - parsed).total_seconds() > ttl:
        return None
    payload = dict(_security_audit_cache)
    payload["cached"] = True
    return payload


def _store_security_audit_cache(payload: dict[str, Any]) -> None:
    global _security_audit_cache
    _security_audit_cache = dict(payload)


def _normalize_build_url(build_url: str) -> str:
    return build_url.rstrip("/")


def _cached_trend_findings(build_url: str) -> list[dict[str, Any]] | None:
    if os.environ.get("SECURITY_AUDIT_CACHE_SECONDS") == "0":
        return None
    cache_key = _normalize_build_url(build_url)
    with _trend_findings_cache_lock:
        cached_findings = _trend_findings_cache.get(cache_key)
        if cached_findings is None:
            return None
        return [dict(finding) for finding in cached_findings]


def _store_trend_findings_cache(build_url: str, findings: list[dict[str, Any]]) -> None:
    if os.environ.get("SECURITY_AUDIT_CACHE_SECONDS") == "0":
        return
    cache_key = _normalize_build_url(build_url)
    with _trend_findings_cache_lock:
        if cache_key not in _trend_findings_cache:
            _trend_findings_cache_order.append(cache_key)
        _trend_findings_cache[cache_key] = [dict(finding) for finding in findings]
        while len(_trend_findings_cache_order) > SECURITY_TREND_FINDINGS_CACHE_LIMIT:
            expired_key = _trend_findings_cache_order.pop(0)
            _trend_findings_cache.pop(expired_key, None)


def _auth_headers(runtime: JenkinsRuntimeConfig) -> dict[str, str]:
    auth_blob = f"{runtime.username}:{runtime.api_token}".encode("utf-8")
    encoded = base64.b64encode(auth_blob).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def _load_security_runtime() -> JenkinsRuntimeConfig:
    source = dict(os.environ)
    missing = [name for name in ("JENKINS_API_AUTH_USER", "JENKINS_API_AUTH_TOKEN") if not source.get(name)]
    if missing:
        missing_csv = ", ".join(missing)
        raise ValueError(f"missing required environment variables: {missing_csv}")

    return JenkinsRuntimeConfig(
        job_url=source.get("JENKINS_SECURITY_AUDIT_PIPELINE_URL", DEFAULT_SECURITY_AUDIT_PIPELINE_URL).strip(),
        username=source["JENKINS_API_AUTH_USER"].strip(),
        api_token=source["JENKINS_API_AUTH_TOKEN"].strip(),
        timeout_seconds=int(source.get("JENKINS_TIMEOUT_SECONDS", "30")),
        ca_bundle_path=source.get("JENKINS_CA_BUNDLE") or source.get("ATLASSIAN_CA_BUNDLE"),
    )


def _http_json_get(url: str, runtime: JenkinsRuntimeConfig) -> Any:
    request = Request(
        url=url,
        headers={"Accept": "application/json", "Accept-Encoding": "gzip", **_auth_headers(runtime)},
        method="GET",
    )
    ssl_context = create_ssl_context(runtime.ca_bundle_path)
    with urlopen(request, timeout=runtime.timeout_seconds, context=ssl_context) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
        raw_json = raw.decode("utf-8")
    return json.loads(raw_json)


def _build_job_api_url(job_url: str) -> str:
    query = urlencode(
        {
            "tree": (
                "displayName,fullName,url,lastBuild[number,url,result,timestamp],"
                "builds[number,url,result,timestamp]{0,5}"
            )
        }
    )
    return f"{job_url.rstrip('/')}/api/json?{query}"


def _build_test_report_url_for_build(build_url: str) -> str:
    query = urlencode(
        {
            "tree": (
                "failCount,skipCount,totalCount,"
                "suites[name,cases[className,name,status,errorDetails,errorStackTrace,stdout]]"
            )
        }
    )
    return f"{build_url.rstrip('/')}/testReport/api/json?{query}"


def _build_test_report_url(job_url: str) -> str:
    return _build_test_report_url_for_build(f"{job_url.rstrip('/')}/lastBuild/")


def _build_workflow_url_for_build(build_url: str) -> str:
    return f"{build_url.rstrip('/')}/wfapi/describe"


def _absolute_jenkins_url(base_url: str, href: str) -> str:
    return urljoin(f"{base_url.rstrip('/')}/", href)


def _empty_layer(name: str, stage: dict[str, Any] | None = None) -> dict[str, Any]:
    severity_counts = {severity.lower(): 0 for severity in SEVERITIES}
    stage_status = stage.get("status") if isinstance(stage, dict) else None
    return {
        "name": name,
        "stageStatus": stage_status if isinstance(stage_status, str) else "NOT_FOUND",
        "durationMillis": stage.get("durationMillis") if isinstance(stage, dict) else None,
        "findingCount": 0,
        "failedFindingCount": 0,
        "skippedFindingCount": 0,
        "severityCounts": severity_counts,
    }


def _extract_severity(*values: str | None) -> str:
    for value in values:
        if not value:
            continue
        match = re.search(r"\b(CRITICAL|HIGH|MEDIUM|LOW|UNKNOWN)\b", value, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return "UNKNOWN"


def _parse_purl(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return (None, None)
    match = re.search(r"pkg:[^/]+/([^@\s]+)@([^\s]+)", value)
    if not match:
        return (None, None)
    return (match.group(1), match.group(2))


def _finding_id(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.split(" ", 1)[0].strip()
    return candidate or None


def _parse_backend_findings(test_report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for suite in test_report.get("suites") or []:
        if not isinstance(suite, dict):
            continue
        for case in suite.get("cases") or []:
            if not isinstance(case, dict):
                continue
            status = str(case.get("status") or "UNKNOWN").upper()
            if status in {"PASSED", "FIXED"}:
                continue
            name = str(case.get("name") or "")
            class_name = str(case.get("className") or "")
            details = str(case.get("errorDetails") or "")
            stdout = str(case.get("stdout") or "")
            package_name, installed_version = _parse_purl(name)
            findings.append(
                {
                    "layer": "Backend",
                    "id": _finding_id(class_name) or _finding_id(name),
                    "severity": _extract_severity(details, stdout),
                    "packageName": package_name,
                    "installedVersion": installed_version,
                    "fixedVersion": None,
                    "target": str(suite.get("name") or ""),
                    "title": stdout.strip() or details.strip() or name,
                    "status": status,
                    "score": _extract_score(details),
                }
            )
    return findings


def _extract_score(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"\bscore:\s*([0-9]+(?:\.[0-9]+)?)", value, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def _parse_trivy_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for result in report.get("Results") or []:
        if not isinstance(result, dict):
            continue
        target = str(result.get("Target") or "")
        for vulnerability in result.get("Vulnerabilities") or []:
            if not isinstance(vulnerability, dict):
                continue
            package_identifier = vulnerability.get("PkgIdentifier")
            purl = package_identifier.get("PURL") if isinstance(package_identifier, dict) else None
            findings.append(
                {
                    "layer": "Trivy Scan",
                    "id": vulnerability.get("VulnerabilityID"),
                    "severity": str(vulnerability.get("Severity") or "UNKNOWN").upper(),
                    "packageName": purl if isinstance(purl, str) and purl.strip() else vulnerability.get("PkgName"),
                    "installedVersion": vulnerability.get("InstalledVersion"),
                    "fixedVersion": vulnerability.get("FixedVersion"),
                    "target": target,
                    "title": vulnerability.get("Title") or vulnerability.get("Description") or "",
                    "status": "FAILED",
                    "score": _best_trivy_score(vulnerability),
                }
            )
    return findings


def _best_trivy_score(vulnerability: dict[str, Any]) -> float | None:
    cvss = vulnerability.get("CVSS")
    if not isinstance(cvss, dict):
        return None
    for vendor in ("nvd", "redhat", "ghsa"):
        candidate = cvss.get(vendor)
        if isinstance(candidate, dict):
            score = candidate.get("V3Score") or candidate.get("V2Score")
            if isinstance(score, (int, float)):
                return float(score)
    return None


def _trivy_artifact_sort_key(name: str) -> tuple[datetime, str]:
    timestamp_match = re.search(r"_(\d{14})\.json$", name)
    if not timestamp_match:
        return (datetime.min.replace(tzinfo=timezone.utc), name)
    try:
        parsed = datetime.strptime(timestamp_match.group(1), "%Y%d%m%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return (datetime.min.replace(tzinfo=timezone.utc), name)
    return (parsed, name)


def _strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", value)


def _json_depth_delta(line: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    for character in line:
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if character in "{[":
            depth += 1
        elif character in "}]":
            depth -= 1
    return depth


def _line_looks_like_json(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(("{", "}", "[", "]", '"'))


def _extract_npm_audit_report_from_log(log_text: str) -> dict[str, Any] | None:
    cleaned = html.unescape(_strip_ansi(log_text))
    marker_index = cleaned.find("NPM audit report results:")
    search_from = marker_index if marker_index != -1 else 0
    json_start = cleaned.find("{", search_from)
    if json_start == -1:
        return None

    json_lines: list[str] = []
    depth = 0
    started = False
    for line in cleaned[json_start:].splitlines():
        if not started and not line.lstrip().startswith("{"):
            continue
        started = True
        if not _line_looks_like_json(line):
            continue
        json_lines.append(line)
        depth += _json_depth_delta(line)
        if depth == 0:
            break

    if not json_lines or depth != 0:
        return None

    try:
        report = json.loads("\n".join(json_lines))
    except json.JSONDecodeError:
        return None
    return report if isinstance(report, dict) else None


def _clean_audit_log_text(log_text: str) -> str:
    return html.unescape(_strip_ansi(log_text))


def _github_advisory_ids(value: str) -> set[str]:
    return set(re.findall(r"\bGHSA-[A-Za-z0-9]+-[A-Za-z0-9]+-[A-Za-z0-9]+\b", value))


def _audit_ci_vulnerable_advisory_ids(log_text: str) -> set[str] | None:
    cleaned = _clean_audit_log_text(log_text)
    marker = "Vulnerable advisories are:"
    marker_index = cleaned.find(marker)
    if marker_index == -1:
        return None

    segment = cleaned[marker_index + len(marker):]
    end_index = segment.find("Exiting...")
    if end_index != -1:
        segment = segment[:end_index]
    return _github_advisory_ids(segment)


def _audit_ci_failed_security_audit(log_text: str) -> bool:
    cleaned = _clean_audit_log_text(log_text).lower()
    return "failed security audit" in cleaned or "vulnerable advisories are:" in cleaned


def _audit_ci_allowlisted_advisory_ids(log_text: str) -> set[str]:
    allowlisted_ids: set[str] = set()
    cleaned = _clean_audit_log_text(log_text)
    for line in cleaned.splitlines():
        normalized_line = line.lower()
        if "not allowlist" in normalized_line or "not allowlisting" in normalized_line:
            continue
        if "allowlist" in normalized_line or "allowlisted" in normalized_line:
            allowlisted_ids.update(_github_advisory_ids(line))
    return allowlisted_ids


def _advisory_url(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"https://github\.com/advisories/[A-Za-z0-9-]+", value)
    return match.group(0) if match else None


def _advisory_id_from_url(value: str | None) -> str | None:
    url = _advisory_url(value)
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1]


def _via_objects(advisory: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in advisory.get("via") or [] if isinstance(item, dict)]


def _via_names(advisory: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in advisory.get("via") or []:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("name") or item.get("dependency")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return names


def _best_npm_advisory_detail(advisory: dict[str, Any], severity: str) -> dict[str, Any] | None:
    details = _via_objects(advisory)
    matching_details = [
        detail
        for detail in details
        if str(detail.get("severity") or "").upper() == severity
    ]
    if matching_details:
        return matching_details[0]
    if severity == "UNKNOWN" and details:
        return details[0]
    return None


def _npm_advisory_id(package_name: str, advisory: dict[str, Any], detail: dict[str, Any] | None) -> str:
    for value in (
        detail.get("url") if detail else None,
        detail.get("title") if detail else None,
    ):
        advisory_id = _advisory_id_from_url(str(value)) if value else None
        if advisory_id:
            return advisory_id

    source = detail.get("source") if detail else None
    if isinstance(source, int):
        return f"NPM-{source}"
    if isinstance(source, str) and source.strip():
        return f"NPM-{source.strip()}"
    return package_name


def _npm_advisory_title(package_name: str, advisory: dict[str, Any], detail: dict[str, Any] | None) -> str:
    title = detail.get("title") if detail else None
    if isinstance(title, str) and title.strip():
        return title.strip()
    via_names = _via_names(advisory)
    if via_names:
        return f"{package_name} vulnerability via {', '.join(via_names)}"
    return f"{package_name} vulnerability reported by npm audit"


def _npm_advisory_score(detail: dict[str, Any] | None) -> float | None:
    cvss = detail.get("cvss") if detail else None
    if not isinstance(cvss, dict):
        return None
    score = cvss.get("score")
    return float(score) if isinstance(score, (int, float)) else None


def _parse_npm_audit_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    advisories = report.get("advisories")
    if not isinstance(advisories, dict):
        return []

    findings: list[dict[str, Any]] = []
    for package_key, advisory_payload in advisories.items():
        if not isinstance(advisory_payload, dict):
            continue
        package_name = str(advisory_payload.get("name") or package_key)
        severity = str(advisory_payload.get("severity") or "UNKNOWN").upper()
        detail = _best_npm_advisory_detail(advisory_payload, severity)
        if detail is None:
            continue
        nodes = advisory_payload.get("nodes")
        target = ", ".join(str(node) for node in nodes) if isinstance(nodes, list) else None
        findings.append(
            {
                "layer": "UI",
                "id": _npm_advisory_id(package_name, advisory_payload, detail),
                "severity": severity,
                "packageName": package_name,
                "installedVersion": None,
                "fixedVersion": None,
                "target": target,
                "title": _npm_advisory_title(package_name, advisory_payload, detail),
                "status": "FAILED",
                "score": _npm_advisory_score(detail),
            }
        )
    return findings


def _parse_npm_audit_log_findings(log_text: str) -> list[dict[str, Any]]:
    report = _extract_npm_audit_report_from_log(log_text)
    if report is None:
        return []

    findings = _parse_npm_audit_findings(report)
    vulnerable_advisory_ids = _audit_ci_vulnerable_advisory_ids(log_text)
    if vulnerable_advisory_ids is not None:
        return [
            finding
            for finding in findings
            if str(finding.get("id") or "") in vulnerable_advisory_ids
        ]

    if not _audit_ci_failed_security_audit(log_text):
        return []

    allowlisted_advisory_ids = _audit_ci_allowlisted_advisory_ids(log_text)
    if allowlisted_advisory_ids:
        return [
            finding
            for finding in findings
            if str(finding.get("id") or "") not in allowlisted_advisory_ids
        ]
    return findings


def _stage_href(stage: dict[str, Any], link_name: str) -> str | None:
    links = stage.get("_links")
    if not isinstance(links, dict):
        return None
    link = links.get(link_name)
    if not isinstance(link, dict):
        return None
    href = link.get("href")
    return href if isinstance(href, str) and href else None


def _stage_detail(stage: dict[str, Any], build_url: str, runtime: JenkinsRuntimeConfig) -> dict[str, Any]:
    if isinstance(stage.get("stageFlowNodes"), list):
        return stage
    href = _stage_href(stage, "self")
    if not href:
        return stage
    try:
        detail = _http_json_get(_absolute_jenkins_url(build_url, href), runtime)
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError):
        return stage
    return detail if isinstance(detail, dict) else stage


def _parse_ui_audit_findings_from_workflow(
    workflow: dict[str, Any],
    build_url: str | None,
    runtime: JenkinsRuntimeConfig,
) -> list[dict[str, Any]]:
    if not build_url:
        return []

    findings: list[dict[str, Any]] = []
    stages = workflow.get("stages") if isinstance(workflow.get("stages"), list) else []
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("name") != "UI":
            continue
        stage_detail = _stage_detail(stage, build_url, runtime)
        for node in stage_detail.get("stageFlowNodes") or []:
            if not isinstance(node, dict):
                continue
            description = str(node.get("parameterDescription") or "")
            if "ui:securityAudit" not in description:
                continue
            log_href = _stage_href(node, "log")
            if not log_href:
                continue
            try:
                log_payload = _http_json_get(_absolute_jenkins_url(build_url, log_href), runtime)
            except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError):
                continue
            log_text = log_payload.get("text") if isinstance(log_payload, dict) else None
            if isinstance(log_text, str):
                findings.extend(_parse_npm_audit_log_findings(log_text))

    return _dedupe_findings(findings)


def _dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        key = (
            str(finding.get("layer") or ""),
            str(finding.get("id") or ""),
            str(finding.get("packageName") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def _latest_trivy_report_for_build(build_url: str, runtime: JenkinsRuntimeConfig) -> tuple[dict[str, Any] | None, str | None]:
    artifacts_url = f"{build_url.rstrip('/')}/wfapi/artifacts"
    artifacts = _http_json_get(artifacts_url, runtime)
    if not isinstance(artifacts, list):
        return (None, None)

    candidates: list[tuple[str, str]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        name = str(artifact.get("name") or "")
        relative_url = artifact.get("url")
        if not name.endswith(".json") or not isinstance(relative_url, str):
            continue
        candidates.append((name, urljoin(f"{build_url.rstrip('/')}/", relative_url)))

    for _, artifact_url in sorted(candidates, key=lambda item: _trivy_artifact_sort_key(item[0]), reverse=True):
        report = _http_json_get(artifact_url, runtime)
        if isinstance(report, dict) and report.get("Results"):
            return (report, report.get("ArtifactName") if isinstance(report.get("ArtifactName"), str) else None)

    return (None, None)


def _latest_trivy_report(job_url: str, runtime: JenkinsRuntimeConfig) -> tuple[dict[str, Any] | None, str | None]:
    return _latest_trivy_report_for_build(f"{job_url.rstrip('/')}/lastBuild/", runtime)


def _update_layer_counts(layers: dict[str, dict[str, Any]], findings: list[dict[str, Any]]) -> None:
    by_layer: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        by_layer.setdefault(str(finding.get("layer") or "Unknown"), []).append(finding)

    for layer_name, layer_findings in by_layer.items():
        layer = layers.setdefault(layer_name, _empty_layer(layer_name))
        counter = Counter(str(finding.get("severity") or "UNKNOWN").upper() for finding in layer_findings)
        layer["findingCount"] = len(layer_findings)
        layer["failedFindingCount"] = sum(1 for finding in layer_findings if finding.get("status") != "SKIPPED")
        layer["skippedFindingCount"] = sum(1 for finding in layer_findings if finding.get("status") == "SKIPPED")
        layer["severityCounts"] = {severity.lower(): counter.get(severity, 0) for severity in SEVERITIES}


def _exclude_unknown_severity(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        finding
        for finding in findings
        if str(finding.get("severity") or "UNKNOWN").upper() != "UNKNOWN"
    ]


def _jira_issue_url(base_url: str, issue_key: str) -> str:
    return f"{base_url.rstrip('/')}/browse/{issue_key}"


def _jira_create_issue_url(base_url: str, params: dict[str, JiraCreateParamValue]) -> str:
    return f"{base_url.rstrip('/')}/secure/CreateIssueDetails!init.jspa?{urlencode(params, doseq=True)}"


def _jira_default_create_issue_url(base_url: str, finding: dict[str, Any]) -> str:
    params = {
        "summary": _jira_create_summary(finding),
        "description": _jira_create_description(finding),
        "assignee": "-1",
    }
    return f"{base_url.rstrip('/')}/secure/CreateIssue!default.jspa?{urlencode(params)}"


def _jql_text_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _build_vulnerability_jira_jql(vulnerability_id: str, project_key: str | None) -> str:
    clauses = []
    if project_key:
        clauses.append(f"project = {project_key}")
    clauses.append(f"text ~ {_jql_text_literal(vulnerability_id)}")
    return f"{' AND '.join(clauses)} ORDER BY updated DESC"


def _parse_jira_datetime_value(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _latest_comment_updated(fields: dict[str, Any]) -> datetime | None:
    comment_payload = fields.get("comment")
    if not isinstance(comment_payload, dict):
        return None

    latest: datetime | None = None
    for comment in comment_payload.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        parsed = _parse_jira_datetime_value(comment.get("updated")) or _parse_jira_datetime_value(comment.get("created"))
        if parsed and (latest is None or parsed > latest):
            latest = parsed
    return latest


def _jira_assignee_name(fields: dict[str, Any]) -> str | None:
    assignee = fields.get("assignee")
    if not isinstance(assignee, dict):
        return None
    for key in ("displayName", "name", "accountId"):
        value = assignee.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _jira_card_from_raw_issue(base_url: str, raw_issue: dict[str, Any]) -> dict[str, Any]:
    fields = raw_issue.get("fields") if isinstance(raw_issue.get("fields"), dict) else {}
    status = fields.get("status") if isinstance(fields.get("status"), dict) else {}
    status_category = status.get("statusCategory") if isinstance(status.get("statusCategory"), dict) else {}
    issue_key = str(raw_issue.get("key") or "")
    latest_comment = _latest_comment_updated(fields)
    return {
        "issueKey": issue_key,
        "summary": str(fields.get("summary") or ""),
        "status": str(status.get("name") or ""),
        "statusCategory": status_category.get("name") if isinstance(status_category.get("name"), str) else None,
        "issueUrl": _jira_issue_url(base_url, issue_key),
        "assignee": _jira_assignee_name(fields),
        "latestCommentAt": latest_comment.isoformat() if latest_comment else None,
    }


def _jira_issue_priority(raw_issue: dict[str, Any]) -> tuple[int, datetime, datetime, str]:
    fields = raw_issue.get("fields") if isinstance(raw_issue.get("fields"), dict) else {}
    assignee_name = _jira_assignee_name(fields)
    latest_comment = _latest_comment_updated(fields) or datetime.min.replace(tzinfo=timezone.utc)
    issue_updated = _parse_jira_datetime_value(fields.get("updated")) or datetime.min.replace(tzinfo=timezone.utc)
    return (1 if assignee_name else 0, latest_comment, issue_updated, str(raw_issue.get("key") or ""))


def _clean_optional_string(value: Any) -> str | None:
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _security_template_field_defaults() -> dict[str, str]:
    return {
        os.environ.get("JIRA_SECURITY_DEPENDENCY_POSSIBILITIES_FIELD", DEFAULT_JIRA_DEPENDENCY_POSSIBILITIES_FIELD): (
            os.environ.get("JIRA_SECURITY_DEPENDENCY_OTHER_OPTION", DEFAULT_JIRA_DEPENDENCY_OTHER_OPTION)
        ),
        os.environ.get("JIRA_SECURITY_REQUIREMENT_CATEGORY_FIELD", DEFAULT_JIRA_REQUIREMENT_CATEGORY_FIELD): (
            os.environ.get("JIRA_SECURITY_REQUIREMENT_FEATURE_OPTION", DEFAULT_JIRA_REQUIREMENT_FEATURE_OPTION)
        ),
        os.environ.get("JIRA_SECURITY_ACTIVITY_TYPE_FIELD", DEFAULT_JIRA_ACTIVITY_TYPE_FIELD): (
            os.environ.get("JIRA_SECURITY_ACTIVITY_PLANNED_OPTION", DEFAULT_JIRA_ACTIVITY_PLANNED_OPTION)
        ),
        os.environ.get("JIRA_SECURITY_PRODUCT_FIELD", DEFAULT_JIRA_PRODUCT_FIELD): (
            os.environ.get("JIRA_SECURITY_PRODUCT_ACONEX_OPTION", DEFAULT_JIRA_PRODUCT_ACONEX_OPTION)
        ),
        os.environ.get("JIRA_SECURITY_EPIC_LINK_FIELD", DEFAULT_JIRA_EPIC_LINK_FIELD): (
            os.environ.get("JIRA_SECURITY_EPIC_LINK", DEFAULT_JIRA_SECURITY_EPIC_LINK)
        ),
    }


def _security_template_field_names() -> tuple[str, ...]:
    return tuple(_security_template_field_defaults().keys())


def _coerce_jira_create_param(value: Any) -> JiraCreateParamValue | None:
    if value is None:
        return None
    if isinstance(value, list):
        values = [
            coerced
            for item in value
            if (coerced := _coerce_jira_create_param(item)) is not None
        ]
        flattened: list[str] = []
        for coerced in values:
            if isinstance(coerced, list):
                flattened.extend(coerced)
            else:
                flattened.append(coerced)
        return flattened or None
    if isinstance(value, dict):
        for key in ("id", "key", "value", "name"):
            coerced = _clean_optional_string(value.get(key))
            if coerced:
                return coerced
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return _clean_optional_string(value)


def _template_params_from_sample_fields(fields: dict[str, Any]) -> dict[str, JiraCreateParamValue]:
    params: dict[str, JiraCreateParamValue] = {}
    for field_name in _security_template_field_names():
        coerced = _coerce_jira_create_param(fields.get(field_name))
        if coerced is not None:
            params[field_name] = coerced

    labels = _coerce_jira_create_param(fields.get("labels"))
    if labels is not None:
        params["labels"] = labels

    components = _coerce_jira_create_param(fields.get("components"))
    if components is not None:
        params["components"] = components

    return params


def _default_jira_template_params() -> dict[str, JiraCreateParamValue]:
    return dict(_security_template_field_defaults())


def _template_with_defaults(template: dict[str, Any]) -> dict[str, Any]:
    params = _default_jira_template_params()
    sample_params = template.get("_templateParams")
    if isinstance(sample_params, dict):
        params.update(sample_params)
    return {**template, "_templateParams": params}


def _default_jira_create_template() -> dict[str, Any] | None:
    project_id = _clean_optional_string(os.environ.get("JIRA_SECURITY_CREATE_PROJECT_ID")) or DEFAULT_JIRA_CREATE_PROJECT_ID
    issue_type_id = (
        _clean_optional_string(os.environ.get("JIRA_SECURITY_CREATE_ISSUE_TYPE_ID"))
        or DEFAULT_JIRA_CREATE_ISSUE_TYPE_ID
    )
    if not project_id or not issue_type_id:
        return None
    return _template_with_defaults({"pid": project_id, "issuetype": issue_type_id})


def _with_active_sprint(
    template: dict[str, Any],
    connector: JiraRestConnector,
    jira_config: JiraRuntimeConfig,
) -> dict[str, Any]:
    sprint_id = _active_sprint_id(connector, jira_config)
    if sprint_id:
        template["_activeSprintId"] = sprint_id
    return template


def _load_jira_create_template_from_sample(
    connector: JiraRestConnector,
    jira_config: JiraRuntimeConfig,
    sample_issue_key: str,
) -> dict[str, Any] | None:
    template_fields = ",".join(("project", "issuetype", "labels", "components", *_security_template_field_names()))
    payload = connector._request_json(
        f"/rest/api/2/issue/{sample_issue_key}",
        params={"fields": template_fields},
    )
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    project = fields.get("project") if isinstance(fields.get("project"), dict) else {}
    issue_type = fields.get("issuetype") if isinstance(fields.get("issuetype"), dict) else {}
    project_id = project.get("id")
    issue_type_id = issue_type.get("id")
    if not isinstance(project_id, str) or not isinstance(issue_type_id, str):
        return None
    return _with_active_sprint(
        _template_with_defaults(
            {
                "pid": project_id,
                "issuetype": issue_type_id,
                "_templateParams": _template_params_from_sample_fields(fields),
            }
        ),
        connector,
        jira_config,
    )


def _select_jira_create_issue_type_id(issue_types: list[Any]) -> str | None:
    configured_issue_type_id = _clean_optional_string(os.environ.get("JIRA_SECURITY_CREATE_ISSUE_TYPE_ID"))
    if configured_issue_type_id:
        return configured_issue_type_id

    configured_issue_type_name = (
        _clean_optional_string(os.environ.get("JIRA_SECURITY_CREATE_ISSUE_TYPE_NAME"))
        or DEFAULT_JIRA_CREATE_ISSUE_TYPE_NAME
    )
    for issue_type in issue_types:
        if not isinstance(issue_type, dict):
            continue
        issue_type_id = _clean_optional_string(issue_type.get("id"))
        issue_type_name = _clean_optional_string(issue_type.get("name"))
        if issue_type_id and issue_type_name and issue_type_name.lower() == configured_issue_type_name.lower():
            return issue_type_id

    for issue_type in issue_types:
        if not isinstance(issue_type, dict):
            continue
        issue_type_id = _clean_optional_string(issue_type.get("id"))
        if issue_type_id and issue_type.get("subtask") is not True:
            return issue_type_id

    for issue_type in issue_types:
        if not isinstance(issue_type, dict):
            continue
        issue_type_id = _clean_optional_string(issue_type.get("id"))
        if issue_type_id:
            return issue_type_id
    return None


def _load_jira_create_template_from_project(
    connector: JiraRestConnector,
    jira_config: JiraRuntimeConfig,
) -> dict[str, Any] | None:
    configured_project_id = _clean_optional_string(os.environ.get("JIRA_SECURITY_CREATE_PROJECT_ID"))
    configured_issue_type_id = _clean_optional_string(os.environ.get("JIRA_SECURITY_CREATE_ISSUE_TYPE_ID"))
    if configured_project_id and configured_issue_type_id:
        return _with_active_sprint(
            _template_with_defaults({"pid": configured_project_id, "issuetype": configured_issue_type_id}),
            connector,
            jira_config,
        )

    project_key = (
        _clean_optional_string(os.environ.get("JIRA_SECURITY_CREATE_PROJECT_KEY"))
        or _clean_optional_string(jira_config.project_key)
    )
    if not project_key:
        return None

    try:
        payload = connector._request_json(f"/rest/api/2/project/{project_key}")
    except JiraAPIError:
        payload = {}
    project_id = configured_project_id or _clean_optional_string(payload.get("id"))
    issue_types = payload.get("issueTypes") if isinstance(payload.get("issueTypes"), list) else []
    issue_type_id = _select_jira_create_issue_type_id(issue_types)
    if project_id and issue_type_id:
        return _with_active_sprint(
            _template_with_defaults({"pid": project_id, "issuetype": issue_type_id}),
            connector,
            jira_config,
        )

    try:
        create_meta = connector._request_json(
            "/rest/api/2/issue/createmeta",
            params={"projectKeys": project_key, "expand": "projects.issuetypes"},
        )
    except JiraAPIError:
        return None
    projects = create_meta.get("projects") if isinstance(create_meta.get("projects"), list) else []
    for project in projects:
        if not isinstance(project, dict):
            continue
        project_id = configured_project_id or _clean_optional_string(project.get("id"))
        issue_types = project.get("issuetypes") if isinstance(project.get("issuetypes"), list) else []
        issue_type_id = _select_jira_create_issue_type_id(issue_types)
        if project_id and issue_type_id:
            return _with_active_sprint(
                _template_with_defaults({"pid": project_id, "issuetype": issue_type_id}),
                connector,
                jira_config,
            )
    return None


def _load_jira_create_template(connector: JiraRestConnector, jira_config: JiraRuntimeConfig) -> dict[str, Any] | None:
    sample_issue_key = os.environ.get("JIRA_SECURITY_CREATE_SAMPLE_KEY", DEFAULT_JIRA_CREATE_SAMPLE_ISSUE_KEY).strip()
    if sample_issue_key:
        try:
            sample_template = _load_jira_create_template_from_sample(connector, jira_config, sample_issue_key)
        except JiraAPIError:
            sample_template = None
        if sample_template:
            return sample_template

    project_template = _load_jira_create_template_from_project(connector, jira_config)
    if project_template:
        return project_template

    default_template = _default_jira_create_template()
    if default_template:
        return _with_active_sprint(default_template, connector, jira_config)
    return None


def _active_sprint_id(connector: JiraRestConnector, jira_config: JiraRuntimeConfig) -> str | None:
    if jira_config.board_id is None:
        return None
    try:
        payload = connector._request_json(
            f"/rest/agile/1.0/board/{jira_config.board_id}/sprint",
            params={"state": "active", "startAt": 0, "maxResults": 1},
        )
        for sprint in payload.get("values") or []:
            if not isinstance(sprint, dict):
                continue
            sprint_id = sprint.get("id")
            if isinstance(sprint_id, int):
                return str(sprint_id)
            if isinstance(sprint_id, str) and sprint_id.strip():
                return sprint_id.strip()
    except JiraAPIError:
        pass
    return _local_active_sprint_id(jira_config)


def _local_active_sprint_id(jira_config: JiraRuntimeConfig) -> str | None:
    if jira_config.board_id is None:
        return None
    try:
        conn = sqlite3.connect(_resolve_db_path())
        try:
            _ensure_schema(conn)
            row = conn.execute(
                """
                SELECT external_sprint_id
                FROM sprints
                WHERE lower(state) = 'active'
                  AND board_external_id = ?
                ORDER BY
                  CASE WHEN start_date IS NULL THEN 1 ELSE 0 END ASC,
                  datetime(start_date) DESC,
                  datetime(updated_at) DESC,
                  external_sprint_id DESC
                LIMIT 1
                """,
                (jira_config.board_id,),
            ).fetchone()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - local sprint fallback must not block create links.
        return None
    if row is None:
        return None
    return str(row[0])


def _jira_create_summary(finding: dict[str, Any]) -> str:
    severity = str(finding.get("severity") or "Unknown").title()
    vulnerability_id = str(finding.get("id") or "vulnerability")
    layer = str(finding.get("layer") or "security")
    return f"Remediate {severity} severity {layer} vulnerability {vulnerability_id}"


def _jira_create_description(finding: dict[str, Any]) -> str:
    lines = [
        "Security audit vulnerability finding.",
        "",
        f"Vulnerability: {finding.get('id') or 'n/a'}",
        f"Severity: {finding.get('severity') or 'n/a'}",
        f"Layer: {finding.get('layer') or 'n/a'}",
        f"Package: {finding.get('packageName') or 'n/a'}",
        f"Installed version: {finding.get('installedVersion') or 'n/a'}",
    ]
    title = str(finding.get("title") or "").strip()
    if title:
        lines.extend(["", title])
    return "\n".join(lines)


def _jira_create_acceptance_criteria(finding: dict[str, Any]) -> str:
    vulnerability_id = str(finding.get("id") or "vulnerability")
    return "\n".join(
        [
            f"* {vulnerability_id} is remediated and Security Audit Pipeline completed successfully.",
            "* Manifest with the latest base image is deployed in PL6 successfully.",
            "* Sanity test completed for the manifest deployed in PL6.",
        ]
    )


def _build_jira_create_url(
    jira_config: JiraRuntimeConfig,
    create_template: dict[str, Any] | None,
    finding: dict[str, Any],
) -> str | None:
    if not create_template:
        return _jira_default_create_issue_url(jira_config.base_url, finding)
    template_params = create_template.get("_templateParams")
    params: dict[str, JiraCreateParamValue] = {}
    if isinstance(template_params, dict):
        for key, value in template_params.items():
            if isinstance(key, str) and (coerced := _coerce_jira_create_param(value)) is not None:
                params[key] = coerced

    params.update(
        {
            "pid": create_template["pid"],
            "issuetype": create_template["issuetype"],
            "summary": _jira_create_summary(finding),
            "description": _jira_create_description(finding),
            os.environ.get("JIRA_SECURITY_ACCEPTANCE_CRITERIA_FIELD", DEFAULT_JIRA_ACCEPTANCE_CRITERIA_FIELD): (
                _jira_create_acceptance_criteria(finding)
            ),
            "assignee": "-1",
        }
    )
    sprint_id = create_template.get("_activeSprintId")
    if sprint_id:
        params[os.environ.get("JIRA_SECURITY_SPRINT_FIELD", DEFAULT_JIRA_SPRINT_FIELD)] = sprint_id
    return _jira_create_issue_url(
        jira_config.base_url,
        params,
    )


def _find_jira_card_for_vulnerability(
    connector: JiraRestConnector,
    jira_config: JiraRuntimeConfig,
    vulnerability_id: str,
) -> dict[str, Any] | None:
    payload = connector._request_json(
        "/rest/api/2/search",
        params={
            "jql": _build_vulnerability_jira_jql(vulnerability_id, jira_config.project_key),
            "startAt": 0,
            "maxResults": JIRA_CARD_SEARCH_LIMIT,
            "fields": "summary,status,assignee,comment,updated",
        },
    )
    issues = [issue for issue in payload.get("issues") or [] if isinstance(issue, dict)]
    if not issues:
        return None

    selected = max(issues, key=_jira_issue_priority)
    return _jira_card_from_raw_issue(jira_config.base_url, selected)


def _attach_jira_cards(findings: list[dict[str, Any]]) -> None:
    vulnerability_ids = sorted(
        {
            str(finding.get("id")).strip()
            for finding in findings
            if isinstance(finding.get("id"), str) and str(finding.get("id")).strip()
        }
    )
    for finding in findings:
        finding["jiraCard"] = None
        finding["jiraCreateUrl"] = None

    if not vulnerability_ids:
        return

    try:
        jira_config = JiraRuntimeConfig.from_env()
        connector = JiraRestConnector(
            config=jira_config.to_connector_config(),
            project_key=jira_config.project_key,
            story_points_field=jira_config.story_points_field,
            epic_link_field=jira_config.epic_link_field,
            sprint_field_candidates=jira_config.sprint_field_candidates,
        )
    except (ValueError, TypeError):
        return

    cards_by_vulnerability: dict[str, dict[str, Any] | None] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(vulnerability_ids) + 1)) as executor:
        create_template_future = executor.submit(_load_jira_create_template, connector, jira_config)
        card_futures = {
            vulnerability_id: executor.submit(
                _find_jira_card_for_vulnerability,
                connector,
                jira_config,
                vulnerability_id,
            )
            for vulnerability_id in vulnerability_ids
        }

        try:
            create_template = create_template_future.result()
        except JiraAPIError:
            create_template = None

        for vulnerability_id, future in card_futures.items():
            try:
                cards_by_vulnerability[vulnerability_id] = future.result()
            except JiraAPIError:
                cards_by_vulnerability[vulnerability_id] = None

    for finding in findings:
        vulnerability_id = str(finding.get("id") or "").strip()
        jira_card = cards_by_vulnerability.get(vulnerability_id)
        finding["jiraCard"] = jira_card
        if jira_card is None:
            finding["jiraCreateUrl"] = _build_jira_create_url(jira_config, create_template, finding)

def _build_findings_for_trend(build_url: str, runtime: JenkinsRuntimeConfig) -> list[dict[str, Any]]:
    cached_findings = _cached_trend_findings(build_url)
    if cached_findings is not None:
        return cached_findings

    findings: list[dict[str, Any]] = []
    had_error = False

    try:
        test_report = _http_json_get(_build_test_report_url_for_build(build_url), runtime)
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError):
        test_report = {}
        had_error = True
    if isinstance(test_report, dict):
        findings.extend(_parse_backend_findings(test_report))

    try:
        trivy_report, _ = _latest_trivy_report_for_build(build_url, runtime)
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError):
        trivy_report = None
        had_error = True
    if trivy_report is not None:
        findings.extend(_parse_trivy_report(trivy_report))

    try:
        workflow = _http_json_get(_build_workflow_url_for_build(build_url), runtime)
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError):
        workflow = {}
        had_error = True
    if isinstance(workflow, dict):
        findings.extend(_parse_ui_audit_findings_from_workflow(workflow, build_url, runtime))

    findings = _exclude_unknown_severity(findings)
    if not had_error:
        _store_trend_findings_cache(build_url, findings)
    return findings


def _selected_trend_builds(job: dict[str, Any]) -> list[dict[str, Any]]:
    builds = job.get("builds") if isinstance(job.get("builds"), list) else []
    return [
        build
        for build in builds[:5]
        if isinstance(build, dict) and isinstance(build.get("url"), str)
    ]


def _is_same_build_url(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return left.rstrip("/") == right.rstrip("/")


def _vulnerability_trend_point(build: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    severity_counter = Counter(str(finding.get("severity") or "UNKNOWN").upper() for finding in findings)
    return {
        "buildNumber": build.get("number"),
        "buildUrl": build.get("url"),
        "status": build.get("result"),
        "startedAt": _millis_to_iso(build.get("timestamp")),
        "totalFindings": len(findings),
        "severityCounts": {severity.lower(): severity_counter.get(severity, 0) for severity in SEVERITIES},
    }


def _sort_vulnerability_trend(trend: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trend.sort(key=lambda item: int(item.get("buildNumber") or 0))
    return trend


def _build_vulnerability_trend_for_builds(
    builds: list[dict[str, Any]],
    runtime: JenkinsRuntimeConfig,
) -> list[dict[str, Any]]:
    if not builds:
        return []

    def trend_point(build: dict[str, Any]) -> dict[str, Any]:
        findings = _build_findings_for_trend(str(build["url"]), runtime)
        return _vulnerability_trend_point(build, findings)

    with ThreadPoolExecutor(max_workers=min(5, len(builds))) as executor:
        trend = list(executor.map(trend_point, builds))

    return _sort_vulnerability_trend(trend)


def _build_vulnerability_trend(
    job: dict[str, Any],
    runtime: JenkinsRuntimeConfig,
    latest_build_url: str | None = None,
    latest_findings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    selected_builds = _selected_trend_builds(job)
    if not selected_builds:
        return []

    trend: list[dict[str, Any]] = []
    builds_to_fetch: list[dict[str, Any]] = []
    for build in selected_builds:
        build_url = str(build["url"])
        if _is_same_build_url(latest_build_url, build_url) and latest_findings is not None:
            trend.append(_vulnerability_trend_point(build, latest_findings))
        else:
            builds_to_fetch.append(build)

    trend.extend(_build_vulnerability_trend_for_builds(builds_to_fetch, runtime))
    return _sort_vulnerability_trend(trend)


def get_security_audit() -> dict[str, Any]:
    load_env_files()
    cached_payload = _cached_security_audit()
    if cached_payload is not None:
        return cached_payload

    base_payload: dict[str, Any] = {
        "source": "jenkins_security_audit",
        "generatedAt": _utc_iso_now(),
        "pipeline": {},
        "summary": {},
        "layers": [],
        "findings": [],
        "trend": [],
        "cached": False,
        "error": None,
    }

    try:
        runtime = _load_security_runtime()
        with ThreadPoolExecutor(max_workers=5) as executor:
            job_future = executor.submit(_http_json_get, _build_job_api_url(runtime.job_url), runtime)
            workflow_future = executor.submit(
                _http_json_get,
                f"{runtime.job_url.rstrip('/')}/lastBuild/wfapi/describe",
                runtime,
            )
            test_report_future = executor.submit(_http_json_get, _build_test_report_url(runtime.job_url), runtime)
            trivy_future = executor.submit(_latest_trivy_report, runtime.job_url, runtime)

            job_result = job_future.result()
            job = job_result if isinstance(job_result, dict) else {}
            last_build = job.get("lastBuild") if isinstance(job.get("lastBuild"), dict) else {}
            latest_build_url = last_build.get("url") if isinstance(last_build.get("url"), str) else None
            latest_trend_build: dict[str, Any] | None = None
            historical_trend_builds: list[dict[str, Any]] = []
            for build in _selected_trend_builds(job):
                build_url = str(build["url"])
                if _is_same_build_url(latest_build_url, build_url):
                    latest_trend_build = build
                else:
                    historical_trend_builds.append(build)
            historical_trend_future = executor.submit(
                _build_vulnerability_trend_for_builds,
                historical_trend_builds,
                runtime,
            )

            workflow_result = workflow_future.result()
            workflow = workflow_result if isinstance(workflow_result, dict) else {}
            test_report = test_report_future.result()
            trivy_report, trivy_artifact_name = trivy_future.result()

            stages = workflow.get("stages") if isinstance(workflow.get("stages"), list) else []
            stage_by_name = {
                stage.get("name"): stage
                for stage in stages
                if isinstance(stage, dict) and isinstance(stage.get("name"), str)
            }
            layers = {name: _empty_layer(name, stage_by_name.get(name)) for name in SECURITY_LAYER_NAMES}

            findings = _parse_backend_findings(test_report if isinstance(test_report, dict) else {})
            if trivy_report is not None:
                findings.extend(_parse_trivy_report(trivy_report))
            findings.extend(_parse_ui_audit_findings_from_workflow(workflow, latest_build_url, runtime))
            findings = _exclude_unknown_severity(findings)
            latest_findings_for_trend = [dict(finding) for finding in findings]

            _update_layer_counts(layers, findings)

            severity_counter = Counter(str(finding.get("severity") or "UNKNOWN").upper() for finding in findings)
            failed_layers = [
                name
                for name, layer in layers.items()
                if layer.get("stageStatus") not in {"SUCCESS"} or int(layer.get("failedFindingCount") or 0) > 0
            ]
            passed_layers = [name for name in SECURITY_LAYER_NAMES if name not in failed_layers]

            jira_future = executor.submit(_attach_jira_cards, findings)
            trend = historical_trend_future.result()
            if latest_trend_build is not None:
                trend.append(_vulnerability_trend_point(latest_trend_build, latest_findings_for_trend))
                trend = _sort_vulnerability_trend(trend)
            jira_future.result()
    except ValueError as exc:
        base_payload["error"] = str(exc)
        return base_payload
    except HTTPError as exc:
        base_payload["error"] = f"Jenkins security audit request failed with HTTP {exc.code}."
        return base_payload
    except URLError as exc:
        base_payload["error"] = f"Jenkins security audit request failed: {exc.reason}"
        return base_payload
    except Exception as exc:  # noqa: BLE001
        base_payload["error"] = f"Unexpected security audit failure: {exc}"
        return base_payload

    base_payload["pipeline"] = {
        "jobName": job.get("fullName") or job.get("displayName"),
        "jobUrl": runtime.job_url,
        "buildNumber": workflow.get("id") or last_build.get("number"),
        "buildUrl": last_build.get("url"),
        "status": workflow.get("status") or last_build.get("result"),
        "startedAt": _millis_to_iso(workflow.get("startTimeMillis")),
        "durationMillis": workflow.get("durationMillis"),
        "trivyArtifactName": trivy_artifact_name,
    }
    base_payload["summary"] = {
        "totalFindings": len(findings),
        "failedFindings": sum(1 for finding in findings if finding.get("status") != "SKIPPED"),
        "skippedFindings": sum(1 for finding in findings if finding.get("status") == "SKIPPED"),
        "severityCounts": {severity.lower(): severity_counter.get(severity, 0) for severity in SEVERITIES},
        "failedLayerCount": len(failed_layers),
        "passedLayerCount": len(passed_layers),
        "failedLayers": failed_layers,
        "passedLayers": passed_layers,
    }

    base_payload["layers"] = [layers[name] for name in SECURITY_LAYER_NAMES]
    base_payload["findings"] = findings
    base_payload["trend"] = trend
    _store_security_audit_cache(base_payload)
    return base_payload
