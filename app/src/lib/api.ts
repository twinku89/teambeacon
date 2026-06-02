export type IntegrationCheck = {
  name: string;
  ok: boolean;
  detail: string;
};

export type JiraIntegrationStatus = {
  source: "jira";
  connected: boolean;
  checkedAt: string;
  config: {
    baseUrl?: string;
    projectKey?: string | null;
    boardId?: number | null;
    storyPointsField?: string;
    epicLinkField?: string;
    sprintFields?: string[];
    authMode?: string;
  };
  checks: IntegrationCheck[];
  metrics?: {
    boardCount?: number;
    projectSampleIssueCount?: number;
  };
  sampleIssueKey?: string | null;
  sampleIssueUrl?: string | null;
  configuredProjectUrl?: string | null;
  configuredBoard?: {
    id: number;
    name: string;
    url?: string | null;
    visible: boolean;
  } | null;
  error?: string | null;
};

export type OciGenAiIntegrationStatus = {
  source: "oci_genai";
  connected: boolean;
  checkedAt: string;
  config: {
    compartmentId?: string;
    endpoint?: string;
    modelId?: string;
    configProfile?: string;
    configFile?: string;
    timeoutSeconds?: {
      connect?: number;
      read?: number;
    };
  };
  checks: IntegrationCheck[];
  error?: string | null;
};

export type AiProvider = "oci" | "ollama" | "openai";

export type AiIntegrationStatus = {
  source: "oci_genai" | "ollama" | "openai";
  provider?: AiProvider;
  configuredProvider?: AiProvider;
  supportedProviders?: AiProvider[];
  connected: boolean;
  checkedAt: string;
  config: {
    compartmentId?: string;
    endpoint?: string;
    baseUrl?: string;
    modelId?: string;
    configProfile?: string;
    configFile?: string;
    timeoutSeconds?: {
      connect?: number;
      read?: number;
    };
  };
  checks: IntegrationCheck[];
  error?: string | null;
};

export type ConfluenceIntegrationStatus = {
  source: "confluence";
  connected: boolean;
  checkedAt: string;
  config: {
    baseUrl?: string;
    authMode?: string;
    timeoutSeconds?: number;
  };
  checks: IntegrationCheck[];
  metrics?: {
    spaceCount?: number;
  };
  error?: string | null;
};

export type JenkinsIntegrationStatus = {
  source: "jenkins";
  connected: boolean;
  checkedAt: string;
  config: {
    jobUrl?: string;
    resolvedJobUrl?: string;
    authUser?: string;
    timeoutSeconds?: number;
  };
  checks: IntegrationCheck[];
  metrics?: {
    jobName?: string | null;
    buildable?: boolean | null;
    lastBuildNumber?: number | null;
    lastBuildResult?: string | null;
    lastSuccessfulBuildNumber?: number | null;
  };
  error?: string | null;
};

export type OciGenAiChatResponse = {
  source: "oci_genai" | "ollama" | "openai";
  provider?: AiProvider;
  configuredProvider?: AiProvider;
  modelId: string;
  response: {
    text: string;
  };
  request?: {
    message?: string;
    maxTokens?: number;
    temperature?: number;
    topP?: number;
    topK?: number;
    frequencyPenalty?: number;
  };
  error?: string | null;
};

export type JiraSyncState = "idle" | "running" | "completed" | "failed";
export type JiraSyncMode = "full" | "since_last" | "since_date";

export type SecuritySeverityCounts = {
  critical: number;
  high: number;
  medium: number;
  low: number;
  unknown: number;
};

export type SecurityAuditLayer = {
  name: string;
  stageStatus: string;
  durationMillis?: number | null;
  findingCount: number;
  failedFindingCount: number;
  skippedFindingCount: number;
  severityCounts: SecuritySeverityCounts;
};

export type SecurityAuditFinding = {
  layer: string;
  id?: string | null;
  severity: string;
  packageName?: string | null;
  installedVersion?: string | null;
  fixedVersion?: string | null;
  target?: string | null;
  title?: string | null;
  status?: string | null;
  score?: number | null;
  jiraCard?: {
    issueKey: string;
    summary: string;
    status: string;
    statusCategory?: string | null;
    issueUrl?: string | null;
    assignee?: string | null;
    latestCommentAt?: string | null;
  } | null;
  jiraCreateUrl?: string | null;
};

