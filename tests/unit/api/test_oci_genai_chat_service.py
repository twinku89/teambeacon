from __future__ import annotations

import base64
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from packages.connectors.oci_genai_config import OciGenAiRuntimeConfig
from services.api.integrations.oci_genai_chat import (
    _decode_jwt_payload,
    _read_current_security_token,
    chat_with_oci_genai,
    get_oci_genai_status,
)


class _FakeCohereChatRequest:
    def __init__(self) -> None:
        self.message: str | None = None
        self.max_tokens: int | None = None
        self.temperature: float | None = None
        self.frequency_penalty: float | None = None
        self.top_p: float | None = None
        self.top_k: int | None = None


class _FakeOnDemandServingMode:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id


class _FakeChatDetails:
    def __init__(self) -> None:
        self.serving_mode: _FakeOnDemandServingMode | None = None
        self.chat_request: _FakeCohereChatRequest | None = None
        self.compartment_id: str | None = None


class _FakeResponseChatPayload:
    text = "Use TeamBeacon weekly summaries for executive updates."


class _FakeResponseDataPayload:
    chat_response = _FakeResponseChatPayload()


class _FakeResponsePayload:
    data = _FakeResponseDataPayload()


class _FakeInferenceClient:
    last_instance: _FakeInferenceClient | None = None

    def __init__(self, config, service_endpoint, retry_strategy, timeout, signer=None):  # noqa: ANN001
        _ = retry_strategy
        self.config = config
        self.service_endpoint = service_endpoint
        self.timeout = timeout
        self.signer = signer
        self.last_chat_detail: _FakeChatDetails | None = None
        _FakeInferenceClient.last_instance = self

    def chat(self, chat_detail):  # noqa: ANN001
        self.last_chat_detail = chat_detail
        return _FakeResponsePayload()


class _FakeRetry:
    @staticmethod
    def NoneRetryStrategy():  # noqa: N802
        return object()


class _FakeModels:
    ChatDetails = _FakeChatDetails
    CohereChatRequest = _FakeCohereChatRequest
    OnDemandServingMode = _FakeOnDemandServingMode


class _FakeGenerativeAiInference:
    GenerativeAiInferenceClient = _FakeInferenceClient
    models = _FakeModels


class _FakeSigner:
    @staticmethod
    def load_private_key_from_file(filename, pass_phrase=None):  # noqa: ANN001
        return {
            "filename": filename,
            "pass_phrase": pass_phrase,
        }


class _FakeSecurityTokenSigner:
    def __init__(self, token, private_key):  # noqa: ANN001
        self.token = token
        self.private_key = private_key


class _FakeAuthSigners:
    SecurityTokenSigner = _FakeSecurityTokenSigner


class _FakeAuth:
    signers = _FakeAuthSigners


class _FakeOciModule:
    retry = _FakeRetry
    generative_ai_inference = _FakeGenerativeAiInference
    signer = _FakeSigner
    auth = _FakeAuth


def _jwt_with_exp(expires_at: datetime) -> str:
    payload = {
        "exp": int(expires_at.timestamp()),
    }
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"header.{encoded_payload}.signature"


