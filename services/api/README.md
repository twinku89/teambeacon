# TeamBeacon Local API

Lightweight local API endpoints used by the desktop/web shell.

## Run
From repository root:

```bash
python3 -m services.api.server --host localhost --port 8000
```

Serve built web assets from the API process (useful in Docker runtime):

```bash
python3 -m services.api.server --host 0.0.0.0 --port 8000 --web-dir app/web
```

## Endpoints
- `GET /openapi.json`
  - Machine-readable OpenAPI schema for the local API.
- `GET /docs`
  - Interactive Swagger UI for exploring and trying endpoints.
  - Aliases: `/api/docs`, `/swagger`
- `GET /health`
- `GET /api/integrations/jira/status`
- `GET /api/integrations/jira/sync/status`
- `POST /api/integrations/jira/sync/start`
  - Optional JSON body:
    - `{"mode":"full"}`
    - `{"mode":"since_last"}`
    - `{"mode":"since_date","sinceDate":"2026-03-01"}`
- `GET /api/integrations/jira/sync/history?limit=30`
- `GET /api/integrations/confluence/status`
  - Validates Confluence REST reachability with PAT/basic auth:
    - `/rest/api/space?limit=1` query
    - Required Confluence environment variables
- `GET /api/integrations/jenkins/status`
  - Validates Jenkins job REST reachability with API-token basic auth:
    - Configured release pipeline job endpoint
    - Required Jenkins environment variables
- `GET /api/releases/insights?releaseLimit=12`
  - Returns release analytics from local sync data:
    - release cycle-time trend from release start date to release date
    - ongoing release readiness and overdue/due-soon counts
    - linked release scope, delivered story points, and risk signals
- `GET /api/releases/refresh/status`
  - Returns current Release Insights refresh state.
- `GET /api/releases/refresh/result`
  - Returns the latest Release Insights summary payload.
- `GET /api/security/audit`
  - Returns latest Jenkins security audit pipeline stages and vulnerability findings:
    - Backend dependency audit findings from Jenkins test reports
    - Trivy container/image findings from archived JSON reports
    - Frontend and UI stage status from Jenkins workflow metadata
- `POST /api/releases/refresh/start`
  - Body:
    - `sources` (required array; each source supports `confluenceUrl` and optional `prompt`)
    - `overallPrompt` (optional string)
- `GET /api/integrations/oci-genai/status`
  - OCI-specific status endpoint (legacy compatibility).
  - Validates local OCI GenAI wiring:
    - OCI SDK availability
    - `~/.oci/config` profile readability
    - Required OCI GenAI environment variables
- `GET /api/integrations/ai/status`
  - Provider-agnostic status for active intelligence provider (or explicit query override).
  - Optional query:
    - `provider=oci|ollama|openai`
- `POST /api/ai/chat`
  - Body:
    - `message` (required string)
    - `provider` (optional string; `oci`, `ollama`, `openai`; defaults from `INTELLIGENCE_PROVIDER`)
    - `modelId` (optional string; defaults from provider-specific model env)
    - `maxTokens` (optional integer)
    - `temperature` (optional number)
    - `topP` (optional number)
    - `topK` (optional integer)
    - `frequencyPenalty` (optional number)
- `GET /api/issues/search`
  - Optional query params:
    - `epicKey=CEGBUPOL-4482`
    - `workedBy=user-qa` (matches assignee/reporter/changelog contributor)
    - `assignee=<accountId>`, `reporter=<accountId>`
    - `issueType=Story`, `status=In Progress`
    - `updatedSince=2026-03-01T00:00:00+00:00`, `updatedUntil=2026-03-31T23:59:59+00:00`
    - `limit=100` (1-500)
- `GET /api/sprints/current`
  - Returns active sprint metadata from local synced data:
    - `name`, `startDate`, `endDate`, `remainingDays`
- `GET /api/sprints/current/work`
  - Returns active sprint work buckets:
    - `done`, `inProgress`, `planned`
    - Includes `totals` per bucket and aggregate `total`
- `GET /api/sprints/current/changes`
  - Returns active sprint change visibility:
    - `addedAfterStart`, `removedAfterStart`, `blockedCards`