export type SecurityAuditTrendPoint = {
  buildNumber?: number | string | null;
  buildUrl?: string | null;
  status?: string | null;
  startedAt?: string | null;
  totalFindings: number;
  severityCounts: SecuritySeverityCounts;
};

export type SecurityAuditResponse = {
  source: "jenkins_security_audit";
  generatedAt: string;
  cached?: boolean;
  pipeline: {
    jobName?: string | null;
    jobUrl?: string | null;
    buildNumber?: number | string | null;
    buildUrl?: string | null;
    status?: string | null;
    startedAt?: string | null;
    durationMillis?: number | null;
    trivyArtifactName?: string | null;
  };
  summary: {
    totalFindings?: number;
    failedFindings?: number;
    skippedFindings?: number;
    severityCounts?: SecuritySeverityCounts;
    failedLayerCount?: number;
    passedLayerCount?: number;
    failedLayers?: string[];
    passedLayers?: string[];
  };
  layers: SecurityAuditLayer[];
  findings: SecurityAuditFinding[];
  trend?: SecurityAuditTrendPoint[];
  error?: string | null;
};

export type NewsArticle = {
  id: string;
  categoryId: string;
  title: string;
  source: string;
  url: string;
  publishedAt?: string | null;
  summary?: string | null;
};

export type NewsCategory = {
  id: string;
  label: string;
  description: string;
  articles: NewsArticle[];
  errors?: string[];
};

export type DogTrainingTip = {
  categoryId: "dogTraining";
  label: string;
  description: string;
  id?: string;
  ageMonths?: number;
  ageDays?: number;
  ageLabel?: string;
  stageLabel?: string;
  skillName?: string;
  skillArea?: string;
  title: string;
  focus: string;
  steps: string[];
  note?: string | null;
};

export type BookOfTheDay = {
  label: string;
  title: string;
  author: string;
  summary: string;
  whyRead: string;
  readingTimeMinutes?: number;
  detailedSummary?: string;
  keyIdeas?: string[];
  tryToday?: string;
};

export type NewsDashboardResponse = {
  source: "rss";
  generatedAt: string;
  timezone: string;
  cached?: boolean;
  categories: NewsCategory[];
  bookOfTheDay?: BookOfTheDay;
  trainingTip?: DogTrainingTip;
  trainingTips?: DogTrainingTip[];
  error?: string | null;
};

export type JiraSyncStatus = {
  source: "jira";
  state: JiraSyncState;
  phase: string;
  syncMode?: JiraSyncMode;
  requestedSyncMode?: JiraSyncMode;
  requestedSince?: string | null;
  boardsSynced?: number;
  sprintsSynced?: number;
  downloadedIssues: number;
  totalIssues?: number | null;
  percent?: number | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  lastSyncedAt?: string | null;
  error?: string | null;
  message?: string | null;
  started?: boolean;
};

export type JiraSyncHistoryEntry = {
  id: number;
  scopeKey: string;
  boardId?: number | null;
  boardName?: string | null;
  syncMode?: JiraSyncMode;
  requestedSince?: string | null;
  boardsSynced: number;
  sprintsSynced: number;
  issuesSynced: number;
  totalIssues?: number | null;
  status: "running" | "completed" | "failed";
  error?: string | null;
  startedAt: string;
  finishedAt?: string | null;
};

export type EpicLookupItem = {
  id: number;
  name: string;
};

export type EpicLookupConfig = {
  groups: EpicLookupItem[];
  workTypes: EpicLookupItem[];
};

export type EpicCandidate = {
  epicKey: string;
  epicName: string;
};

export type EpicMetadataEntry = {
  epicKey: string;
  epicTitle?: string | null;
  successCriteria: string[];
  timelineEnabled?: boolean;
  timelineStartDate?: string | null;
  targetCompletionDate?: string | null;
  groupIds: number[];
  groups: EpicLookupItem[];
  workTypeIds: number[];
  workTypes: EpicLookupItem[];
  updatedAt?: string | null;
};