class OciGenAiChatServiceUnitTests(unittest.TestCase):
    def _runtime(self) -> OciGenAiRuntimeConfig:
        return OciGenAiRuntimeConfig(
            compartment_id="ocid1.compartment.oc1..example",
            endpoint="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
            model_id="cohere.command-r-08-2024",
            config_profile="DEFAULT",
            config_file_path="~/.oci/config",
            max_tokens=1000,
            temperature=1.0,
            top_p=0.75,
            top_k=0,
            frequency_penalty=0.0,
            connect_timeout_seconds=10,
            read_timeout_seconds=240,
        )

    def test_status_returns_configuration_error_when_env_missing(self) -> None:
        with patch("services.api.integrations.oci_genai_chat.load_env_files"), patch(
            "services.api.integrations.oci_genai_chat.OciGenAiRuntimeConfig.from_env",
            side_effect=ValueError(
                "missing required environment variables: OCI_GENAI_COMPARTMENT_ID, OCI_GENAI_ENDPOINT, OCI_GENAI_MODEL_ID"
            ),
        ):
            payload = get_oci_genai_status()

        self.assertFalse(payload["connected"])
        self.assertEqual(payload["source"], "oci_genai")
        self.assertIn("missing required environment variables", payload["error"])
        self.assertTrue(payload["checks"])

    def test_status_returns_connected_when_profile_is_loadable(self) -> None:
        with patch("services.api.integrations.oci_genai_chat.load_env_files"), patch(
            "services.api.integrations.oci_genai_chat.OciGenAiRuntimeConfig.from_env",
            return_value=self._runtime(),
        ), patch(
            "services.api.integrations.oci_genai_chat._load_oci_module",
            return_value=_FakeOciModule(),
        ), patch(
            "services.api.integrations.oci_genai_chat._load_oci_profile",
            return_value={"tenancy": "ocid1.tenancy.oc1..example"},
        ):
            payload = get_oci_genai_status()

        self.assertTrue(payload["connected"])
        self.assertEqual(payload["config"]["modelId"], "cohere.command-r-08-2024")
        self.assertEqual(payload["checks"][0]["name"], "oci_sdk")
        self.assertEqual(payload["checks"][1]["name"], "oci_profile")
        self.assertIsNone(payload["error"])

    def test_chat_calls_oci_and_returns_text_response(self) -> None:
        runtime = self._runtime()
        with patch("services.api.integrations.oci_genai_chat.load_env_files"), patch(
            "services.api.integrations.oci_genai_chat.OciGenAiRuntimeConfig.from_env",
            return_value=runtime,
        ), patch(
            "services.api.integrations.oci_genai_chat._load_oci_module",
            return_value=_FakeOciModule(),
        ), patch(
            "services.api.integrations.oci_genai_chat._load_oci_profile",
            return_value={"region": "us-chicago-1"},
        ):
            payload = chat_with_oci_genai(
                message="Summarize delivery risks for this sprint.",
                max_tokens=256,
                temperature=0.4,
                top_p=0.9,
                top_k=10,
                frequency_penalty=0.1,
            )

        self.assertEqual(payload["source"], "oci_genai")
        self.assertEqual(payload["modelId"], "cohere.command-r-08-2024")
        self.assertIn("TeamBeacon", payload["response"]["text"])
        self.assertEqual(payload["request"]["maxTokens"], 256)
        self.assertEqual(payload["request"]["temperature"], 0.4)
        self.assertEqual(payload["request"]["topP"], 0.9)
        self.assertEqual(payload["request"]["topK"], 10)
        self.assertEqual(payload["request"]["frequencyPenalty"], 0.1)

        client = _FakeInferenceClient.last_instance
        self.assertIsNotNone(client)
        if client is None:
            self.fail("Expected OCI inference client instance to be created.")
        self.assertEqual(client.service_endpoint, runtime.endpoint)
        self.assertEqual(client.timeout, (runtime.connect_timeout_seconds, runtime.read_timeout_seconds))
        self.assertIsNone(client.signer)
        self.assertIsNotNone(client.last_chat_detail)
        if client.last_chat_detail is None:
            self.fail("Expected chat request details to be captured.")
        self.assertEqual(client.last_chat_detail.compartment_id, runtime.compartment_id)
        self.assertIsNotNone(client.last_chat_detail.serving_mode)
        if client.last_chat_detail.serving_mode is None:
            self.fail("Expected on-demand serving mode to be set.")
        self.assertEqual(client.last_chat_detail.serving_mode.model_id, runtime.model_id)
        self.assertIsNotNone(client.last_chat_detail.chat_request)
        if client.last_chat_detail.chat_request is None:
            self.fail("Expected Cohere chat request payload to be set.")
        self.assertEqual(client.last_chat_detail.chat_request.message, "Summarize delivery risks for this sprint.")

    def test_chat_requires_non_empty_message(self) -> None:
        with self.assertRaises(ValueError):
            chat_with_oci_genai(message="   ")

    def test_chat_uses_security_token_signer_for_session_profiles(self) -> None:
        runtime = self._runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token"
            key_path = Path(tmpdir) / "oci_api_key.pem"
            token = _jwt_with_exp(datetime.now(timezone.utc) + timedelta(hours=1))
            token_path.write_text(token, encoding="utf-8")
            key_path.write_text("private-key", encoding="utf-8")

            with patch("services.api.integrations.oci_genai_chat.load_env_files"), patch(
                "services.api.integrations.oci_genai_chat.OciGenAiRuntimeConfig.from_env",
                return_value=runtime,
            ), patch(
                "services.api.integrations.oci_genai_chat._load_oci_module",
                return_value=_FakeOciModule(),
            ), patch(
                "services.api.integrations.oci_genai_chat._load_oci_profile",
                return_value={
                    "region": "us-chicago-1",
                    "security_token_file": str(token_path),
                    "key_file": str(key_path),
                },
            ):
                chat_with_oci_genai(message="Summarize delivery risks for this sprint.")

            client = _FakeInferenceClient.last_instance
            self.assertIsNotNone(client)
            if client is None:
                self.fail("Expected OCI inference client instance to be created.")
            self.assertIsInstance(client.signer, _FakeSecurityTokenSigner)
            self.assertEqual(client.signer.token, token)
            self.assertEqual(client.signer.private_key["filename"], str(key_path))

    def test_security_token_expiry_is_reported_before_oci_request(self) -> None:
        runtime = self._runtime()
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token"
            token_path.write_text(
                _jwt_with_exp(datetime.now(timezone.utc) - timedelta(minutes=1)),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                _read_current_security_token(
                    {
                        "security_token_file": str(token_path),
                    },
                    runtime,
                )

        self.assertIn("OCI session token for profile DEFAULT expired", str(context.exception))
        self.assertIn("oci session authenticate --profile DEFAULT", str(context.exception))

    def test_decode_jwt_payload_handles_invalid_tokens(self) -> None:
        self.assertIsNone(_decode_jwt_payload("not-a-token"))


if __name__ == "__main__":
    unittest.main()
