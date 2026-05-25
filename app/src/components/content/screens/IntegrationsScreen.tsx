import { h } from "preact";
import { useCallback, useEffect, useMemo, useState } from "preact/hooks";
import {
  addEpicGroup,
  addWorkType,
  AiIntegrationStatus,
  ConfluenceIntegrationStatus,
  deleteEpicGroup,
  deleteWorkType,
  EpicLookupConfig,
  fetchAiIntegrationStatus,
  fetchConfluenceIntegrationStatus,
  fetchEpicLookupConfig,
  fetchJenkinsIntegrationStatus,
  fetchJiraIntegrationStatus,
  fetchJiraSyncHistory,
  fetchJiraSyncStatus,
  JenkinsIntegrationStatus,
  JiraIntegrationStatus,
  JiraSyncHistoryEntry,
  JiraSyncMode,
  JiraSyncStatus,
  startJiraSync,
  updateEpicGroup,
  updateWorkType,
} from "../../../lib/api";

const SHORT_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

function formatDateOnlyLabel(value: string): string | null {
  const trimmed = value.trim();
  const dateOnlyMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  if (dateOnlyMatch) {
    const [, year, month, day] = dateOnlyMatch;
    const monthIndex = Number.parseInt(month, 10) - 1;
    if (monthIndex < 0 || monthIndex >= SHORT_MONTH_NAMES.length) {
      return null;
    }
    return `${day}-${SHORT_MONTH_NAMES[monthIndex]}-${year}`;
  }

  const date = new Date(trimmed);
  if (Number.isNaN(date.getTime())) return null;
  const day = String(date.getDate()).padStart(2, "0");
  const month = SHORT_MONTH_NAMES[date.getMonth()];
  const year = String(date.getFullYear());
  return `${day}-${month}-${year}`;
}