export type InitiativeEpicSummary = {
  epicKey: string;
  epicName: string;
  completedCards: number;
  totalCards: number;
  completionPercent: number;
  completedLastWeek?: number;
  deltaPercent?: number;
  completedInPeriod?: number;
  deltaPercentInPeriod?: number;
  groups: EpicLookupItem[];
  workTypes: EpicLookupItem[];
  successCriteria: string[];
  timelineEnabled?: boolean;
  timelineStartDate?: string | null;
  targetCompletionDate?: string | null;
  ragScore?: string | null;
  insightComment?: string | null;
  updatedAt?: string | null;
};

export type EpicSummaryReportingPeriod = {
  startDate: string;
  endDate: string;
  days: number;
  timezone: string;
};

export type ConfiguredEpicSummaryResponse = {
  epics: InitiativeEpicSummary[];
  reportingPeriod?: EpicSummaryReportingPeriod;
  error?: string | null;
};

export type EpicCompletedCard = {
  issueKey: string;
  summary: string;
  status?: string | null;
  statusCategory?: string | null;
  storyPoints?: number | null;
  assigneeAccountId?: string | null;
  completedAt?: string | null;
  epicKey?: string | null;
  epicName?: string | null;
};

export type EpicCompletedCardsResponse = {
  source: "local";
  epicKey: string;
  epicName?: string | null;
  count: number;
  limit: number;
  truncated: boolean;
  completedCards: EpicCompletedCard[];
  reportingPeriod?: EpicSummaryReportingPeriod;
  error?: string | null;
};

export type ConfiguredEpicsCompletedCardsResponse = {
  source: "local";
  scope: "configured";
  count: number;
  limit: number;
  truncated: boolean;
  completedCards: EpicCompletedCard[];
  perEpicCounts: Record<string, number>;
  reportingPeriod?: EpicSummaryReportingPeriod;
  error?: string | null;
};

export type CurrentSprint = {
  id: number;
  boardId?: number | null;
  name: string;
  state: string;
  startDate?: string | null;
  endDate?: string | null;
  goal?: string | null;
  sprintUrl?: string | null;
  daysOver?: number | null;
  remainingDays?: number | null;
};

export type CurrentSprintResponse = {
  source: "local";
  sprint: CurrentSprint | null;
  error?: string | null;
};

export type CurrentSprintWorkIssue = {
  issueKey: string;
  summary: string;
  status: string;
  statusCategory?: string | null;
  storyPoints?: number | null;
  epicKey?: string | null;
  epicName?: string | null;
  groupName?: string | null;
  workTypeName?: string | null;
  assigneeAccountId?: string | null;
  epicUrl?: string | null;
  issueUrl?: string | null;
};

export type CurrentSprintWorkResponse = {
  source: "local";
  sprint: CurrentSprint | null;
  work: {
    done: CurrentSprintWorkIssue[];
    inProgress: CurrentSprintWorkIssue[];
    planned: CurrentSprintWorkIssue[];
    totals: {
      done: number;
      inProgress: number;
      planned: number;
      total: number;
      storyPoints: {
        done: number;
        inProgress: number;
        planned: number;
        total: number;
      };
    };
  };
  error?: string | null;
};

export type CurrentSprintChangeIssue = {
  issueKey: string;
  summary: string;
  issueUrl?: string | null;
  epicName?: string | null;
  epicUrl?: string | null;
  storyPoints?: number | null;
  status?: string | null;
  statusCategory?: string | null;
};

export type CurrentSprintChangesResponse = {
  source: "local";
  sprint: CurrentSprint | null;
  changes: {
    addedAfterStart: {
      count: number;
      storyPointsTotal: number;
      issueKeys: string[];
      issueCards: CurrentSprintChangeIssue[];
    };
    removedAfterStart: {
      count: number;
      storyPointsTotal: number;
      issueKeys: string[];
      issueCards: CurrentSprintChangeIssue[];
    };
    blockedCards: {
      count: number;
      storyPointsTotal: number;
      issueKeys: string[];
      issueCards: CurrentSprintChangeIssue[];
    };
  };
  error?: string | null;
};

