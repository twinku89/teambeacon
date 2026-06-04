# Configuration

## Files
- `.env.example`: template for local/runtime configuration.
- `.env`: local secrets and runtime settings (ignored by git).

## Required JIRA Variables
- `JIRA_BASE_URL`
- `JIRA_PAT`
- `JIRA_PROJECT_KEY` (recommended for scoped queries)
- `JIRA_BOARD_ID` (required for board/sprint integration tests)
- `JIRA_STORY_POINTS_FIELD`

## Optional Variables
- `JIRA_EPIC_LINK_FIELD` (default: `customfield_10014`; set to your environment value, e.g. `customfield_10902`)
- `JIRA_SPRINT_FIELDS` (comma-separated sprint field priority; default: `sprint,customfield_10901,customfield_10020`)
- `JIRA_AUTH_MODE` (`pat_bearer` default, `basic` also supported)
- `JIRA_CA_BUNDLE` or `ATLASSIAN_CA_BUNDLE` (optional PEM file for internal/corporate TLS CAs)
- `JIRA_USERNAME` (only needed for `basic` auth mode)
- `JIRA_TIMEOUT_SECONDS` (default: `30`)
- `RUN_LIVE_JIRA_TESTS` (`1` enables live integration tests)

## Confluence Variables
- `CONFLUENCE_BASE_URL` (required)
- `CONFLUENCE_PAT` (required)
- `CONFLUENCE_AUTH_MODE` (`pat_bearer` default, `basic` also supported)
- `CONFLUENCE_CA_BUNDLE` or `ATLASSIAN_CA_BUNDLE` (optional PEM file for internal/corporate TLS CAs)
- `CONFLUENCE_USERNAME` (only needed for `basic` auth mode)
- `CONFLUENCE_TIMEOUT_SECONDS` (default: `30`)

## Jenkins Variables
- `JENKINS_RELEASE_PIPELINE_URL` (required; Jenkins job URL checked by Settings)
- `JENKINS_SECURITY_AUDIT_PIPELINE_URL` (optional; Security Insights pipeline URL)
- `JENKINS_API_AUTH_USER` (required)
- `JENKINS_API_AUTH_TOKEN` (required)
- `JENKINS_CA_BUNDLE` or `ATLASSIAN_CA_BUNDLE` (optional PEM file for internal/corporate TLS CAs)
- `JENKINS_TIMEOUT_SECONDS` (default: `30`)

## Intelligence Provider
- `INTELLIGENCE_PROVIDER` (default: `ollama`; supported: `oci`, `ollama`, `openai`)
- `AI_PROVIDER` (optional alias for `INTELLIGENCE_PROVIDER`)
- Settings UI label: `AI Model Connection` (shows active provider/model and health status)

## OCI GenAI Variables
- `OCI_GENAI_COMPARTMENT_ID` (required)
- `OCI_GENAI_ENDPOINT` (required, e.g. `https://inference.generativeai.us-chicago-1.oci.oraclecloud.com`)
- `OCI_GENAI_MODEL_ID` (required, e.g. `cohere.command-r-08-2024`)
- `OCI_GENAI_CONFIG_PROFILE` (default: `DEFAULT`)
- `OCI_GENAI_CONFIG_FILE` (default: `~/.oci/config`)
- `OCI_GENAI_MAX_TOKENS` (default: `1000`)
- `OCI_GENAI_TEMPERATURE` (default: `1`)
- `OCI_GENAI_TOP_P` (default: `0.75`)
- `OCI_GENAI_TOP_K` (default: `0`)
- `OCI_GENAI_FREQUENCY_PENALTY` (default: `0`)
- `OCI_GENAI_CONNECT_TIMEOUT_SECONDS` (default: `10`)
- `OCI_GENAI_READ_TIMEOUT_SECONDS` (default: `240`)

## Ollama Variables
- `OLLAMA_MODEL` or `OLLAMA_MODEL_ID` (required when `INTELLIGENCE_PROVIDER=ollama`; default: `llama3.1:8b`)
- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `OLLAMA_NUM_CTX` (default: `12288`; increase for larger prompts)
- `OLLAMA_MAX_TOKENS` (default: `1200`)
- `OLLAMA_TEMPERATURE` (default: `1`)
- `OLLAMA_TOP_P` (default: `0.75`)
- `OLLAMA_TOP_K` (default: `0`)
- `OLLAMA_REPEAT_PENALTY` (default: `1`)
- `OLLAMA_CONNECT_TIMEOUT_SECONDS` (default: `10`)
- `OLLAMA_READ_TIMEOUT_SECONDS` (default: `240`)

## OpenAI Variables
- `OPENAI_API_KEY` (required when `INTELLIGENCE_PROVIDER=openai`)
- `OPENAI_MODEL` or `OPENAI_MODEL_ID` (default: `gpt-4o-mini`)
- `OPENAI_BASE_URL` (default: `https://api.openai.com/v1`)
- `OPENAI_MAX_TOKENS` (default: `600`)
- `OPENAI_TEMPERATURE` (default: `1`)
- `OPENAI_TOP_P` (default: `0.75`)
- `OPENAI_FREQUENCY_PENALTY` (default: `0`)
- `OPENAI_CONNECT_TIMEOUT_SECONDS` (default: `10`)
- `OPENAI_READ_TIMEOUT_SECONDS` (default: `240`)

## Docker Runtime Notes (Ollama and OCI)
### Ollama in Docker
- Keep `OLLAMA_BASE_URL` for local (non-Docker) development (`http://localhost:11434`).
- Use `OLLAMA_BASE_URL_DOCKER` for container runtime (set in `config/.env`).
- Docker default is `http://host.docker.internal:11434`.
- Rancher Desktop typically uses `http://host.rancher-desktop.internal:11434`.

### OCI in Docker
- Compose mounts `${HOME}/.oci` into the container at `/home/teambeacon/.oci` (read-only).
- Compose also mounts `${HOME}/.oci` at the same absolute host-style path inside the container (for configs that reference `/Users/<name>/.oci/...` directly).
- Default `OCI_GENAI_CONFIG_FILE` is `/home/teambeacon/.oci/config` in container mode.
- Ensure your `config/.env` includes `INTELLIGENCE_PROVIDER=oci` and required OCI variables.
- If your OCI config lives elsewhere, override with `OCI_GENAI_CONFIG_FILE=/path/in/container/config`.
