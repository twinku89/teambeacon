from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from packages.connectors.jenkins_config import JenkinsRuntimeConfig
from packages.connectors.jira_config import load_env_files
from packages.connectors.tls import create_ssl_context


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auth_headers(runtime: JenkinsRuntimeConfig) -> dict[str, str]:
    auth_blob = f"{runtime.username}:{runtime.api_token}".encode("utf-8")
    encoded = base64.b64encode(auth_blob).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def _job_api_url(job_url: str) -> str:
    query = urlencode(
        {
            "tree": (
                "displayName,fullName,url,buildable,"
                "lastBuild[number,url,result,timestamp],"
                "lastSuccessfulBuild[number,url,timestamp]"
            )
        }
    )
    return f"{job_url.rstrip('/')}/api/json?{query}"


def _decode_json_object(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _format_url_error(error: URLError, runtime: JenkinsRuntimeConfig) -> str:
    detail = str(error.reason)
    if "CERTIFICATE_VERIFY_FAILED" not in detail:
        return f"Jenkins request failed: {detail}"
    if runtime.ca_bundle_path:
        return (
            f"Jenkins request failed: {detail}. Python could not validate the Jenkins TLS certificate "
            f"using the configured CA bundle at {runtime.ca_bundle_path}."
        )
    return (
        f"Jenkins request failed: {detail}. Set JENKINS_CA_BUNDLE or ATLASSIAN_CA_BUNDLE in config/.env "
        "to a PEM file containing the required CA certificate chain, then restart the API."
    )


def get_jenkins_status() -> dict[str, Any]:
    load_env_files()
    base_payload: dict[str, Any] = {
        "source": "jenkins",
        "connected": False,
        "checkedAt": _utc_iso_now(),
        "config": {},
        "checks": [],
        "metrics": {},
        "error": None,
    }

    try:
        runtime = JenkinsRuntimeConfig.from_env()
    except ValueError as exc:
        base_payload["error"] = str(exc)
        base_payload["checks"].append(
            {
                "name": "configuration",
                "ok": False,
                "detail": "Required Jenkins environment variables are missing.",
            }
        )
        return base_payload

    base_payload["config"] = {
        "jobUrl": runtime.job_url,
        "authUser": runtime.username,
        "timeoutSeconds": runtime.timeout_seconds,
    }

    request = Request(
        url=_job_api_url(runtime.job_url),
        headers={"Accept": "application/json", **_auth_headers(runtime)},
        method="GET",
    )

    try:
        ssl_context = create_ssl_context(runtime.ca_bundle_path)
        with urlopen(request, timeout=runtime.timeout_seconds, context=ssl_context) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = f"Jenkins job request failed with HTTP {exc.code}."
        base_payload["error"] = detail
        base_payload["checks"].append({"name": "job_api", "ok": False, "detail": detail})
        return base_payload
    except URLError as exc:
        detail = _format_url_error(exc, runtime)
        base_payload["error"] = detail
        base_payload["checks"].append({"name": "job_api", "ok": False, "detail": detail})
        return base_payload
    except Exception as exc:  # noqa: BLE001
        detail = f"Unexpected Jenkins job request failure: {exc}"
        base_payload["error"] = detail
        base_payload["checks"].append({"name": "job_api", "ok": False, "detail": detail})
        return base_payload

    payload = _decode_json_object(raw)
    if payload is None:
        detail = "Jenkins job response was not valid JSON."
        base_payload["error"] = detail
        base_payload["checks"].append({"name": "job_api", "ok": False, "detail": detail})
        return base_payload

    job_name = payload.get("fullName") or payload.get("displayName")
    job_url = payload.get("url") if isinstance(payload.get("url"), str) else runtime.job_url
    last_build = payload.get("lastBuild") if isinstance(payload.get("lastBuild"), dict) else {}
    last_successful_build = (
        payload.get("lastSuccessfulBuild") if isinstance(payload.get("lastSuccessfulBuild"), dict) else {}
    )

    base_payload["connected"] = True
    base_payload["config"]["resolvedJobUrl"] = job_url
    base_payload["metrics"] = {
        "jobName": job_name if isinstance(job_name, str) else None,
        "buildable": payload.get("buildable") if isinstance(payload.get("buildable"), bool) else None,
        "lastBuildNumber": last_build.get("number") if isinstance(last_build.get("number"), int) else None,
        "lastBuildResult": last_build.get("result") if isinstance(last_build.get("result"), str) else None,
        "lastSuccessfulBuildNumber": (
            last_successful_build.get("number") if isinstance(last_successful_build.get("number"), int) else None
        ),
    }
    base_payload["checks"].append(
        {
            "name": "job_api",
            "ok": True,
            "detail": f"Jenkins job API is reachable{f' ({job_name})' if isinstance(job_name, str) else ''}.",
        }
    )
    return base_payload