export type TeamInsightTrendPoint = {
  sprintId: number;
  sprintName: string;
  state?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  committedStoryPoints: number;
  completedStoryPoints: number;
  avgCycleTimeDays?: number | null;
  completionRatioPercent: number;
  carryoverPercent: number;
};

export type TeamInsightWorkMixSlice = {
  label: string;
  count: number;
  percent: number;
};

export type TeamInsightStatusCycleRow = {
  status: string;
  issueCount: number;
  avgDays: number;
  medianDays: number;
  p85Days: number;
  maxDays: number;
  totalDays: number;
  percentOfCycleTime: number;
};

export type TeamInsightAvailableStatus = {
  statusKey: string;
  status: string;
  statusCategory: string;
  defaultIncluded: boolean;
};

export type TeamInsightCardStatusTimelineEntry = {
  statusKey: string;
  status: string;
  changedAt: string;
  days: number;
  percentOfTicketTime: number;
  isCycleTimeStatus: boolean;
};

export type TeamInsightCardWindowRow = {
  issueKey: string;
  issueUrl?: string | null;
  epicKey?: string | null;
  epicName?: string | null;
  sprintId: number;
  sprintName: string;
  status: string;
  statusKey: string;
  issueType: string;
  issueTypeKey: string;
  storyPoints?: number | null;
  cycleTimeDays?: number | null;
  cycleTimeToDateDays?: number | null;
  summary: string;
  isCompleted: boolean;
  statusTimeline: TeamInsightCardStatusTimelineEntry[];
};

export type TeamInsightsResponse = {
  source: "local";
  generatedAt?: string | null;
  windowSize?: number;
  metrics: {
    avgCommittedStoryPoints: number;
    avgCompletedStoryPoints: number;
    completionRatioPercent: number;
    carryoverPercent: number;
    avgCycleTimeDays?: number | null;
    cycleTimeStdDevDays?: number | null;
    medianCycleTimeDays?: number | null;
  };
  trend: TeamInsightTrendPoint[];
  statusCycleTime: {
    trackedIssues: number;
    completedIssues?: number;
    excludedIssues?: number;
    totalDays: number;
    appliedStatusKeys?: string[];
    defaultStatusKeys?: string[];
    availableStatuses?: TeamInsightAvailableStatus[];
    rows: TeamInsightStatusCycleRow[];
  };
  cardsInWindow?: {
    totalCards: number;
    inProgressCards: number;
    completedCards: number;
    trackedCards?: number;
    appliedStatusKeys?: string[];
    rows: TeamInsightCardWindowRow[];
  };
  workMix: {
    sprintId?: number | null;
    sprintName?: string | null;
    totalIssues: number;
    slices: TeamInsightWorkMixSlice[];
  };
  summary: string;
  error?: string | null;
};

export type ReleaseRefreshState = "idle" | "running" | "completed" | "failed";
export type ReleaseRefreshSourceState = "queued" | "fetching" | "processing" | "completed" | "failed";

export type ReleaseRefreshSourceInput = {
  confluenceUrl: string;
  prompt?: string;
};

export type ReleaseRefreshSourceStatus = {
  id: number;
  confluenceUrl: string;
  prompt?: string;
  state: ReleaseRefreshSourceState;
  percent?: number | null;
  message?: string | null;
  error?: string | null;
  title?: string | null;
  resolvedUrl?: string | null;
  summary?: string | null;
};

export type ReleaseRefreshStatus = {
  source: "releases";
  state: ReleaseRefreshState;
  phase: string;
  percent?: number | null;
  message?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  generatedAt?: string | null;
  error?: string | null;
  sources: ReleaseRefreshSourceStatus[];
  started?: boolean;
};

export type ReleaseRefreshResult = {
  source: "releases";
  state: ReleaseRefreshState;
  generatedAt?: string | null;
  html?: string | null;
  text?: string | null;
  sources: ReleaseRefreshSourceStatus[];
  error?: string | null;
};

export type ReleaseRiskLevel = "green" | "amber" | "red" | "neutral";

export type ReleaseIssueTypeSlice = {
  label: string;
  count: number;
  percent: number;
};

