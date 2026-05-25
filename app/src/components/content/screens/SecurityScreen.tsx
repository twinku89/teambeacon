import { h } from "preact";
import { useCallback, useEffect, useMemo, useState } from "preact/hooks";
import { fetchSecurityAudit, SecurityAuditFinding, SecurityAuditResponse } from "../../../lib/api";

const SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"] as const;

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatDuration(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "n/a";
  const totalSeconds = Math.round(value / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) return `${seconds}s`;
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

function severityClass(severity: string | null | undefined): string {
  const normalized = (severity ?? "unknown").toLowerCase();
  if (normalized === "critical" || normalized === "high") return "is-risk";
  if (normalized === "medium") return "is-warn";
  if (normalized === "low") return "is-good";
  return "is-neutral";
}

function statusClass(status: string | null | undefined): string {
  const normalized = (status ?? "").toLowerCase();
  if (normalized === "success" || normalized === "passed") return "is-good";
  if (normalized === "failed" || normalized === "failure") return "is-risk";
  if (normalized === "skipped" || normalized === "unstable") return "is-warn";
  return "is-neutral";
}

function valueToneClass(tone: string): string {
  if (tone === "is-risk") return "tb-value-risk";
  if (tone === "is-warn") return "tb-value-warn";
  if (tone === "is-good") return "tb-value-good";
  return "tb-value-warn";
}

function layerToneClass(layer: {
  stageStatus?: string | null;
  severityCounts: { critical: number; high: number; medium: number; low: number; unknown: number };
}): string {
  const normalizedStage = (layer.stageStatus ?? "").toUpperCase();
  const hasCriticalOrHigh = layer.severityCounts.critical > 0 || layer.severityCounts.high > 0;
  if (hasCriticalOrHigh || normalizedStage === "FAILED") return "tb-value-risk";
  if (layer.severityCounts.medium > 0) return "tb-value-warn";
  return "tb-value-good";
}

function findingSortValue(finding: SecurityAuditFinding): number {
  const index = SEVERITY_ORDER.indexOf((finding.severity ?? "UNKNOWN").toUpperCase() as typeof SEVERITY_ORDER[number]);
  return index === -1 ? SEVERITY_ORDER.length : index;
}

function formatTrendDelta(value: number | null): string {
  if (value === null) return "Waiting for previous run";
  if (value === 0) return "No change from previous run";
  return `${value > 0 ? "+" : ""}${value} from previous run`;
}

export function SecurityScreen() {
  const [audit, setAudit] = useState<SecurityAuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchSecurityAudit();
      setAudit(payload);
      setError(payload.error ?? null);
    } catch (err) {
      setAudit(null);
      setError(err instanceof Error ? err.message : "Unknown security audit failure.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAudit().catch(() => {
      // loadAudit updates local state.
    });
  }, [loadAudit]);

  const severityCounts = audit?.summary?.severityCounts;
  const totalFindings = audit?.summary?.totalFindings ?? 0;
  const failedFindings = audit?.summary?.failedFindings ?? 0;
  const skippedFindings = audit?.summary?.skippedFindings ?? 0;
  const failedLayerCount = audit?.summary?.failedLayerCount ?? 0;
  const passedLayerCount = audit?.summary?.passedLayerCount ?? 0;
  const vulnerabilityTrend = audit?.trend ?? [];
  const latestTrendPoint = vulnerabilityTrend[vulnerabilityTrend.length - 1];
  const previousTrendPoint = vulnerabilityTrend[vulnerabilityTrend.length - 2];
  const latestTrendFindings = latestTrendPoint?.totalFindings ?? totalFindings;
  const trendDelta = previousTrendPoint ? latestTrendFindings - previousTrendPoint.totalFindings : null;
  const trendMax = Math.max(1, ...vulnerabilityTrend.map((point) => point.totalFindings));

  const sortedFindings = useMemo(() => {
    return [...(audit?.findings ?? [])].sort((left, right) => {
      const severityDelta = findingSortValue(left) - findingSortValue(right);
      if (severityDelta !== 0) return severityDelta;
      return (left.id ?? "").localeCompare(right.id ?? "");
    });
  }, [audit?.findings]);

  const pipelineStatus = loading ? "Checking" : audit?.pipeline?.status ?? "Unknown";
  const pipelineTone = loading ? "is-neutral" : statusClass(audit?.pipeline?.status);

  return (
    <div class="tb-screen-grid">
      <section class="tb-panel">
        <header class="tb-panel-header">
          <div>
            <h3>Security Audit Dashboard</h3>
            <p class="tb-muted-note">Latest Jenkins security audit pipeline results across application and image checks.</p>
          </div>
          <div class="tb-action-row">
            {audit?.pipeline?.buildUrl ? (
              <a
                class="tb-btn tb-btn-sm"
                href={audit.pipeline.buildUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open Jenkins Build
              </a>
            ) : null}
            <button type="button" class="tb-btn tb-btn-primary" onClick={() => loadAudit()} disabled={loading}>
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </header>

        {error ? <p class="tb-error-note">Security audit error: {error}</p> : null}

        <div class="tb-metrics-grid tb-five-up">
          <article class="tb-metric-card">
            <h4>Pipeline Status</h4>
            <strong class={`tb-value ${valueToneClass(pipelineTone)}`}>
              {pipelineStatus}
            </strong>
            <p>Build: {audit?.pipeline?.buildNumber ?? "n/a"}</p>
            <p>Started: {formatDateTime(audit?.pipeline?.startedAt)}</p>
          </article>
          <article class="tb-metric-card">
            <h4>Open Findings</h4>
            <strong class={`tb-value ${failedFindings > 0 ? "tb-value-risk" : "tb-value-good"}`}>{failedFindings}</strong>
            <p>Total reported: {totalFindings}</p>
            <p>Skipped/waived: {skippedFindings}</p>
          </article>
          <article class="tb-metric-card">
            <h4>Severity Mix</h4>
            <strong class={`tb-value ${(severityCounts?.critical ?? 0) + (severityCounts?.high ?? 0) > 0 ? "tb-value-risk" : "tb-value-good"}`}>
              {(severityCounts?.critical ?? 0) + (severityCounts?.high ?? 0)}
            </strong>
            <p>Critical/High</p>
            <p>Medium: {severityCounts?.medium ?? 0}</p>
          </article>
          <article class="tb-metric-card">
            <h4>Layer Health</h4>
            <strong class={`tb-value ${failedLayerCount > 0 ? "tb-value-risk" : "tb-value-good"}`}>{passedLayerCount}/4</strong>
            <p>Layers passing</p>
            <p>Duration: {formatDuration(audit?.pipeline?.durationMillis)}</p>
          </article>
          <article class="tb-metric-card tb-security-trend-card">
            <h4>5-Run Vulnerability Trend</h4>
            <strong class={`tb-value ${latestTrendFindings > 0 ? "tb-value-warn" : "tb-value-good"}`}>
              {latestTrendFindings}
            </strong>
            <p>Latest run findings</p>
            <div class="tb-security-trend" aria-label="Last 5 pipeline vulnerability counts">
              {vulnerabilityTrend.length === 0 ? (
                <span class="tb-security-trend-empty">No trend data</span>
              ) : null}
              {vulnerabilityTrend.map((point) => {
                const height = Math.max(10, Math.round((point.totalFindings / trendMax) * 100));
                const buildLabel = point.buildNumber ?? "n/a";
                return (
                  <div
                    class="tb-security-trend-item"
                    key={`${buildLabel}-${point.startedAt ?? "run"}`}
                    title={`Build ${buildLabel}: ${point.totalFindings} findings`}
                  >
                    <span
                      class={`tb-security-trend-bar ${point.totalFindings > 0 ? "is-warn" : "is-good"}`}
                      style={{ height: `${height}%` }}
                    />
                    <span class="tb-security-trend-count">{point.totalFindings}</span>
                    <span class="tb-security-trend-build">#{buildLabel}</span>
                  </div>
                );
              })}
            </div>
            <p>{formatTrendDelta(trendDelta)}</p>
          </article>
        </div>
      </section>

      <section class="tb-panel">
        <header class="tb-panel-header">
          <div>
            <h3>Security Layers</h3>
            <p class="tb-muted-note">Backend, Frontend, Trivy Scan, and UI checks from the latest pipeline run.</p>
          </div>
        </header>

        <div class="tb-metrics-grid tb-four-up">
          {(audit?.layers ?? ["Backend", "Frontend", "Trivy Scan", "UI"].map((name) => ({
            name,
            stageStatus: loading ? "CHECKING" : "UNKNOWN",
            durationMillis: null,
            findingCount: 0,
            failedFindingCount: 0,
            skippedFindingCount: 0,
            severityCounts: { critical: 0, high: 0, medium: 0, low: 0, unknown: 0 },
          }))).map((layer) => (
            <article class="tb-metric-card" key={layer.name}>
              <h4>{layer.name}</h4>
              <strong class={`tb-value ${layerToneClass(layer)}`}>
                {layer.stageStatus}
              </strong>
              <p>Findings: {layer.findingCount}</p>
              <p>High: {layer.severityCounts.high}, Medium: {layer.severityCounts.medium}</p>
              <p>Duration: {formatDuration(layer.durationMillis)}</p>
            </article>
          ))}
        </div>
      </section>

      <section class="tb-panel">
        <header class="tb-panel-header">
          <div>
            <h3>Vulnerability Findings</h3>
            <p class="tb-muted-note">Dependency and container findings reported by the security audit pipeline.</p>
          </div>
        </header>

        <div class="tb-security-table-wrap">
          <table class="tb-security-table" aria-label="Security vulnerability findings">
            <thead>
              <tr>
                <th>Layer</th>
                <th>Severity</th>
                <th>ID</th>
                <th>Package</th>
                <th>Installed</th>
                <th>Jira Card</th>
              </tr>
            </thead>
            <tbody>
              {sortedFindings.length === 0 ? (
                <tr>
                  <td colSpan={6}>{loading ? "Loading security findings..." : "No vulnerabilities reported."}</td>
                </tr>
              ) : null}
              {sortedFindings.map((finding, index) => (
                <tr key={`${finding.layer}-${finding.id ?? "finding"}-${finding.packageName ?? "pkg"}-${index}`}>
                  <td>{finding.layer}</td>
                  <td>
                    <span class={`tb-status-pill ${severityClass(finding.severity)}`}>{finding.severity ?? "UNKNOWN"}</span>
                  </td>
                  <td>{finding.id ?? "n/a"}</td>
                  <td title={finding.title ?? undefined}>{finding.packageName ?? "n/a"}</td>
                  <td>{finding.installedVersion ?? "n/a"}</td>
                  <td>
                    {finding.jiraCard ? (
                      <a
                        class="tb-security-jira-card"
                        href={finding.jiraCard.issueUrl ?? undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={finding.jiraCard.summary}
                      >
                        <span>{finding.jiraCard.issueKey}</span>
                        <small>{finding.jiraCard.status}</small>
                      </a>
                    ) : finding.jiraCreateUrl ? (
                      <a
                        class="tb-security-jira-card"
                        href={finding.jiraCreateUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={`Create Jira card for ${finding.id ?? "vulnerability"}`}
                      >
                        <span>Create ticket</span>
                        <small>Unassigned</small>
                      </a>
                    ) : (
                      <span class="tb-muted-note">Not found</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
