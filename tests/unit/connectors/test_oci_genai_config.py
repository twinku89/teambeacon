from __future__ import annotations

import unittest

from packages.connectors.oci_genai_config import OciGenAiRuntimeConfig


class OciGenAiConfigUnitTests(unittest.TestCase):
    def test_from_env_reads_required_and_optional_values(self) -> None:
        runtime = OciGenAiRuntimeConfig.from_env(
            env={
                "OCI_GENAI_COMPARTMENT_ID": "ocid1.compartment.oc1..example",
                "OCI_GENAI_ENDPOINT": "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
                "OCI_GENAI_MODEL_ID": "cohere.command-r-08-2024",
                "OCI_GENAI_CONFIG_PROFILE": "DEFAULT",
                "OCI_GENAI_CONFIG_FILE": "~/.oci/config",
                "OCI_GENAI_MAX_TOKENS": "700",
                "OCI_GENAI_TEMPERATURE": "0.5",
                "OCI_GENAI_TOP_P": "0.8",
                "OCI_GENAI_TOP_K": "3",
                "OCI_GENAI_FREQUENCY_PENALTY": "0.2",
                "OCI_GENAI_CONNECT_TIMEOUT_SECONDS": "12",
                "OCI_GENAI_READ_TIMEOUT_SECONDS": "260",
            }
        )

        self.assertEqual(runtime.compartment_id, "ocid1.compartment.oc1..example")
        self.assertEqual(runtime.endpoint, "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com")
        self.assertEqual(runtime.model_id, "cohere.command-r-08-2024")
        self.assertEqual(runtime.config_profile, "DEFAULT")
        self.assertEqual(runtime.config_file_path, "~/.oci/config")
        self.assertEqual(runtime.max_tokens, 700)
        self.assertEqual(runtime.temperature, 0.5)
        self.assertEqual(runtime.top_p, 0.8)
        self.assertEqual(runtime.top_k, 3)
        self.assertEqual(runtime.frequency_penalty, 0.2)
        self.assertEqual(runtime.connect_timeout_seconds, 12)
        self.assertEqual(runtime.read_timeout_seconds, 260)

    def test_from_env_requires_compartment_endpoint_and_model(self) -> None:
        with self.assertRaises(ValueError):
            OciGenAiRuntimeConfig.from_env(env={})

    def test_from_env_defaults_to_shared_answer_budget(self) -> None:
        runtime = OciGenAiRuntimeConfig.from_env(
            env={
                "OCI_GENAI_COMPARTMENT_ID": "ocid1.compartment.oc1..example",
                "OCI_GENAI_ENDPOINT": "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
                "OCI_GENAI_MODEL_ID": "cohere.command-r-08-2024",
            }
        )

        self.assertEqual(runtime.max_tokens, 1000)


if __name__ == "__main__":
    unittest.main()