export type ReleaseOpenIssue = {
  issueKey: string;
  issueUrl?: string | null;
  summary: string;
  status: string;
  priority?: string | null;
  storyPoints?: number | null;
};

export type ReleaseInsightRow = {
  versionId: string;
  projectKey?: string | null;
  name: string;
  description?: string | null;
  archived: boolean;
  released: boolean;
  startDate?: string | null;
  releaseDate?: string | null;
  cycleTimeDays?: number | null;
  ageDays?: number | null;
  dueInDays?: number | null;
  overdueDays?: number | null;
  issueCount: number;
  doneIssueCount: number;
  inProgressIssueCount: number;
  todoIssueCount: number;
  storyPoints: number;
  doneStoryPoints: number;
  readinessPercent: number;
  criticalOpenIssueCount: number;
  issueTypeMix: ReleaseIssueTypeSlice[];
  sampleOpenIssues: ReleaseOpenIssue[];
  riskLevel: ReleaseRiskLevel;
  riskSummary: string;
};

export type ReleaseCycleTimeTrendPoint = {
  versionId: string;
  name: string;
  releaseDate?: string | null;
  cycleTimeDays?: number | null;
  storyPoints: number;
  issueCount: number;
};

export type ReleaseRiskSignal = {
  level: ReleaseRiskLevel;
  title: string;
  detail: string;
};

export type ReleaseInsightsResponse = {
  source: "local";
  generatedAt?: string | null;
  projectKey?: string | null;
  metrics: {
    totalReleases: number;
    releasedCount: number;
    ongoingCount: number;
    archivedCount: number;
    overdueCount: number;
    dueSoonCount: number;
    avgCycleTimeDays?: number | null;
    medianCycleTimeDays?: number | null;
    p85CycleTimeDays?: number | null;
    avgCadenceDays?: number | null;
    deliveredStoryPoints: number;
  };
  cycleTimeTrend: ReleaseCycleTimeTrendPoint[];
  ongoingReleases: ReleaseInsightRow[];
  recentReleases: ReleaseInsightRow[];
  riskSignals: ReleaseRiskSignal[];
  summary: string;
  error?: string | null;
};

function resolveApiBase(): string {
  const configured = (globalThis as unknown as { TEAMBEACON_API_BASE?: string }).TEAMBEACON_API_BASE;
  if (typeof configured === "string" && configured.trim()) {
    return configured.trim().replace(/\/+$/, "");
  }

  if (typeof window !== "undefined" && typeof window.location.origin === "string" && window.location.origin) {
    const { hostname, origin, port, protocol } = window.location;
    const normalizedOrigin = origin.replace(/\/+$/, "");
    const isLocalHost = hostname === "127.0.0.1" || hostname === "localhost";
    const isLocalWebDevServer = isLocalHost && (port === "5174" || port === "5173");
    const isTauriShell = protocol === "tauri:";

    // Local OJET/Tauri dev shells call the API on :8000, not the frontend dev server origin.
    if (isLocalWebDevServer || isTauriShell) {
      return "http://127.0.0.1:8000";
    }
    return normalizedOrigin;
  }

  return "http://127.0.0.1:8000";
}

const API_BASE = resolveApiBase();

async function parseError(response: Response, fallback: string): Promise<Error> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload?.detail) {
      return new Error(payload.detail);
    }
  } catch {
    // Best-effort parsing; fallback below.
  }
  return new Error(fallback);
}

export async function fetchJiraIntegrationStatus(): Promise<JiraIntegrationStatus> {
  const response = await fetch(`${API_BASE}/api/integrations/jira/status`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `JIRA status request failed (${response.status})`);
  }
  return (await response.json()) as JiraIntegrationStatus;
}

export async function fetchOciGenAiIntegrationStatus(): Promise<OciGenAiIntegrationStatus> {
  const response = await fetch(`${API_BASE}/api/integrations/oci-genai/status`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `OCI GenAI status request failed (${response.status})`);
  }
  return (await response.json()) as OciGenAiIntegrationStatus;
}

