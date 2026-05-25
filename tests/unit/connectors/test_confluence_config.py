from __future__ import annotations

import unittest

from packages.connectors.confluence_config import ConfluenceRuntimeConfig


class ConfluenceConfigUnitTests(unittest.TestCase):
    def test_from_env_reads_required_and_optional_values(self) -> None:
        runtime = ConfluenceRuntimeConfig.from_env(
            env={
                "CONFLUENCE_BASE_URL": "https://gbuconfluence.oraclecorp.com",
                "CONFLUENCE_PAT": "token",
                "CONFLUENCE_AUTH_MODE": "pat_bearer",
                "CONFLUENCE_TIMEOUT_SECONDS": "45",
                "CONFLUENCE_CA_BUNDLE": "/tmp/corporate-ca.pem",
            }
        )

        self.assertEqual(runtime.base_url, "https://gbuconfluence.oraclecorp.com")
        self.assertEqual(runtime.pat_token, "token")
        self.assertEqual(runtime.auth_mode, "pat_bearer")
        self.assertEqual(runtime.timeout_seconds, 45)
        self.assertEqual(runtime.ca_bundle_path, "/tmp/corporate-ca.pem")

    def test_from_env_requires_base_url_and_pat(self) -> None:
        with self.assertRaises(ValueError):
            ConfluenceRuntimeConfig.from_env(env={})


if __name__ == "__main__":
    unittest.main()