- `GET /api/team/insights?sprintLimit=6`
  - Team sprint trend, cycle-time metrics, and work-mix summary.
  - Optional query:
    - `sprintLimit` (1-12; UI presets: `1/2/3/4/6/8/10/12`; default `6`)
    - `cycleTimeStatusMode=custom` to use explicit workflow-status selection
    - Repeated `cycleTimeStatus=<normalized-status-key>` params when `cycleTimeStatusMode=custom`
  - Trend payload includes:
    - `completedStoryPoints` per sprint
    - `avgCycleTimeDays` per sprint
    - sprint metadata (`sprintName`, `state`, `startDate`, `endDate`)
  - Status-level cycle-time payload includes:
    - `statusCycleTime.trackedIssues` (cards with measurable cycle time or cycle time to date)
    - `statusCycleTime.completedIssues` and `statusCycleTime.excludedIssues`
    - `statusCycleTime.appliedStatusKeys` and `statusCycleTime.defaultStatusKeys`
    - `statusCycleTime.availableStatuses[]` with `statusKey`, `status`, `statusCategory`, and `defaultIncluded`
    - `statusCycleTime.rows[]` with per-status `avgDays`, `medianDays`, `p85Days`, `maxDays`, `totalDays`, and `percentOfCycleTime`
  - Cards-in-window payload includes:
    - `cardsInWindow.totalCards`, `cardsInWindow.inProgressCards`, `cardsInWindow.completedCards`, `cardsInWindow.trackedCards`
    - `cardsInWindow.appliedStatusKeys` (status keys currently used for cycle-time calculations)
    - `cardsInWindow.rows[]` with per-card details:
      - `issueKey`, `sprintId`, `sprintName`, `status`, `statusKey`, `issueType`, `issueTypeKey`, `storyPoints`, `summary`, `isCompleted`
      - `cycleTimeDays` (completed cards only) and `cycleTimeToDateDays` (completed + in-progress cards)
      - `statusTimeline[]` in chronological order with `status`, `changedAt`, `days`, `percentOfTicketTime`, and `isCycleTimeStatus`
  - Cycle-time semantics:
    - Default status selection excludes obvious backlog/to-do states
    - Custom status mode sums the time spent in the selected workflow statuses from issue creation to resolution, or to "now" for active/unresolved tracked cards
    - `cycleTimeToDateDays` uses the same selected workflow statuses and runs to "now" for unresolved cards
    - Tracked cards with no time in the selected statuses are excluded from cycle-time metrics
    - Epics are excluded from cycle-time calculations
    - Sub-tasks are excluded from Team Insights calculations
- `GET /api/metadata/lookup`
  - Returns lookup/reference data:
    - `groups` (epic groups)
    - `workTypes` (work-type taxonomy)
- `POST /api/metadata/lookup/groups`
  - Body: `{"name":"Platform"}`
- `POST /api/metadata/lookup/groups/update`
  - Body: `{"id":1,"name":"Platform Core"}`
- `POST /api/metadata/lookup/groups/delete`
  - Body: `{"id":1}`
- `POST /api/metadata/lookup/work-types`
  - Body: `{"name":"Feature"}`
- `POST /api/metadata/lookup/work-types/update`
  - Body: `{"id":10,"name":"Run"}`
- `POST /api/metadata/lookup/work-types/delete`
  - Body: `{"id":10}`
- `GET /api/metadata/epics?limit=50`
  - Optional query param: `epicKey=CEGBUPOL-4482`
- `GET /api/metadata/epics/summary?limit=50`
  - Returns configured epics with completion metrics derived from local synced issue cards.
  - Optional query params:
    - `periodStart=2026-03-01`
    - `periodEnd=2026-03-31`
    - `timezone=Australia/Melbourne` (IANA timezone; defaults to `UTC`)
  - Includes:
    - `completedInPeriod` (items completed in inclusive reporting period)
    - `deltaPercentInPeriod` (`completedInPeriod / totalCards * 100`)
    - Backward-compatible aliases:
      - `completedLastWeek` -> `completedInPeriod`
      - `deltaPercent` -> `deltaPercentInPeriod`
    - `reportingPeriod`:
      - `startDate`, `endDate`, `days`, `timezone`
- `GET /api/metadata/epics/candidates?q=<key-or-name>&limit=20`
  - Returns unconfigured epic candidates from local synced `issues` (issue type `Epic`).
- `POST /api/metadata/epics`
  - Body:
    - `epicKey` (required)
    - `successCriteria` (string array)
    - `groupIds` (int array)
    - `workTypeIds` (int array)
    - `timelineEnabled` (optional boolean)
    - `timelineStartDate` (optional ISO date)
    - `targetCompletionDate` (optional ISO date)
- `POST /api/metadata/epics/delete`
  - Body:
    - `epicKey` (required)
- `GET /api/metadata/epics/completed-cards?epicKey=<key>&limit=200`
  - Returns completed cards for a single epic in a selected reporting period.
- `GET /api/metadata/epics/completed-cards/configured?limit=300`
  - Returns completed cards across all configured epics in a selected reporting period.

## Notes
- The JIRA status endpoint reads `config/.env` (or process env vars).
- The Confluence status endpoint reads `config/.env` (or process env vars).
- AI endpoints read `config/.env` (or process env vars) and route by `INTELLIGENCE_PROVIDER`:
  - `oci`: requires OCI Python SDK (`python3 -m pip install oci`)
  - `ollama`: requires local Ollama API (default local runtime `http://localhost:11434`; Docker runtime `http://host.docker.internal:11434`)
  - `openai`: requires `OPENAI_API_KEY`
- JIRA sync persists board/sprint/issue/changelog data to local SQLite (`teambeacon.db` by default).
- Parent-child lineage is stored on `issues.parent_issue_key`; epic linkage is stored on `issues.epic_key`.
- Epic metadata is persisted across:
  - `epic_groups`, `work_types` (lookup/reference data)
  - `epic_metadata` (success checklist by epic)
  - `epic_metadata_groups`, `epic_metadata_work_types` (many-to-many mapping)
- Intended for local desktop runtime and frontend proxy usage.