export async function fetchAiIntegrationStatus(provider?: AiProvider): Promise<AiIntegrationStatus> {
  const params = new URLSearchParams();
  if (provider) {
    params.set("provider", provider);
  }
  const query = params.toString();
  const suffix = query ? `?${query}` : "";

  const response = await fetch(`${API_BASE}/api/integrations/ai/status${suffix}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `AI status request failed (${response.status})`);
  }
  return (await response.json()) as AiIntegrationStatus;
}

export async function fetchConfluenceIntegrationStatus(): Promise<ConfluenceIntegrationStatus> {
  const response = await fetch(`${API_BASE}/api/integrations/confluence/status`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Confluence status request failed (${response.status})`);
  }
  return (await response.json()) as ConfluenceIntegrationStatus;
}

export async function fetchJenkinsIntegrationStatus(): Promise<JenkinsIntegrationStatus> {
  const response = await fetch(`${API_BASE}/api/integrations/jenkins/status`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Jenkins status request failed (${response.status})`);
  }
  return (await response.json()) as JenkinsIntegrationStatus;
}

export async function chatWithOciGenAi(payload: {
  message: string;
  provider?: AiProvider;
  modelId?: string;
  maxTokens?: number;
  temperature?: number;
  topP?: number;
  topK?: number;
  frequencyPenalty?: number;
}): Promise<OciGenAiChatResponse> {
  const response = await fetch(`${API_BASE}/api/ai/chat`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, `AI chat request failed (${response.status})`);
  }
  return (await response.json()) as OciGenAiChatResponse;
}

export async function fetchJiraSyncStatus(): Promise<JiraSyncStatus> {
  const response = await fetch(`${API_BASE}/api/integrations/jira/sync/status`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `JIRA sync status request failed (${response.status})`);
  }
  return (await response.json()) as JiraSyncStatus;
}

export async function startJiraSync(mode: JiraSyncMode = "full", sinceDate?: string): Promise<JiraSyncStatus> {
  const payload: { mode: JiraSyncMode; sinceDate?: string } = { mode };
  if (sinceDate) {
    payload.sinceDate = sinceDate;
  }
  const response = await fetch(`${API_BASE}/api/integrations/jira/sync/start`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, `JIRA sync start request failed (${response.status})`);
  }
  return (await response.json()) as JiraSyncStatus;
}

export async function fetchJiraSyncHistory(limit = 20): Promise<JiraSyncHistoryEntry[]> {
  const response = await fetch(`${API_BASE}/api/integrations/jira/sync/history?limit=${encodeURIComponent(String(limit))}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `JIRA sync history request failed (${response.status})`);
  }
  const payload = (await response.json()) as { source: string; history?: JiraSyncHistoryEntry[] };
  return payload.history ?? [];
}

