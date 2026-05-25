import { render, screen, waitFor } from "@testing-library/preact";
import { SecurityScreen } from "../../src/components/content/screens/SecurityScreen";
import { setupFetchMock } from "../utils/fetchMock";

describe("SecurityScreen", () => {
  it("renders security audit dashboard sourced from Jenkins", async () => {
    setupFetchMock({
      "/api/security/audit": {
        source: "jenkins_security_audit",
        generatedAt: "2026-05-25T03:00:00Z",
        pipeline: {
          jobName: "blade-runners/reviews/reviews-security-audit-pipeline",
          buildNumber: "807",
          buildUrl: "https://jenkins.example.com/job/security-audit/807/",
          status: "FAILED",
          startedAt: "2026-05-25T01:18:37Z",
          durationMillis: 428097,
          trivyArtifactName: "reviews_9fa4ae3c7_20262505012408.json",
        },
        summary: {
          totalFindings: 4,
          failedFindings: 3,
          skippedFindings: 1,
          severityCounts: { critical: 0, high: 1, medium: 3, low: 0, unknown: 0 },
          failedLayerCount: 2,
          passedLayerCount: 2,
          failedLayers: ["Backend", "Trivy Scan"],
          passedLayers: ["Frontend", "UI"],
        },
        layers: [
          {
            name: "Backend",
            stageStatus: "SUCCESS",
            durationMillis: 79157,
            findingCount: 1,
            failedFindingCount: 1,
            skippedFindingCount: 0,
            severityCounts: { critical: 0, high: 0, medium: 1, low: 0, unknown: 0 },
          },
          {
            name: "Frontend",
            stageStatus: "SUCCESS",
            durationMillis: 12337,
            findingCount: 0,
            failedFindingCount: 0,
            skippedFindingCount: 0,
            severityCounts: { critical: 0, high: 0, medium: 0, low: 0, unknown: 0 },
          },
          {
            name: "Trivy Scan",
            stageStatus: "FAILED",
            durationMillis: 95994,
            findingCount: 3,
            failedFindingCount: 3,
            skippedFindingCount: 0,
            severityCounts: { critical: 0, high: 1, medium: 2, low: 0, unknown: 0 },
          },
          {
            name: "UI",
            stageStatus: "SUCCESS",
            durationMillis: 33178,
            findingCount: 0,
            failedFindingCount: 0,
            skippedFindingCount: 0,
            severityCounts: { critical: 0, high: 0, medium: 0, low: 0, unknown: 0 },
          },
        ],
        findings: [
          {
            layer: "Trivy Scan",
            id: "CVE-2026-33416",
            severity: "HIGH",
            packageName: "libpng",
            installedVersion: "2:1.6.37-12.el9_7.3",
            fixedVersion: "2:1.6.37-12.el9_7.4",
            target: "reviews:9fa4ae3c7",
            title: "Arbitrary code execution due to use-after-free vulnerability",
            status: "FAILED",
            jiraCard: {
              issueKey: "SEC-123",
              summary: "Track CVE-2026-33416",
              status: "In Progress",
              statusCategory: "In Progress",
              issueUrl: "https://jira.example.com/browse/SEC-123",
            },
          },
          {
            layer: "Backend",
            id: "CVE-2026-45205",
            severity: "MEDIUM",
            packageName: "org.apache.commons/commons-configuration2",
            installedVersion: "2.11.0",
            fixedVersion: null,
            target: "commons-configuration2-2.11.0.jar",
            title: "Uncontrolled Recursion vulnerability in Apache Commons.",
            status: "FAILED",
            jiraCard: null,
            jiraCreateUrl: "https://jira.example.com/secure/CreateIssueDetails!init.jspa?pid=19824&issuetype=7&summary=Remediate%20Medium%20severity%20Backend%20vulnerability%20CVE-2026-45205&assignee=-1",
          },
        ],
        trend: [
          {
            buildNumber: 803,
            buildUrl: "https://jenkins.example.com/job/security-audit/803/",
            status: "FAILURE",
            startedAt: "2026-05-24T21:18:37Z",
            totalFindings: 2,
            severityCounts: { critical: 0, high: 0, medium: 2, low: 0, unknown: 0 },
          },
          {
            buildNumber: 804,
            buildUrl: "https://jenkins.example.com/job/security-audit/804/",
            status: "FAILURE",
            startedAt: "2026-05-24T22:18:37Z",
            totalFindings: 3,
            severityCounts: { critical: 0, high: 1, medium: 2, low: 0, unknown: 0 },
          },
          {
            buildNumber: 805,
            buildUrl: "https://jenkins.example.com/job/security-audit/805/",
            status: "FAILURE",
            startedAt: "2026-05-24T23:18:37Z",
            totalFindings: 1,
            severityCounts: { critical: 0, high: 0, medium: 1, low: 0, unknown: 0 },
          },
          {
            buildNumber: 806,
            buildUrl: "https://jenkins.example.com/job/security-audit/806/",
            status: "FAILURE",
            startedAt: "2026-05-25T00:18:37Z",
            totalFindings: 3,
            severityCounts: { critical: 0, high: 1, medium: 2, low: 0, unknown: 0 },
          },
          {
            buildNumber: 807,
            buildUrl: "https://jenkins.example.com/job/security-audit/807/",
            status: "FAILURE",
            startedAt: "2026-05-25T01:18:37Z",
            totalFindings: 4,
            severityCounts: { critical: 0, high: 1, medium: 3, low: 0, unknown: 0 },
          },
        ],
      },
    });

    render(<SecurityScreen />);

    expect(screen.getByRole("heading", { name: "Security Audit Dashboard" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Security Layers" })).toBeInTheDocument();
    expect(await screen.findByText("CVE-2026-33416")).toBeInTheDocument();
    expect(screen.getByText("libpng")).toBeInTheDocument();
    expect(screen.getByText("CVE-2026-45205")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Build: 807")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "5-Run Vulnerability Trend" })).toBeInTheDocument();
      expect(screen.getByText("+1 from previous run")).toBeInTheDocument();
      expect(screen.getByText("#807")).toBeInTheDocument();
      expect(screen.getByText("Layers passing")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Open Jenkins Build" })).toHaveAttribute(
        "href",
        "https://jenkins.example.com/job/security-audit/807/",
      );
      expect(screen.getByRole("link", { name: /SEC-123/ })).toHaveAttribute(
        "href",
        "https://jira.example.com/browse/SEC-123",
      );
      expect(screen.getByRole("link", { name: /Create ticket/ })).toHaveAttribute(
        "href",
        expect.stringContaining("assignee=-1"),
      );
      expect(screen.getByRole("table", { name: "Security vulnerability findings" })).toBeInTheDocument();
    });
  });
});
