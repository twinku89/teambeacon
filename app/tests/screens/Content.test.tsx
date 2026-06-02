import { fireEvent, render, screen } from "@testing-library/preact";
import { within } from "@testing-library/dom";
import { beforeEach } from "vitest";
import { Content } from "../../src/components/content";
import { setupFetchMock } from "../utils/fetchMock";

const ACTIVE_SCREEN_PREFERENCE_KEY = "teambeacon.activeScreen";

function setupContentShellFetchMock() {
  setupFetchMock({
    "/api/news/dashboard": {
      source: "rss",
      generatedAt: "2026-05-25T07:00:00+00:00",
      timezone: "Australia/Melbourne",
      categories: [],
      error: null,
    },
    "/api/security/audit": {
      source: "jenkins_security_audit",
      generatedAt: "2026-05-28T00:18:18+00:00",
      cached: false,
      pipeline: {
        buildNumber: "810",
        status: "FAILED",
        startedAt: "2026-05-27T20:15:01.086000+00:00",
        durationMillis: 37871,
      },
      summary: {
        totalFindings: 1,
        failedFindings: 1,
        skippedFindings: 0,
        severityCounts: { critical: 0, high: 1, medium: 0, low: 0, unknown: 0 },
        failedLayerCount: 1,
        passedLayerCount: 3,
      },
      layers: [
        {
          name: "Backend",
          stageStatus: "SUCCESS",
          durationMillis: 1000,
          findingCount: 0,
          failedFindingCount: 0,
          skippedFindingCount: 0,
          severityCounts: { critical: 0, high: 0, medium: 0, low: 0, unknown: 0 },
        },
        {
          name: "Frontend",
          stageStatus: "SUCCESS",
          durationMillis: 1000,
          findingCount: 0,
          failedFindingCount: 0,
          skippedFindingCount: 0,
          severityCounts: { critical: 0, high: 0, medium: 0, low: 0, unknown: 0 },
        },
        {
          name: "Trivy Scan",
          stageStatus: "SUCCESS",
          durationMillis: 1000,
          findingCount: 0,
          failedFindingCount: 0,
          skippedFindingCount: 0,
          severityCounts: { critical: 0, high: 0, medium: 0, low: 0, unknown: 0 },
        },
        {
          name: "UI",
          stageStatus: "FAILED",
          durationMillis: 37871,
          findingCount: 1,
          failedFindingCount: 1,
          skippedFindingCount: 0,
          severityCounts: { critical: 0, high: 1, medium: 0, low: 0, unknown: 0 },
        },
      ],
      findings: [],
      trend: [],
      error: null,
    },
  });
}

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("Content", () => {
  it("opens the dashboard from the URL hash on browser refresh", async () => {
    setupContentShellFetchMock();
    window.history.replaceState(null, "", "/#security");

    render(<Content appName="TeamBeacon" />);

    expect(await screen.findByRole("heading", { name: "Security Insights" })).toBeInTheDocument();
    expect(window.localStorage.getItem(ACTIVE_SCREEN_PREFERENCE_KEY)).toBe("security");
  });

  it("persists the selected dashboard to the URL and preferences", async () => {
    setupContentShellFetchMock();

    render(<Content appName="TeamBeacon" />);

    fireEvent.click(screen.getByRole("button", { name: /Security Insights/ }));

    expect(await screen.findByRole("heading", { name: "Security Insights" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#security");
    expect(window.localStorage.getItem(ACTIVE_SCREEN_PREFERENCE_KEY)).toBe("security");
  });

  it("renders construction markers only for static screens in sidebar", async () => {
    setupFetchMock({
      "/api/integrations/jira/status": {
        source: "jira",
        connected: true,
        checkedAt: "2026-03-30T09:15:00Z",
        config: {
          baseUrl: "https://jira.example.com",
          projectKey: "CEG",
          boardId: 42,
          storyPointsField: "customfield_10016",
          epicLinkField: "customfield_10014",
          sprintFields: ["customfield_10020"],
        },
        checks: [
          { name: "auth", ok: true, detail: "reachable" },
          { name: "project", ok: true, detail: "resolved" },
        ],
      },
      "/api/integrations/ai/status": {
        source: "ollama",
        provider: "ollama",
        configuredProvider: "ollama",
        connected: true,
        checkedAt: "2026-03-30T09:15:00Z",
        config: {
          baseUrl: "http://127.0.0.1:11434",
          modelId: "gemma4:e2b",
        },
        checks: [
          { name: "ollama_api", ok: true, detail: "reachable" },
          { name: "configured_model", ok: true, detail: "loaded" },
        ],
      },
      "/api/integrations/confluence/status": {
        source: "confluence",
        connected: true,
        checkedAt: "2026-03-30T09:15:00Z",
        config: {
          baseUrl: "https://gbuconfluence.oraclecorp.com",
          authMode: "pat_bearer",
        },
        checks: [
          { name: "auth", ok: true, detail: "reachable" },
          { name: "space_query", ok: true, detail: "responding" },
        ],
      },
      "/api/team/insights": {
        source: "local",
        generatedAt: "2026-04-10T09:00:00Z",
        windowSize: 6,
        metrics: {
          avgCommittedStoryPoints: 92,
          avgCompletedStoryPoints: 81,
          completionRatioPercent: 88.04,
          carryoverPercent: 11.96,
          avgCycleTimeDays: 4.1,
          cycleTimeStdDevDays: 2.7,
          medianCycleTimeDays: 3.4,
        },
        trend: [
          {
            sprintId: 4101,
            sprintName: "Sprint 41 (Q4 FY26)",
            state: "closed",
            startDate: "2026-03-18T00:00:00+00:00",
            endDate: "2026-04-01T00:00:00+00:00",
            committedStoryPoints: 88,
            completedStoryPoints: 80,
            avgCycleTimeDays: 4.7,
            completionRatioPercent: 90.91,
            carryoverPercent: 9.09,
          },
          {
            sprintId: 4102,
            sprintName: "Sprint 42 (Q4 FY26)",
            state: "active",
            startDate: "2026-04-02T00:00:00+00:00",
            endDate: "2026-04-15T00:00:00+00:00",
            committedStoryPoints: 96,
            completedStoryPoints: 82,
            avgCycleTimeDays: 3.9,
            completionRatioPercent: 85.42,
            carryoverPercent: 14.58,
          },
        ],
        statusCycleTime: {
          trackedIssues: 13,
          totalDays: 29.6,
          rows: [
            {
              status: "In Progress",
              issueCount: 13,
              avgDays: 1.5,
              medianDays: 1.2,
              p85Days: 2.4,
              maxDays: 4.8,
              totalDays: 19.4,
              percentOfCycleTime: 65.54,
            },
          ],
        },
        workMix: {
          sprintId: 4102,
          sprintName: "Sprint 42",
          totalIssues: 20,
          slices: [
            { label: "Feature", count: 12, percent: 60 },
            { label: "Ops", count: 5, percent: 25 },
            { label: "Security", count: 3, percent: 15 },
          ],
        },
        summary: "Work mix is currently Feature 60%, Ops 25%, Security 15%.",
        error: null,
      },
      "/api/metadata/epics/summary": {
        epics: [
          {
            epicKey: "CEG-101",
            epicName: "Payment Orchestration",
            completedCards: 7,
            totalCards: 10,
            completionPercent: 70,
            completedInPeriod: 2,
            deltaPercentInPeriod: 5,
            groups: [{ id: 1, name: "Core Platform" }],
            workTypes: [{ id: 2, name: "Feature" }],
            successCriteria: ["Latency under 120ms"],
            timelineEnabled: true,
            timelineStartDate: "2026-03-01",
            targetCompletionDate: "2026-04-15",
            insightComment: "Delivery is aligned with sprint capacity.",
          },
        ],
        reportingPeriod: {
          startDate: "2026-03-23",
          endDate: "2026-03-30",
          days: 8,
          timezone: "Australia/Melbourne",
        },
      },
      "/api/metadata/lookup": {
        groups: [{ id: 1, name: "Core Platform" }],
        workTypes: [{ id: 2, name: "Feature" }],
      },
      "/api/news/dashboard": {
        source: "rss",
        generatedAt: "2026-05-25T07:00:00+00:00",
        timezone: "Australia/Melbourne",
        categories: [
          {
            id: "world",
            label: "World News",
            description: "Global headlines to start the day.",
            articles: [
              {
                id: "world-1",
                categoryId: "world",
                title: "World headline",
                source: "BBC News",
                url: "https://example.com/world",
                publishedAt: "2026-05-25T06:30:00+00:00",
                summary: "Global update.",
              },
            ],
            errors: [],
          },
          {
            id: "manchesterUnited",
            label: "Manchester United",
            description: "A dedicated United watchlist.",
            articles: [],
            errors: [],
          },
        ],
        bookOfTheDay: {
          label: "Book of the Day",
          title: "Atomic Habits",
          author: "James Clear",
          summary: "A practical habit-building book.",
          whyRead: "Useful for steady routines.",
          readingTimeMinutes: 5,
          detailedSummary: "A longer practical guide to habit systems.",
          keyIdeas: ["Focus on systems, not only goals."],
          tryToday: "Start with two minutes.",
        },
        trainingTip: {
          categoryId: "dogTraining",
          label: "Dog Training",
          description: "Training tips for this 9-month-old working-line GSD, tuned for adolescent working-line foundations.",
          title: "Engagement check-ins",
          skillName: "Voluntary check-in",
          skillArea: "Life skills",
          focus: "Teach your adolescent working-line GSD that checking in is always worth it.",
          steps: ["Reward calm check-ins.", "Resume walking after each reward."],
          note: "Keep sessions short, reward-based, and matched to health, energy, and recovery.",
        },
        error: null,
      },
    });

    render(<Content appName="TeamBeacon" />);

    expect(await screen.findByRole("heading", { name: "Daily Briefing", level: 2 })).toBeInTheDocument();
    expect(await screen.findByText("World headline")).toBeInTheDocument();
    expect(screen.getByText("Atomic Habits")).toBeInTheDocument();
    expect(screen.getByText("Engagement check-ins")).toBeInTheDocument();
    expect(screen.getByText("Illuminating Engineering Insights")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Integrations Settings" })).not.toBeInTheDocument();

    const nav = screen.getByRole("navigation");
    const orderedTitles = within(nav)
      .getAllByRole("button")
      .map((button) => button.querySelector(".tb-nav-title")?.textContent?.trim() ?? "");
    expect(orderedTitles).toEqual([
      "Daily Briefing",
      "Sprint Insights",
      "Team Insights",
      "Security Insights",
      "Operations Insights",
      "Release Insights",
      "Settings",
    ]);

    expect(screen.getByLabelText("Security Insights is under construction")).toBeInTheDocument();
    expect(screen.getByLabelText("Operations Insights is under construction")).toBeInTheDocument();

    expect(screen.getByText("World / AU / India / Books / Dog Training")).toBeInTheDocument();
    expect(screen.getByText("Overview / Progress / Scope Creep / Blockers")).toBeInTheDocument();
    expect(screen.getByText("Sprint Trend / Cycle Time")).toBeInTheDocument();
    expect(screen.getByText("Scan / Vulnerability Posture")).toBeInTheDocument();
    expect(screen.getByText("Incidents / DR / Observability")).toBeInTheDocument();
    expect(screen.getByText("Cycle Time / Readiness / Risk")).toBeInTheDocument();
    expect(screen.getByText("Connections / Metadata Configuration")).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: /Initiative Insights/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Team Dashboard/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Epic Config / Progress / RAG")).not.toBeInTheDocument();
    expect(screen.queryByText("Summary / Wins / Risks / Progress / Work Mix")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Daily Briefing is under construction")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Team Insights is under construction")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Settings is under construction")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Sprint Insights is under construction")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Release Insights is under construction")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Individual Insights/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Team Insights Settings" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Team Insights/ }));
    expect(await screen.findByRole("heading", { name: "Team Insights" })).toBeInTheDocument();
    const trendWindowSelect = screen.getByRole("combobox", { name: "Trend Window" });
    expect(trendWindowSelect).toHaveTextContent("Last 12 sprints");
    const teamSettingsButton = screen.getByRole("button", { name: "Team Insights Settings" });
    const teamTopbarActions = teamSettingsButton.closest(".tb-topbar-actions");
    expect(teamTopbarActions).not.toBeNull();
    expect(within(teamTopbarActions as HTMLElement).getByRole("combobox", { name: "Trend Window" })).toBeInTheDocument();
    fireEvent.click(trendWindowSelect);
    expect(screen.getByRole("listbox", { name: "Trend Window options" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: "Last 6 sprints" }));
    expect(trendWindowSelect).toHaveTextContent("Last 6 sprints");
    expect(await screen.findByRole("heading", { name: "Cards in Selected Window (Last 6 sprints)" })).toBeInTheDocument();
    fireEvent.click(teamSettingsButton);
    expect(await screen.findByRole("dialog", { name: "Team Insights Settings" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Team Insights Settings" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Security Insights/ }));
    expect(await screen.findByRole("heading", { name: "Security Insights" })).toBeInTheDocument();
    expect(screen.getByLabelText("Security Insights under construction")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Under construction" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Team Insights Settings" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Operations Insights/ }));
    expect(await screen.findByRole("heading", { name: "Operations Insights" })).toBeInTheDocument();
    expect(screen.getByLabelText("Operations Insights under construction")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Under construction" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Settings/ }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
  });
});