export async function fetchSecurityAudit(): Promise<SecurityAuditResponse> {
  const response = await fetch(`${API_BASE}/api/security/audit`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Security audit request failed (${response.status})`);
  }
  return (await response.json()) as SecurityAuditResponse;
}

export async function fetchNewsDashboard(): Promise<NewsDashboardResponse> {
  const response = await fetch(`${API_BASE}/api/news/dashboard`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `News dashboard request failed (${response.status})`);
  }
  return (await response.json()) as NewsDashboardResponse;
}

export async function fetchConfiguredEpicSummary(
  limit = 50,
  options?: {
    periodStart?: string | null;
    periodEnd?: string | null;
    timezone?: string | null;
  },
): Promise<ConfiguredEpicSummaryResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (options?.periodStart) {
    params.set("periodStart", options.periodStart);
  }
  if (options?.periodEnd) {
    params.set("periodEnd", options.periodEnd);
  }
  if (options?.timezone) {
    params.set("timezone", options.timezone);
  }

  const response = await fetch(`${API_BASE}/api/metadata/epics/summary?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Configured epic summary request failed (${response.status})`);
  }
  return (await response.json()) as ConfiguredEpicSummaryResponse;
}

export async function fetchEpicCompletedCards(
  epicKey: string,
  options?: {
    limit?: number;
    periodStart?: string | null;
    periodEnd?: string | null;
    timezone?: string | null;
  },
): Promise<EpicCompletedCardsResponse> {
  const normalizedEpicKey = epicKey.trim();
  if (!normalizedEpicKey) {
    throw new Error("epicKey is required.");
  }

  const params = new URLSearchParams();
  params.set("epicKey", normalizedEpicKey);
  params.set("limit", String(options?.limit ?? 200));
  if (options?.periodStart) {
    params.set("periodStart", options.periodStart);
  }
  if (options?.periodEnd) {
    params.set("periodEnd", options.periodEnd);
  }
  if (options?.timezone) {
    params.set("timezone", options.timezone);
  }

  const response = await fetch(`${API_BASE}/api/metadata/epics/completed-cards?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Epic completed cards request failed (${response.status})`);
  }
  return (await response.json()) as EpicCompletedCardsResponse;
}

export async function fetchConfiguredEpicsCompletedCards(options?: {
  limit?: number;
  periodStart?: string | null;
  periodEnd?: string | null;
  timezone?: string | null;
}): Promise<ConfiguredEpicsCompletedCardsResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(options?.limit ?? 300));
  if (options?.periodStart) {
    params.set("periodStart", options.periodStart);
  }
  if (options?.periodEnd) {
    params.set("periodEnd", options.periodEnd);
  }
  if (options?.timezone) {
    params.set("timezone", options.timezone);
  }

  const response = await fetch(`${API_BASE}/api/metadata/epics/completed-cards/configured?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Configured completed cards request failed (${response.status})`);
  }
  return (await response.json()) as ConfiguredEpicsCompletedCardsResponse;
}

export async function fetchEpicLookupConfig(): Promise<EpicLookupConfig> {
  const response = await fetch(`${API_BASE}/api/metadata/lookup`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Epic lookup request failed (${response.status})`);
  }
  return (await response.json()) as EpicLookupConfig;
}

export async function addEpicGroup(name: string): Promise<EpicLookupItem> {
  const response = await fetch(`${API_BASE}/api/metadata/lookup/groups`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw await parseError(response, `Epic group create failed (${response.status})`);
  }
  return (await response.json()) as EpicLookupItem;
}

export async function updateEpicGroup(id: number, name: string): Promise<EpicLookupItem> {
  const response = await fetch(`${API_BASE}/api/metadata/lookup/groups/update`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ id, name }),
  });
  if (!response.ok) {
    throw await parseError(response, `Epic group update failed (${response.status})`);
  }
  return (await response.json()) as EpicLookupItem;
}

export async function deleteEpicGroup(id: number): Promise<{ id: number; deleted: boolean }> {
  const response = await fetch(`${API_BASE}/api/metadata/lookup/groups/delete`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  if (!response.ok) {
    throw await parseError(response, `Epic group delete failed (${response.status})`);
  }
  return (await response.json()) as { id: number; deleted: boolean };
}

export async function addWorkType(name: string): Promise<EpicLookupItem> {
  const response = await fetch(`${API_BASE}/api/metadata/lookup/work-types`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw await parseError(response, `Work type create failed (${response.status})`);
  }
  return (await response.json()) as EpicLookupItem;
}

export async function updateWorkType(id: number, name: string): Promise<EpicLookupItem> {
  const response = await fetch(`${API_BASE}/api/metadata/lookup/work-types/update`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ id, name }),
  });
  if (!response.ok) {
    throw await parseError(response, `Work type update failed (${response.status})`);
  }
  return (await response.json()) as EpicLookupItem;
}

export async function deleteWorkType(id: number): Promise<{ id: number; deleted: boolean }> {
  const response = await fetch(`${API_BASE}/api/metadata/lookup/work-types/delete`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  if (!response.ok) {
    throw await parseError(response, `Work type delete failed (${response.status})`);
  }
  return (await response.json()) as { id: number; deleted: boolean };
}

export async function fetchEpicCandidates(query: string, limit = 20): Promise<EpicCandidate[]> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  params.set("limit", String(limit));
  const response = await fetch(`${API_BASE}/api/metadata/epics/candidates?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Epic candidate request failed (${response.status})`);
  }
  const payload = (await response.json()) as { epics?: EpicCandidate[] };
  return payload.epics ?? [];
}

