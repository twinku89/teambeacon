from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from packages.connectors.confluence_config import ConfluenceRuntimeConfig
from packages.connectors.jira_config import load_env_files
from packages.connectors.tls import create_ssl_context


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auth_headers(runtime: ConfluenceRuntimeConfig) -> dict[str, str]:
    if runtime.auth_mode == "pat_bearer":
        return {"Authorization": f"Bearer {runtime.pat_token}"}
    if runtime.auth_mode == "basic":
        if not runtime.username:
            raise ValueError("CONFLUENCE_USERNAME is required for basic auth mode.")
        auth_blob = f"{runtime.username}:{runtime.pat_token}".encode("utf-8")
        encoded = base64.b64encode(auth_blob).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
    raise ValueError(f"unsupported CONFLUENCE_AUTH_MODE: {runtime.auth_mode}")


def _build_space_query_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/rest/api/space?limit=1"


def _build_current_user_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/rest/api/user/current"


def _append_query(url: str, query: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


def _decode_json_object(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _extract_user_identifier(payload: dict[str, Any]) -> str | None:
    for key in ("username", "name", "displayName", "userKey", "accountId"):
        value = payload.get(key)
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate
    return None


def _is_anonymous_user(payload: dict[str, Any], identifier: str | None) -> bool:
    user_type = payload.get("type")
    if isinstance(user_type, str) and user_type.strip().lower() == "anonymous":
        return True
    if isinstance(identifier, str) and identifier.strip().lower() == "anonymous":
        return True
    anonymous = payload.get("anonymous")
    return isinstance(anonymous, bool) and anonymous


def get_confluence_status() -> dict[str, Any]:
    load_env_files()
    base_payload: dict[str, Any] = {
        "source": "confluence",
        "connected": False,
        "checkedAt": _utc_iso_now(),
        "config": {},
        "checks": [],
        "metrics": {},
        "error": None,
    }

    try:
        runtime = ConfluenceRuntimeConfig.from_env()
    except ValueError as exc:
        base_payload["error"] = str(exc)
        base_payload["checks"].append(
            {
                "name": "configuration",
                "ok": False,
                "detail": "Required Confluence environment variables are missing.",
            }
        )
        return base_payload

    base_payload["config"] = {
        "baseUrl": runtime.base_url,
        "authMode": runtime.auth_mode,
        "timeoutSeconds": runtime.timeout_seconds,
    }

    try:
        auth_headers = _auth_headers(runtime)
    except ValueError as exc:
        detail = str(exc)
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "authentication",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload

    current_user_url = _build_current_user_url(runtime.base_url)
    ssl_context = create_ssl_context(getattr(runtime, "ca_bundle_path", None))
    try:
        request = Request(
            url=current_user_url,
            headers={"Accept": "application/json", **auth_headers},
            method="GET",
        )
        with urlopen(request, timeout=runtime.timeout_seconds, context=ssl_context) as response:  # noqa: S310
            current_user_raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = f"Confluence current user request failed with HTTP {exc.code}."
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "current_user",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload
    except URLError as exc:
        detail = f"Confluence current user request failed: {exc.reason}"
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "current_user",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload
    except Exception as exc:  # noqa: BLE001
        detail = f"Unexpected Confluence current user failure: {exc}"
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "current_user",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload

    current_user_payload = _decode_json_object(current_user_raw)
    current_user_identifier = _extract_user_identifier(current_user_payload or {})
    if current_user_payload is None:
        detail = "Confluence current user response was not valid JSON."
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "current_user",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload

    if _is_anonymous_user(current_user_payload, current_user_identifier):
        forced_auth_url = _append_query(current_user_url, "os_authType=basic")
        try:
            request = Request(
                url=forced_auth_url,
                headers={"Accept": "application/json", **auth_headers},
                method="GET",
            )
            with urlopen(request, timeout=runtime.timeout_seconds, context=ssl_context) as response:  # noqa: S310
                forced_auth_raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = (
                "Confluence authentication check failed: credentials were rejected "
                f"when forcing API authentication (HTTP {exc.code})."
            )
            base_payload["error"] = detail
            base_payload["checks"].append(
                {
                    "name": "current_user",
                    "ok": False,
                    "detail": detail,
                }
            )
            return base_payload
        except URLError as exc:
            detail = (
                "Confluence authentication check failed while forcing API authentication: "
                f"{exc.reason}"
            )
            base_payload["error"] = detail
            base_payload["checks"].append(
                {
                    "name": "current_user",
                    "ok": False,
                    "detail": detail,
                }
            )
            return base_payload
        except Exception as exc:  # noqa: BLE001
            detail = f"Unexpected Confluence forced-auth user check failure: {exc}"
            base_payload["error"] = detail
            base_payload["checks"].append(
                {
                    "name": "current_user",
                    "ok": False,
                    "detail": detail,
                }
            )
            return base_payload

        forced_auth_payload = _decode_json_object(forced_auth_raw)
        forced_auth_identifier = _extract_user_identifier(forced_auth_payload or {})
        if forced_auth_payload and not _is_anonymous_user(forced_auth_payload, forced_auth_identifier):
            current_user_identifier = forced_auth_identifier
        else:
            detail = (
                "Confluence authentication check failed: current user is anonymous "
                "and forced API authentication did not establish an authenticated identity."
            )
            base_payload["error"] = detail
            base_payload["checks"].append(
                {
                    "name": "current_user",
                    "ok": False,
                    "detail": detail,
                }
            )
            return base_payload

    if current_user_identifier is None:
        detail = "Confluence current user response did not include an identifiable user."
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "current_user",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload

    base_payload["checks"].append(
        {
            "name": "current_user",
            "ok": True,
            "detail": f"Confluence authenticated user check succeeded ({current_user_identifier}).",
        }
    )

    space_query_url = _build_space_query_url(runtime.base_url)
    try:
        request = Request(
            url=space_query_url,
            headers={"Accept": "application/json", **auth_headers},
            method="GET",
        )
        with urlopen(request, timeout=runtime.timeout_seconds, context=ssl_context) as response:  # noqa: S310
            space_query_raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = f"Confluence space query failed with HTTP {exc.code}."
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "space_query",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload
    except URLError as exc:
        detail = f"Confluence space query failed: {exc.reason}"
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "space_query",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload
    except Exception as exc:  # noqa: BLE001
        detail = f"Unexpected Confluence space query failure: {exc}"
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "space_query",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload

    payload = _decode_json_object(space_query_raw)
    if payload is None:
        detail = "Confluence space query response was not valid JSON."
        base_payload["error"] = detail
        base_payload["checks"].append(
            {
                "name": "space_query",
                "ok": False,
                "detail": detail,
            }
        )
        return base_payload

    spaces = payload.get("results")
    space_count = len(spaces) if isinstance(spaces, list) else 0
    base_payload["metrics"] = {
        "spaceCount": space_count,
        "authenticatedUser": current_user_identifier,
    }
    base_payload["checks"].append(
        {
            "name": "space_query",
            "ok": True,
            "detail": "Confluence space query succeeded.",
        }
    )
    base_payload["connected"] = True
    return base_payload
