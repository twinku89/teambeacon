from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass
class OciGenAiRuntimeConfig:
    compartment_id: str
    endpoint: str
    model_id: str
    config_profile: str = "DEFAULT"
    config_file_path: str = "~/.oci/config"
    max_tokens: int = 1000
    temperature: float = 1.0
    top_p: float = 0.75
    top_k: int = 0
    frequency_penalty: float = 0.0
    connect_timeout_seconds: int = 10
    read_timeout_seconds: int = 240

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> OciGenAiRuntimeConfig:
        source = dict(os.environ if env is None else env)
        missing = [
            name
            for name in ("OCI_GENAI_COMPARTMENT_ID", "OCI_GENAI_ENDPOINT", "OCI_GENAI_MODEL_ID")
            if not source.get(name)
        ]
        if missing:
            missing_csv = ", ".join(missing)
            raise ValueError(f"missing required environment variables: {missing_csv}")

        return cls(
            compartment_id=source["OCI_GENAI_COMPARTMENT_ID"],
            endpoint=source["OCI_GENAI_ENDPOINT"],
            model_id=source["OCI_GENAI_MODEL_ID"],
            config_profile=source.get("OCI_GENAI_CONFIG_PROFILE", "DEFAULT"),
            config_file_path=source.get("OCI_GENAI_CONFIG_FILE", "~/.oci/config"),
            max_tokens=int(source.get("OCI_GENAI_MAX_TOKENS", "1000")),
            temperature=float(source.get("OCI_GENAI_TEMPERATURE", "1")),
            top_p=float(source.get("OCI_GENAI_TOP_P", "0.75")),
            top_k=int(source.get("OCI_GENAI_TOP_K", "0")),
            frequency_penalty=float(source.get("OCI_GENAI_FREQUENCY_PENALTY", "0")),
            connect_timeout_seconds=int(source.get("OCI_GENAI_CONNECT_TIMEOUT_SECONDS", "10")),
            read_timeout_seconds=int(source.get("OCI_GENAI_READ_TIMEOUT_SECONDS", "240")),
        )

    @property
    def expanded_config_file_path(self) -> str:
        return os.path.expanduser(self.config_file_path)