export async function upsertEpicMetadata(payload: {
  epicKey: string;
  successCriteria: string[];
  groupIds: number[];
  workTypeIds: number[];
  timelineEnabled?: boolean;
  timelineStartDate?: string | null;
  targetCompletionDate?: string | null;
}): Promise<EpicMetadataEntry> {
  const response = await fetch(`${API_BASE}/api/metadata/epics`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, `Epic metadata save failed (${response.status})`);
  }
  return (await response.json()) as EpicMetadataEntry;
}

export async function deleteEpicMetadata(epicKey: string): Promise<{
  epicKey: string;
  deleted: boolean;
  removedGroupMappings: number;
  removedWorkTypeMappings: number;
  removedMetadataRows: number;
}> {
  const response = await fetch(`${API_BASE}/api/metadata/epics/delete`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ epicKey }),
  });
  if (!response.ok) {
    throw await parseError(response, `Epic metadata delete failed (${response.status})`);
  }
  return (await response.json()) as {
    epicKey: string;
    deleted: boolean;
    removedGroupMappings: number;
    removedWorkTypeMappings: number;
    removedMetadataRows: number;
  };
}

export async function fetchCurrentSprint(): Promise<CurrentSprintResponse> {
  const response = await fetch(`${API_BASE}/api/sprints/current`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Current sprint request failed (${response.status})`);
  }
  return (await response.json()) as CurrentSprintResponse;
}

export async function fetchCurrentSprintWork(): Promise<CurrentSprintWorkResponse> {
  const response = await fetch(`${API_BASE}/api/sprints/current/work`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Current sprint work request failed (${response.status})`);
  }
  return (await response.json()) as CurrentSprintWorkResponse;
}

export async function fetchCurrentSprintChanges(): Promise<CurrentSprintChangesResponse> {
  const response = await fetch(`${API_BASE}/api/sprints/current/changes`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Current sprint changes request failed (${response.status})`);
  }
  return (await response.json()) as CurrentSprintChangesResponse;
}

export async function fetchTeamInsights(
  sprintLimit = 6,
  cycleTimeStatusKeys?: string[] | null,
): Promise<TeamInsightsResponse> {
  const params = new URLSearchParams();
  params.set("sprintLimit", String(sprintLimit));
  if (cycleTimeStatusKeys !== undefined && cycleTimeStatusKeys !== null) {
    params.set("cycleTimeStatusMode", "custom");
    for (const statusKey of cycleTimeStatusKeys) {
      params.append("cycleTimeStatus", statusKey);
    }
  }
  const response = await fetch(`${API_BASE}/api/team/insights?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Team insights request failed (${response.status})`);
  }
  return (await response.json()) as TeamInsightsResponse;
}

export async function startReleaseRefresh(payload: {
  sources: ReleaseRefreshSourceInput[];
  overallPrompt?: string;
}): Promise<ReleaseRefreshStatus> {
  const response = await fetch(`${API_BASE}/api/releases/refresh/start`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, `Release refresh start request failed (${response.status})`);
  }
  return (await response.json()) as ReleaseRefreshStatus;
}

export async function fetchReleaseRefreshStatus(): Promise<ReleaseRefreshStatus> {
  const response = await fetch(`${API_BASE}/api/releases/refresh/status`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Release refresh status request failed (${response.status})`);
  }
  return (await response.json()) as ReleaseRefreshStatus;
}

export async function fetchReleaseRefreshResult(): Promise<ReleaseRefreshResult> {
  const response = await fetch(`${API_BASE}/api/releases/refresh/result`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Release refresh result request failed (${response.status})`);
  }
  return (await response.json()) as ReleaseRefreshResult;
}

export async function fetchReleaseInsights(releaseLimit = 12, projectKey?: string | null): Promise<ReleaseInsightsResponse> {
  const params = new URLSearchParams();
  params.set("releaseLimit", String(releaseLimit));
  if (projectKey?.trim()) {
    params.set("projectKey", projectKey.trim());
  }
  const response = await fetch(`${API_BASE}/api/releases/insights?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response, `Release insights request failed (${response.status})`);
  }
  return (await response.json()) as ReleaseInsightsResponse;
}
