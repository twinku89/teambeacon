# OCI GenAI Connectivity Smoke Test

Use this runbook to validate that TeamBeacon can reach OCI Generative AI and execute a basic chat request.

## 1. Preconditions

From repository root:

1. Confirm OCI SDK is installed for the Python interpreter used by the API:

```bash
python3 -m pip show oci
```

2. Confirm required OCI GenAI config exists in `config/.env`:

```bash
grep '^OCI_GENAI_' config/.env
```

Required keys:
- `OCI_GENAI_COMPARTMENT_ID`
- `OCI_GENAI_ENDPOINT`
- `OCI_GENAI_MODEL_ID`

3. Ensure OCI is selected as the active AI provider:

```bash
grep '^INTELLIGENCE_PROVIDER=' config/.env
```

Expected:

```text
INTELLIGENCE_PROVIDER=oci
```

4. Confirm OCI profile exists:

```bash
grep '^\[DEFAULT\]' ~/.oci/config
```

If using a different profile, check that section name instead of `DEFAULT`.

## 2. Start Local API

```bash
python3 -m services.api.server --host localhost --port 8000
```

In a separate terminal:

```bash
curl -sS http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## 3. Smoke Test: OCI Integration Status

```bash
curl -sS http://localhost:8000/api/integrations/oci-genai/status
```

Expected key checks:
- `"source":"oci_genai"`
- `"connected":true`
- `"checks"` includes:
  - `"name":"oci_sdk"` with `"ok":true`
  - `"name":"oci_profile"` with `"ok":true`

## 4. Smoke Test: OCI Chat Request

```bash
curl -sS -X POST http://localhost:8000/api/ai/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message":"Write one short update about TeamBeacon delivery health.",
    "maxTokens":200,
    "temperature":0.2
  }'
```

Expected key checks:
- `"source":"oci_genai"`
- `"modelId"` is present
- `"response":{"text":"..."}`
- `"error":null`

## 5. Common Failures

- `OCI Python SDK is not installed`
  - Fix:
    ```bash
    python3 -m pip install oci
    ```

- `missing required environment variables: OCI_GENAI_...`
  - Fix: add missing keys to `config/.env` and restart API.

- `Failed to load OCI config profile ...`
  - Fix:
    1. Verify `OCI_GENAI_CONFIG_FILE` path.
    2. Verify `OCI_GENAI_CONFIG_PROFILE` section exists in that file.
    3. Verify key file path in OCI config is valid.

- `OCI session token for profile ... expired`
  - Fix:
    ```bash
    oci session authenticate --profile DEFAULT
    ```
  - Use your configured `OCI_GENAI_CONFIG_PROFILE` value when it is not `DEFAULT`, then restart the API.

- `OCI GenAI chat request failed: ...`
  - Typical causes: invalid endpoint, unauthorized profile, blocked model access, wrong compartment OCID.

## 6. Pass/Fail Criteria

Pass when both checks succeed:
1. `GET /api/integrations/oci-genai/status` returns `connected=true`.
2. `POST /api/ai/chat` returns non-empty `response.text` and `error=null`.
