from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass
class JenkinsRuntimeConfig:
    job_url: str
    username: str
    api_token: str
    timeout_seconds: int = 30
    ca_bundle_path: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> JenkinsRuntimeConfig:
        source = dict(os.environ if env is None else env)
        missing = [
            name
            for name in ("JENKINS_RELEASE_PIPELINE_URL", "JENKINS_API_AUTH_USER", "JENKINS_API_AUTH_TOKEN")
            if not source.get(name)
        ]
        if missing:
            missing_csv = ", ".join(missing)
            raise ValueError(f"missing required environment variables: {missing_csv}")

        return cls(
            job_url=source["JENKINS_RELEASE_PIPELINE_URL"].strip(),
            username=source["JENKINS_API_AUTH_USER"].strip(),
            api_token=source["JENKINS_API_AUTH_TOKEN"].strip(),
            timeout_seconds=int(source.get("JENKINS_TIMEOUT_SECONDS", "30")),
            ca_bundle_path=source.get("JENKINS_CA_BUNDLE") or source.get("ATLASSIAN_CA_BUNDLE"),
        )