function formatDateTimeLabel(value: string): string | null {
  const dateLabel = formatDateOnlyLabel(value);
  if (!dateLabel) return null;
  const dateOnlyMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (dateOnlyMatch) {
    return dateLabel;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return `${dateLabel}, ${parsed.toLocaleTimeString()}`;
}

function formatCheckedAt(value: string | null | undefined): string {
  if (!value) return "n/a";
  const formatted = formatDateTimeLabel(value);
  return formatted ?? value;
}

function checksSummary(checks: { ok: boolean }[] | undefined): string {
  if (!checks || checks.length === 0) return "No connectivity checks returned.";
  const passed = checks.filter((check) => check.ok).length;
  return `${passed}/${checks.length} connectivity checks passed.`;
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  const formatted = formatDateTimeLabel(value);
  return formatted ?? value;
}

function formatSyncMode(mode: JiraSyncMode | null | undefined, requestedSince?: string | null): string {
  if (mode === "since_date") {
    if (!requestedSince) return "Since Date";
    const formatted = formatDateOnlyLabel(requestedSince);
    return `Since ${formatted ?? requestedSince}`;
  }
  return mode === "since_last" ? "Since Last" : "Full";
}

function formatAiProviderName(value: string | null | undefined): string {
  const normalized = (value ?? "").trim().toLowerCase();
  if (normalized === "oci" || normalized === "oci-genai" || normalized === "oci_genai") return "OCI";
  if (normalized === "ollama") return "Ollama";
  if (normalized === "openai") return "OpenAI";
  return "AI";
}

type PendingLookupDelete = {
  type: "group" | "workType";
  id: number;
  name: string;
} | null;

export function IntegrationsScreen() {
  const todayLocalDate = useMemo(() => {
    const now = new Date();
    const shifted = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    return shifted.toISOString().slice(0, 10);
  }, []);

  const [jiraStatus, setJiraStatus] = useState<JiraIntegrationStatus | null>(null);
  const [aiStatus, setAiStatus] = useState<AiIntegrationStatus | null>(null);
  const [confluenceStatus, setConfluenceStatus] = useState<ConfluenceIntegrationStatus | null>(null);
  const [jenkinsStatus, setJenkinsStatus] = useState<JenkinsIntegrationStatus | null>(null);
  const [jiraSyncStatus, setJiraSyncStatus] = useState<JiraSyncStatus | null>(null);
  const [jiraSyncHistory, setJiraSyncHistory] = useState<JiraSyncHistoryEntry[]>([]);

  const [jiraError, setJiraError] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [confluenceError, setConfluenceError] = useState<string | null>(null);
  const [jenkinsError, setJenkinsError] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [metaSuccess, setMetaSuccess] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(true);
  const [confluenceLoading, setConfluenceLoading] = useState(true);
  const [jenkinsLoading, setJenkinsLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isSyncOptionsOpen, setIsSyncOptionsOpen] = useState(false);
  const [isJiraDiagnosticsOpen, setIsJiraDiagnosticsOpen] = useState(false);
  const [selectedSyncMode, setSelectedSyncMode] = useState<JiraSyncMode>("since_last");
  const [selectedSinceDate, setSelectedSinceDate] = useState(todayLocalDate);

  const [epicLookup, setEpicLookup] = useState<EpicLookupConfig>({ groups: [], workTypes: [] });
  const [groupDraft, setGroupDraft] = useState("");
  const [workTypeDraft, setWorkTypeDraft] = useState("");
  const [editingGroupId, setEditingGroupId] = useState<number | null>(null);
  const [editingGroupName, setEditingGroupName] = useState("");
  const [editingWorkTypeId, setEditingWorkTypeId] = useState<number | null>(null);
  const [editingWorkTypeName, setEditingWorkTypeName] = useState("");
  const [pendingLookupDelete, setPendingLookupDelete] = useState<PendingLookupDelete>(null);
  const [lookupDeleteLoading, setLookupDeleteLoading] = useState(false);

  const loadJiraStatus = useCallback(async () => {
    setLoading(true);
    setJiraError(null);
    try {
      const status = await fetchJiraIntegrationStatus();
      setJiraStatus(status);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown JIRA status failure.";
      setJiraError(message);
      setJiraStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAiStatus = useCallback(async () => {
    setAiLoading(true);
    setAiError(null);
    try {
      const status = await fetchAiIntegrationStatus();
      setAiStatus(status);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown AI status failure.";
      setAiError(message);
      setAiStatus(null);
    } finally {
      setAiLoading(false);
    }
  }, []);

  const loadConfluenceStatus = useCallback(async () => {
    setConfluenceLoading(true);
    setConfluenceError(null);
    try {
      const status = await fetchConfluenceIntegrationStatus();
      setConfluenceStatus(status);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown Confluence status failure.";
      setConfluenceError(message);
      setConfluenceStatus(null);
    } finally {
      setConfluenceLoading(false);
    }
  }, []);

  const loadJenkinsStatus = useCallback(async () => {
    setJenkinsLoading(true);
    setJenkinsError(null);
    try {
      const status = await fetchJenkinsIntegrationStatus();
      setJenkinsStatus(status);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown Jenkins status failure.";
      setJenkinsError(message);
      setJenkinsStatus(null);
    } finally {
      setJenkinsLoading(false);
    }
  }, []);

  const loadJiraSyncStatus = useCallback(async () => {
    try {
      const status = await fetchJiraSyncStatus();
      setJiraSyncStatus(status);
      setSyncError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown sync status failure.";
      setSyncError(message);
      setJiraSyncStatus(null);
    }
  }, []);

  const loadJiraSyncHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const entries = await fetchJiraSyncHistory(30);
      setJiraSyncHistory(entries);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown sync history failure.";
      setHistoryError(message);
      setJiraSyncHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const loadEpicMetadataConfig = useCallback(async () => {
    setMetaError(null);
    try {
      const lookup = await fetchEpicLookupConfig();
      setEpicLookup(lookup);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown epic metadata failure.";
      setMetaError(message);
      setEpicLookup({ groups: [], workTypes: [] });
    }
  }, []);

  const checkSourceConnections = useCallback(() => {
    loadJiraStatus().catch(() => {
      // loadJiraStatus updates local state.
    });
    loadAiStatus().catch(() => {
      // loadAiStatus updates local state.
    });
    loadConfluenceStatus().catch(() => {
      // loadConfluenceStatus updates local state.
    });
    loadJenkinsStatus().catch(() => {
      // loadJenkinsStatus updates local state.
    });
  }, [loadAiStatus, loadConfluenceStatus, loadJenkinsStatus, loadJiraStatus]);

  const triggerJiraSync = useCallback(async (mode: JiraSyncMode, sinceDate?: string) => {
    setSyncError(null);
    try {
      const status = await startJiraSync(mode, sinceDate);
      setJiraSyncStatus(status);
      setIsSyncOptionsOpen(false);
      await loadJiraSyncStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown sync start failure.";
      setSyncError(message);
    }
  }, [loadJiraSyncStatus]);

  useEffect(() => {
    loadJiraStatus().catch(() => {
      // loadJiraStatus updates local state.
    });
    loadAiStatus().catch(() => {
      // loadAiStatus updates local state.
    });
    loadConfluenceStatus().catch(() => {
      // loadConfluenceStatus updates local state.
    });
    loadJenkinsStatus().catch(() => {
      // loadJenkinsStatus updates local state.
    });
    loadJiraSyncStatus().catch(() => {
      // loadJiraSyncStatus updates local state.
    });
    loadEpicMetadataConfig().catch(() => {
      // loadEpicMetadataConfig updates local state.
    });
  }, [loadAiStatus, loadConfluenceStatus, loadEpicMetadataConfig, loadJenkinsStatus, loadJiraStatus, loadJiraSyncStatus]);

  useEffect(() => {
    if (jiraSyncStatus?.state !== "running") {
      return;
    }
    const intervalId = window.setInterval(() => {
      loadJiraSyncStatus().catch(() => {
        // loadJiraSyncStatus updates local state.
      });
    }, 1500);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [jiraSyncStatus?.state, loadJiraSyncStatus]);

  useEffect(() => {
    if (!isHistoryOpen || jiraSyncStatus?.state !== "running") {
      return;
    }
    const intervalId = window.setInterval(() => {
      loadJiraSyncHistory().catch(() => {
        // loadJiraSyncHistory updates local state.
      });
    }, 2000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [isHistoryOpen, jiraSyncStatus?.state, loadJiraSyncHistory]);

  useEffect(() => {
    if (!metaSuccess) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setMetaSuccess(null);
    }, 2600);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [metaSuccess]);

  const openSyncOptions = useCallback(() => {
    if (jiraSyncStatus?.state === "running") {
      return;
    }
    setSelectedSyncMode("since_last");
    setSelectedSinceDate(todayLocalDate);
    setIsSyncOptionsOpen(true);
  }, [jiraSyncStatus?.state, todayLocalDate]);

  const openHistoryOverlay = useCallback(() => {
    setIsHistoryOpen(true);
    loadJiraSyncHistory().catch(() => {
      // loadJiraSyncHistory updates local state.
    });
  }, [loadJiraSyncHistory]);

  const handleAddEpicGroup = useCallback(async () => {
    const candidate = groupDraft.trim();
    if (!candidate) {
      setMetaError("Epic group name is required.");
      return;
    }
    setMetaError(null);
    setMetaSuccess(null);
    try {
      await addEpicGroup(candidate);
      setGroupDraft("");
      await loadEpicMetadataConfig();
      setMetaSuccess(`Epic group "${candidate}" saved.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save epic group.";
      setMetaError(message);
    }
  }, [groupDraft, loadEpicMetadataConfig]);

  const handleAddWorkType = useCallback(async () => {
    const candidate = workTypeDraft.trim();
    if (!candidate) {
      setMetaError("Work type name is required.");
      return;
    }
    setMetaError(null);
    setMetaSuccess(null);
    try {
      await addWorkType(candidate);
      setWorkTypeDraft("");
      await loadEpicMetadataConfig();
      setMetaSuccess(`Work type "${candidate}" saved.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save work type.";
      setMetaError(message);
    }
  }, [loadEpicMetadataConfig, workTypeDraft]);

  const beginEditGroup = useCallback((id: number, name: string) => {
    setEditingGroupId(id);
    setEditingGroupName(name);
    setMetaError(null);
    setMetaSuccess(null);
  }, []);

  const cancelEditGroup = useCallback(() => {
    setEditingGroupId(null);
    setEditingGroupName("");
  }, []);

  const handleSaveEditedGroup = useCallback(async () => {
    if (editingGroupId === null) {
      return;
    }
    const candidate = editingGroupName.trim();
    if (!candidate) {
      setMetaError("Epic group name is required.");
      return;
    }
    setMetaError(null);
    setMetaSuccess(null);
    try {
      await updateEpicGroup(editingGroupId, candidate);
      await loadEpicMetadataConfig();
      setMetaSuccess("Epic group updated.");
      setEditingGroupId(null);
      setEditingGroupName("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update epic group.";
      setMetaError(message);
    }
  }, [editingGroupId, editingGroupName, loadEpicMetadataConfig]);

  const requestDeleteGroup = useCallback((id: number, name: string) => {
    setMetaError(null);
    setMetaSuccess(null);
    setPendingLookupDelete({ type: "group", id, name });
  }, []);

  const beginEditWorkType = useCallback((id: number, name: string) => {
    setEditingWorkTypeId(id);
    setEditingWorkTypeName(name);
    setMetaError(null);
    setMetaSuccess(null);
  }, []);

  const cancelEditWorkType = useCallback(() => {
    setEditingWorkTypeId(null);
    setEditingWorkTypeName("");
  }, []);

  const handleSaveEditedWorkType = useCallback(async () => {
    if (editingWorkTypeId === null) {
      return;
    }
    const candidate = editingWorkTypeName.trim();
    if (!candidate) {
      setMetaError("Work type name is required.");
      return;
    }
    setMetaError(null);
    setMetaSuccess(null);
    try {
      await updateWorkType(editingWorkTypeId, candidate);
      await loadEpicMetadataConfig();
      setMetaSuccess("Work type updated.");
      setEditingWorkTypeId(null);
      setEditingWorkTypeName("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update work type.";
      setMetaError(message);
    }
  }, [editingWorkTypeId, editingWorkTypeName, loadEpicMetadataConfig]);

  const requestDeleteWorkType = useCallback((id: number, name: string) => {
    setMetaError(null);
    setMetaSuccess(null);
    setPendingLookupDelete({ type: "workType", id, name });
  }, []);

  const confirmLookupDelete = useCallback(async () => {
    if (!pendingLookupDelete) {
      return;
    }

    setLookupDeleteLoading(true);
    setMetaError(null);
    setMetaSuccess(null);
    try {
      if (pendingLookupDelete.type === "group") {
        await deleteEpicGroup(pendingLookupDelete.id);
        if (editingGroupId === pendingLookupDelete.id) {
          setEditingGroupId(null);
          setEditingGroupName("");
        }
        setMetaSuccess(`Epic group "${pendingLookupDelete.name}" deleted.`);
      } else {
        await deleteWorkType(pendingLookupDelete.id);
        if (editingWorkTypeId === pendingLookupDelete.id) {
          setEditingWorkTypeId(null);
          setEditingWorkTypeName("");
        }
        setMetaSuccess(`Work type "${pendingLookupDelete.name}" deleted.`);
      }
      await loadEpicMetadataConfig();
      setPendingLookupDelete(null);
    } catch (err) {
      const message = err instanceof Error
        ? err.message
        : pendingLookupDelete.type === "group"
          ? "Failed to delete epic group."
          : "Failed to delete work type.";
      setMetaError(message);
    } finally {
      setLookupDeleteLoading(false);
    }
  }, [editingGroupId, editingWorkTypeId, loadEpicMetadataConfig, pendingLookupDelete]);

  const jiraValue = useMemo(() => {
    if (jiraError) return "Unavailable";
    if (loading) return "Checking...";
    return jiraStatus?.connected ? "Connected" : "Check Required";
  }, [jiraError, jiraStatus, loading]);

  const aiValue = useMemo(() => {
    if (aiError) return "Unavailable";
    if (aiLoading) return "Checking...";
    return aiStatus?.connected ? "Connected" : "Check Required";
  }, [aiError, aiLoading, aiStatus]);

  const confluenceValue = useMemo(() => {
    if (confluenceError) return "Unavailable";
    if (confluenceLoading) return "Checking...";
    return confluenceStatus?.connected ? "Connected" : "Check Required";
  }, [confluenceError, confluenceLoading, confluenceStatus]);

  const jenkinsValue = useMemo(() => {
    if (jenkinsError) return "Unavailable";
    if (jenkinsLoading) return "Checking...";
    return jenkinsStatus?.connected ? "Connected" : "Check Required";
  }, [jenkinsError, jenkinsLoading, jenkinsStatus]);

  const jiraToneClass = jiraError ? "tb-value-risk" : jiraStatus?.connected ? "tb-value-good" : "tb-value-warn";
  const aiToneClass = aiError ? "tb-value-risk" : aiStatus?.connected ? "tb-value-good" : "tb-value-warn";
  const confluenceToneClass = confluenceError
    ? "tb-value-risk"
    : confluenceStatus?.connected
      ? "tb-value-good"
      : "tb-value-warn";
  const jenkinsToneClass = jenkinsError
    ? "tb-value-risk"
    : jenkinsStatus?.connected
      ? "tb-value-good"
      : "tb-value-warn";

  const jiraHint = useMemo(() => {
    if (jiraError) return jiraError;
    if (loading) return "Testing JIRA API reachability and board/project access.";
    if (!jiraStatus) return "Status not loaded.";
    if (jiraStatus.error) return jiraStatus.error;
    return checksSummary(jiraStatus.checks);
  }, [jiraError, jiraStatus, loading]);

  const aiProviderName = useMemo(
    () => formatAiProviderName(aiStatus?.provider ?? aiStatus?.configuredProvider ?? aiStatus?.source),
    [aiStatus?.configuredProvider, aiStatus?.provider, aiStatus?.source],
  );
  const aiModelName = useMemo(() => {
    const raw = aiStatus?.config?.modelId;
    if (typeof raw === "string" && raw.trim()) return raw.trim();
    return "n/a";
  }, [aiStatus?.config?.modelId]);

  const aiHint = useMemo(() => {
    if (aiError) return aiError;
    if (aiLoading) {
      if (aiProviderName === "OCI") return "Testing OCI GenAI endpoint and OCI profile access.";
      if (aiProviderName === "Ollama") return "Testing Ollama endpoint and configured model access.";
      if (aiProviderName === "OpenAI") return "Testing OpenAI endpoint and configured model access.";
      return "Testing AI provider connectivity.";
    }
    if (!aiStatus) return "Status not loaded.";
    if (aiStatus.error) return aiStatus.error;
    return checksSummary(aiStatus.checks);
  }, [aiError, aiLoading, aiProviderName, aiStatus]);

  const confluenceHint = useMemo(() => {
    if (confluenceError) return confluenceError;
    if (confluenceLoading) return "Testing Confluence REST API reachability and PAT access.";
    if (!confluenceStatus) return "Status not loaded.";
    if (confluenceStatus.error) return confluenceStatus.error;
    return checksSummary(confluenceStatus.checks);
  }, [confluenceError, confluenceLoading, confluenceStatus]);

  const jenkinsHint = useMemo(() => {
    if (jenkinsError) return jenkinsError;
    if (jenkinsLoading) return "Testing Jenkins job API reachability and API token access.";
    if (!jenkinsStatus) return "Status not loaded.";
    if (jenkinsStatus.error) return jenkinsStatus.error;
    return checksSummary(jenkinsStatus.checks);
  }, [jenkinsError, jenkinsLoading, jenkinsStatus]);

  const jiraSyncToneClass = useMemo(() => {
    if (syncError) return "is-risk";
    if (!jiraSyncStatus) return "is-neutral";
    if (jiraSyncStatus.state === "failed") return "is-risk";
    if (jiraSyncStatus.state === "running") return "is-warn";
    if (jiraSyncStatus.state === "completed") return "is-good";
    return "is-neutral";
  }, [syncError, jiraSyncStatus]);

  const jiraSyncStateText = useMemo(() => {
    if (syncError) return "Sync Error";
    if (!jiraSyncStatus) return "Idle";
    if (jiraSyncStatus.state === "running") return "Syncing";
    if (jiraSyncStatus.state === "completed") return "Completed";
    if (jiraSyncStatus.state === "failed") return "Failed";
    return "Idle";
  }, [syncError, jiraSyncStatus]);

  const jiraSyncPercent = useMemo(() => {
    if (!jiraSyncStatus || syncError) return null;
    if (typeof jiraSyncStatus.percent === "number" && Number.isFinite(jiraSyncStatus.percent)) {
      const bounded = Math.max(0, Math.min(100, jiraSyncStatus.percent));
      return Math.round(bounded * 10) / 10;
    }
    if (jiraSyncStatus.state === "completed") {
      return 100;
    }
    return null;
  }, [syncError, jiraSyncStatus]);

  const jiraSyncProgressSummary = useMemo(() => {
    if (syncError) return `Sync status error: ${syncError}`;
    if (!jiraSyncStatus) return "Sync not started.";
    if (jiraSyncStatus.state === "failed") {
      return jiraSyncStatus.error ?? "Last sync failed.";
    }
    if (jiraSyncStatus.state === "running") {
      return "In progress";
    }
    if (jiraSyncStatus.state === "completed") {
      return "Sync complete.";
    }
    if (jiraSyncStatus.lastSyncedAt) {
      return "Not currently syncing.";
    }
    return "Sync not started.";
  }, [syncError, jiraSyncStatus]);

  const jiraLastSyncedText = useMemo(() => formatCheckedAt(jiraSyncStatus?.lastSyncedAt), [jiraSyncStatus?.lastSyncedAt]);

  const showJiraSyncStatusPillInActions = Boolean(syncError || jiraSyncStatus?.state === "failed");
  const showJiraSyncProgressNote = jiraSyncPercent !== null && jiraSyncProgressSummary !== "In progress";

  const jiraBaseUrl = jiraStatus?.config.baseUrl ? jiraStatus.config.baseUrl.replace(/\/$/, "") : null;
  const configuredBoard = jiraStatus?.configuredBoard;
  const configuredBoardUrl = configuredBoard?.url
    ?? (jiraBaseUrl && jiraStatus?.config.boardId
      ? `${jiraBaseUrl}/secure/RapidBoard.jspa?rapidView=${jiraStatus.config.boardId}`
      : null);
  const configuredProjectUrl = jiraStatus?.configuredProjectUrl
    ?? (jiraBaseUrl && jiraStatus?.config.projectKey
      ? `${jiraBaseUrl}/projects/${jiraStatus.config.projectKey}`
      : null);
  const sampleIssueUrl = jiraStatus?.sampleIssueUrl
    ?? (jiraBaseUrl && jiraStatus?.sampleIssueKey
      ? `${jiraBaseUrl}/browse/${jiraStatus.sampleIssueKey}`
      : null);

  const configuredBoardText = configuredBoard?.id !== undefined
    ? `${configuredBoard.name} (${configuredBoard.id})`
    : jiraStatus?.config.boardId !== undefined && jiraStatus?.config.boardId !== null
      ? `Board ${jiraStatus.config.boardId}`
      : "n/a";

  const storyPointsField = jiraStatus?.config.storyPointsField ?? "customfield_10004";
  const epicLinkField = jiraStatus?.config.epicLinkField ?? "customfield_10902";
  const sprintFields = jiraStatus?.config.sprintFields?.length
    ? jiraStatus.config.sprintFields.join(", ")
    : "auto-detected";

  return (
    <div class="tb-screen-grid">
      <section class="tb-panel">
        <header class="tb-panel-header">
          <div>
            <h3>Source Connections</h3>
            <p class="tb-muted-note">Live connectivity checks from frontend to TeamBeacon backend integrations.</p>
          </div>
          <button type="button" class="tb-btn tb-btn-primary" onClick={checkSourceConnections}>
            {loading || aiLoading || confluenceLoading || jenkinsLoading ? "Checking..." : "Check Now"}
          </button>
        </header>
        <div class="tb-metrics-grid tb-four-up">
          <article class="tb-metric-card">
            <h4>JIRA Connection</h4>
            <strong class={`tb-value ${jiraToneClass}`}>{jiraValue}</strong>
            <p>{jiraHint}</p>
            <p>Last checked: {formatCheckedAt(jiraStatus?.checkedAt)}</p>
            {jiraSyncStatus?.state === "running" ? (
              <>
                <p class="tb-sync-progress-row">
                  <span>Sync:</span>
                  {jiraSyncStatus?.state === "running" ? (
                    <span class={`tb-status-pill ${jiraSyncToneClass}`}>
                      <span class="tb-inline-spinner" aria-hidden="true" />
                      <span>{jiraSyncStateText}</span>
                    </span>
                  ) : null}
                  {jiraSyncPercent !== null ? (
                    <>
                      <span
                        class="tb-sync-progress-track"
                        role="progressbar"
                        aria-label="JIRA sync progress"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={jiraSyncPercent}
                      >
                        <span class="tb-sync-progress-fill" style={{ width: `${jiraSyncPercent}%` }} />
                      </span>
                      <span class="tb-sync-progress-percent">{jiraSyncPercent.toFixed(1).replace(/\.0$/, "")}%</span>
                    </>
                  ) : null}
                </p>
                {showJiraSyncProgressNote ? <p class="tb-sync-progress-note">{jiraSyncProgressSummary}</p> : null}
              </>
            ) : null}
            <p>Last synced: {jiraLastSyncedText}</p>
            <div class="tb-card-actions">
              <button
                type="button"
                class="tb-btn tb-btn-sm"
                onClick={openSyncOptions}
                disabled={jiraSyncStatus?.state === "running"}
              >
                {jiraSyncStatus?.state === "running" ? "Syncing..." : "Sync Data"}
              </button>
              <button type="button" class="tb-btn tb-btn-sm" onClick={openHistoryOverlay}>
                Sync History
              </button>
              <button type="button" class="tb-btn tb-btn-sm" onClick={() => setIsJiraDiagnosticsOpen(true)}>
                Diagnostics
              </button>
              {showJiraSyncStatusPillInActions ? (
                <span class={`tb-status-pill ${jiraSyncToneClass}`}>
                  {jiraSyncStatus?.state === "running" ? (
                    <span class="tb-inline-spinner" aria-hidden="true" />
                  ) : null}
                  <span>{jiraSyncStateText}</span>
                </span>
              ) : null}
            </div>
          </article>

          <article class="tb-metric-card">
            <h4>Confluence Connection</h4>
            <strong class={`tb-value ${confluenceToneClass}`}>{confluenceValue}</strong>
            <p>{confluenceHint}</p>
            <p>Last checked: {formatCheckedAt(confluenceStatus?.checkedAt)}</p>
          </article>

          <article class="tb-metric-card">
            <h4>Jenkins Connection</h4>
            <strong class={`tb-value ${jenkinsToneClass}`}>{jenkinsValue}</strong>
            <p>{jenkinsHint}</p>
            <p>Last checked: {formatCheckedAt(jenkinsStatus?.checkedAt)}</p>
            <p>Job: {jenkinsStatus?.metrics?.jobName ?? "n/a"}</p>
            <p>Last build: {jenkinsStatus?.metrics?.lastBuildNumber ?? "n/a"}</p>
          </article>

          <article class="tb-metric-card">
            <h4>AI Model Connection</h4>
            <strong class={`tb-value ${aiToneClass}`}>{aiValue}</strong>
            <p>{aiHint}</p>
            <p>Last checked: {formatCheckedAt(aiStatus?.checkedAt)}</p>
            <p>Provider: {aiProviderName}</p>
            <p>Model: {aiModelName}</p>
          </article>
        </div>
      </section>

      <section class="tb-panel">
        <header class="tb-panel-header">
          <div>
            <h3>Epic Metadata Configuration</h3>
            <p class="tb-muted-note">Manage reusable epic groups and work types used by epic configuration.</p>
          </div>
        </header>

        {metaError ? <p class="tb-error-note">Epic metadata error: {metaError}</p> : null}

        <div class="tb-lookup-grid">
          <article class="tb-lookup-card">
            <h4>Epic Groups</h4>
            <div class="tb-lookup-add-row">
              <input
                type="text"
                value={groupDraft}
                onInput={(event) => setGroupDraft((event.currentTarget as HTMLInputElement).value)}
                placeholder="Add epic group"
              />
              <button type="button" class="tb-btn tb-btn-sm" onClick={() => handleAddEpicGroup()}>
                Add
              </button>
            </div>
            <div class="tb-lookup-item-list">
              {epicLookup.groups.length === 0 ? <span class="tb-chip">No groups</span> : null}
              {epicLookup.groups.map((group) => (
                <div key={group.id} class="tb-lookup-item-row">
                  {editingGroupId === group.id ? (
                    <input
                      type="text"
                      value={editingGroupName}
                      onInput={(event) => setEditingGroupName((event.currentTarget as HTMLInputElement).value)}
                      placeholder="Epic group name"
                    />
                  ) : (
                    <span class="tb-chip">{group.name}</span>
                  )}
                  <div class="tb-action-row">
                    {editingGroupId === group.id ? (
                      <>
                        <button type="button" class="tb-btn tb-btn-sm" onClick={() => handleSaveEditedGroup()}>
                          Save
                        </button>
                        <button type="button" class="tb-btn tb-btn-sm" onClick={cancelEditGroup}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" class="tb-btn tb-btn-sm" onClick={() => beginEditGroup(group.id, group.name)}>
                          Edit
                        </button>
                        <button type="button" class="tb-btn tb-btn-sm tb-btn-danger" onClick={() => requestDeleteGroup(group.id, group.name)}>
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article class="tb-lookup-card">
            <h4>Work Types</h4>
            <div class="tb-lookup-add-row">
              <input
                type="text"
                value={workTypeDraft}
                onInput={(event) => setWorkTypeDraft((event.currentTarget as HTMLInputElement).value)}
                placeholder="Add work type"
              />
              <button type="button" class="tb-btn tb-btn-sm" onClick={() => handleAddWorkType()}>
                Add
              </button>
            </div>
            <div class="tb-lookup-item-list">
              {epicLookup.workTypes.length === 0 ? <span class="tb-chip">No work types</span> : null}
              {epicLookup.workTypes.map((workType) => (
                <div key={workType.id} class="tb-lookup-item-row">
                  {editingWorkTypeId === workType.id ? (
                    <input
                      type="text"
                      value={editingWorkTypeName}
                      onInput={(event) => setEditingWorkTypeName((event.currentTarget as HTMLInputElement).value)}
                      placeholder="Work type name"
                    />
                  ) : (
                    <span class="tb-chip">{workType.name}</span>
                  )}
                  <div class="tb-action-row">
                    {editingWorkTypeId === workType.id ? (
                      <>
                        <button type="button" class="tb-btn tb-btn-sm" onClick={() => handleSaveEditedWorkType()}>
                          Save
                        </button>
                        <button type="button" class="tb-btn tb-btn-sm" onClick={cancelEditWorkType}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" class="tb-btn tb-btn-sm" onClick={() => beginEditWorkType(workType.id, workType.name)}>
                          Edit
                        </button>
                        <button type="button" class="tb-btn tb-btn-sm tb-btn-danger" onClick={() => requestDeleteWorkType(workType.id, workType.name)}>
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </article>
        </div>
      </section>

      {metaSuccess ? (
        <div class="tb-overlay-toast-layer" aria-live="polite" aria-atomic="true">
          <div class="tb-overlay-toast is-success">{metaSuccess}</div>
        </div>
      ) : null}

      {isJiraDiagnosticsOpen ? (
        <div class="tb-modal-layer" role="dialog" aria-modal="true" aria-label="Diagnostics">
          <div class="tb-modal-backdrop" onClick={() => setIsJiraDiagnosticsOpen(false)} />
          <div class="tb-modal tb-modal-diagnostics">
            <header class="tb-modal-head">
              <div>
                <h3>Diagnostics</h3>
                <p class="tb-muted-note">Board and project checks from live API response.</p>
              </div>
              <button type="button" class="tb-btn tb-btn-sm" onClick={() => setIsJiraDiagnosticsOpen(false)}>
                Close
              </button>
            </header>

            <div class="tb-metrics-grid tb-three-up">
              <article class="tb-metric-card">
                <h4>Configured Board</h4>
                <strong class={`tb-value ${jiraStatus?.connected ? "tb-value-good" : "tb-value-warn"}`}>
                  {configuredBoardUrl ? (
                    <a class="tb-external-link" href={configuredBoardUrl} target="_blank" rel="noopener noreferrer">
                      {configuredBoardText}
                    </a>
                  ) : (
                    configuredBoardText
                  )}
                </strong>
              </article>
              <article class="tb-metric-card">
                <h4>Sample Issue</h4>
                <strong class={`tb-value ${jiraStatus?.sampleIssueKey ? "tb-value-good" : "tb-value-warn"}`}>
                  {sampleIssueUrl && jiraStatus?.sampleIssueKey ? (
                    <a class="tb-external-link" href={sampleIssueUrl} target="_blank" rel="noopener noreferrer">
                      {jiraStatus.sampleIssueKey}
                    </a>
                  ) : (
                    jiraStatus?.sampleIssueKey ?? "none"
                  )}
                </strong>
              </article>
              <article class="tb-metric-card">
                <h4>Configured Project</h4>
                <strong class={`tb-value ${jiraStatus?.config.projectKey ? "tb-value-good" : "tb-value-warn"}`}>
                  {configuredProjectUrl && jiraStatus?.config.projectKey ? (
                    <a class="tb-external-link" href={configuredProjectUrl} target="_blank" rel="noopener noreferrer">
                      {jiraStatus.config.projectKey}
                    </a>
                  ) : (
                    jiraStatus?.config.projectKey ?? "n/a"
                  )}
                </strong>
              </article>
            </div>

            <hr class="tb-section-divider" />

            <header class="tb-panel-header">
              <div>
                <h3>Field Mapping Readiness</h3>
                <p class="tb-muted-note">Track required custom fields before sync pipelines run.</p>
              </div>
              <span class={`tb-status-pill ${jiraStatus?.connected ? "is-good" : "is-warn"}`}>
                {jiraStatus?.connected ? "JIRA Mapping Loaded" : "Pending Live Check"}
              </span>
            </header>
            <ul class="tb-integration-list">
              <li>
                <span class="tb-integration-label">Story Points</span>
                <span class="tb-status-pill is-good">{storyPointsField}</span>
              </li>
              <li>
                <span class="tb-integration-label">Sprint Fields</span>
                <span class="tb-status-pill is-good">{sprintFields}</span>
              </li>
              <li>
                <span class="tb-integration-label">Epic Link</span>
                <span class="tb-status-pill is-good">{epicLinkField}</span>
              </li>
            </ul>
          </div>
        </div>
      ) : null}

      {isSyncOptionsOpen ? (
        <div class="tb-modal-layer" role="dialog" aria-modal="true" aria-label="Start JIRA Sync">
          <div class="tb-modal-backdrop" onClick={() => setIsSyncOptionsOpen(false)} />
          <div class="tb-modal tb-modal-sync">
            <h3>Start JIRA Sync</h3>
            <p class="tb-muted-note">Choose how much data to refresh before starting the sync.</p>

            <div class="tb-sync-option-list">
              <label class={`tb-sync-option ${selectedSyncMode === "since_last" ? "is-selected" : ""}`}>
                <input
                  type="radio"
                  name="jira-sync-mode"
                  value="since_last"
                  checked={selectedSyncMode === "since_last"}
                  onChange={() => setSelectedSyncMode("since_last")}
                />
                <span>
                  <strong>Sync Since Last Timestamp</strong>
                  <small>Pull issues updated since the previous sync timestamp.</small>
                </span>
              </label>

              <label class={`tb-sync-option ${selectedSyncMode === "full" ? "is-selected" : ""}`}>
                <input
                  type="radio"
                  name="jira-sync-mode"
                  value="full"
                  checked={selectedSyncMode === "full"}
                  onChange={() => setSelectedSyncMode("full")}
                />
                <span>
                  <strong>Full Sync</strong>
                  <small>Download the entire configured board dataset.</small>
                </span>
              </label>

              <label class={`tb-sync-option ${selectedSyncMode === "since_date" ? "is-selected" : ""}`}>
                <input
                  type="radio"
                  name="jira-sync-mode"
                  value="since_date"
                  checked={selectedSyncMode === "since_date"}
                  onChange={() => setSelectedSyncMode("since_date")}
                />
                <span>
                  <strong>Sync Since Specific Date</strong>
                  <small>Pull issues updated on or after a selected UTC date.</small>
                </span>
              </label>
            </div>

            {selectedSyncMode === "since_date" ? (
              <label class="tb-sync-date-field">
                <span>Start date (UTC)</span>
                <input
                  type="date"
                  value={selectedSinceDate}
                  max={todayLocalDate}
                  onInput={(event) => setSelectedSinceDate((event.currentTarget as HTMLInputElement).value)}
                />
              </label>
            ) : null}

            <p class="tb-muted-note">
              Last synced: {jiraLastSyncedText}. If no previous sync exists, incremental mode falls back to full sync.
            </p>

            <footer class="tb-modal-actions">
              <button type="button" class="tb-btn" onClick={() => setIsSyncOptionsOpen(false)}>
                Cancel
              </button>
              <button
                type="button"
                class="tb-btn tb-btn-primary"
                onClick={() => {
                  if (selectedSyncMode === "since_date" && !selectedSinceDate) {
                    setSyncError("Please select a start date for date-based sync.");
                    return;
                  }
                  triggerJiraSync(
                    selectedSyncMode,
                    selectedSyncMode === "since_date" ? selectedSinceDate : undefined,
                  ).catch(() => {
                    // triggerJiraSync updates local state.
                  });
                }}
              >
                Start Sync
              </button>
            </footer>
          </div>
        </div>
      ) : null}

      {isHistoryOpen ? (
        <div class="tb-modal-layer" role="dialog" aria-modal="true" aria-label="JIRA Sync History">
          <div class="tb-modal-backdrop" onClick={() => setIsHistoryOpen(false)} />
          <div class="tb-modal tb-modal-history">
            <header class="tb-modal-head">
              <h3>JIRA Sync History</h3>
              <div class="tb-action-row">
                <button type="button" class="tb-btn tb-btn-sm" onClick={() => loadJiraSyncHistory()}>
                  Refresh
                </button>
                <button type="button" class="tb-btn tb-btn-sm" onClick={() => setIsHistoryOpen(false)}>
                  Close
                </button>
              </div>
            </header>

            {historyError ? <p class="tb-error-note">Failed to load history: {historyError}</p> : null}
            {historyLoading ? <p class="tb-muted-note">Loading sync history...</p> : null}

            <div class="tb-sync-history-wrap">
              <table class="tb-sync-history-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Board</th>
                    <th>Mode</th>
                    <th>Sprints</th>
                    <th>Issues</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {jiraSyncHistory.map((entry) => (
                    <tr key={entry.id}>
                      <td>{formatTimestamp(entry.finishedAt ?? entry.startedAt)}</td>
                      <td>{entry.boardName ?? (entry.boardId ? `Board ${entry.boardId}` : "-")}</td>
                      <td>{formatSyncMode(entry.syncMode, entry.requestedSince)}</td>
                      <td>{entry.sprintsSynced}</td>
                      <td>{entry.issuesSynced}</td>
                      <td>{entry.status}</td>
                    </tr>
                  ))}
                  {!historyLoading && jiraSyncHistory.length === 0 ? (
                    <tr>
                      <td colSpan={6}>No sync history available yet.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}

      {pendingLookupDelete ? (
        <div class="tb-modal-layer" role="dialog" aria-modal="true" aria-label="Confirm Metadata Delete">
          <div
            class="tb-modal-backdrop"
            onClick={() => {
              if (!lookupDeleteLoading) {
                setPendingLookupDelete(null);
              }
            }}
          />
          <div class="tb-modal">
            <header class="tb-modal-head">
              <h3>{pendingLookupDelete.type === "group" ? "Delete Epic Group" : "Delete Work Type"}</h3>
              <button
                type="button"
                class="tb-btn tb-btn-sm"
                onClick={() => setPendingLookupDelete(null)}
                disabled={lookupDeleteLoading}
              >
                Close
              </button>
            </header>

            <p class="tb-muted-note">
              Are you sure you want to delete <strong>{pendingLookupDelete.name}</strong>?
            </p>
            <p class="tb-muted-note">
              This change impacts all epic metadata configuration forms that reference this value.
            </p>

            <footer class="tb-modal-actions">
              <button
                type="button"
                class="tb-btn"
                onClick={() => setPendingLookupDelete(null)}
                disabled={lookupDeleteLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                class="tb-btn tb-btn-danger"
                onClick={() => confirmLookupDelete()}
                disabled={lookupDeleteLoading}
              >
                {lookupDeleteLoading ? "Deleting..." : "Delete"}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </div>
  );
}
