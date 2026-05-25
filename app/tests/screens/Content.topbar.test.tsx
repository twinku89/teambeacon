import { fireEvent, render, screen } from "@testing-library/preact";
import { vi } from "vitest";

const mockedContentState = vi.hoisted(() => {
  const trendWindowOptions = [1, 2, 3, 4, 6, 8, 10, 12] as const;

  return {
    trendWindowOptions,
    openInitiativesConfigureEvent: "teambeacon:initiatives-open-configure",
    openInitiativesReportingPeriodEvent: "teambeacon:initiatives-open-reporting-period",
    openTeamInsightsSettingsEvent: "teambeacon:team-insights-open-settings",
    teamInsightsTrendWindowChangeEvent: "teambeacon:team-insights-trend-window-change",
    teamInsightsTrendWindowSyncEvent: "teambeacon:team-insights-trend-window-sync",
    openTeamDashboardReportingPeriodEvent: "teambeacon:team-dashboard-open-reporting-period",
    openTeamDashboardInitiativeConfigEvent: "teambeacon:team-dashboard-open-initiative-config",
    exportTeamDashboardHtmlEvent: "teambeacon:team-dashboard-export-html",
    formatTrendWindowLabel(value: number): string {
      if (value === 1) return "1 sprint";
      return `Last ${value} sprints`;
    },
    normalizeTrendWindow(value: number): number {
      return trendWindowOptions.includes(value as typeof trendWindowOptions[number]) ? value : 12;
    },
  };
});

vi.mock("../../src/components/content/screens/TeamInsightsScreen", async () => {
  const { useEffect, useState } = await import("preact/hooks");

  return {
    OPEN_TEAM_INSIGHTS_SETTINGS_EVENT: mockedContentState.openTeamInsightsSettingsEvent,
    TEAM_INSIGHTS_TREND_WINDOW_CHANGE_EVENT: mockedContentState.teamInsightsTrendWindowChangeEvent,
    TEAM_INSIGHTS_TREND_WINDOW_SYNC_EVENT: mockedContentState.teamInsightsTrendWindowSyncEvent,
    TREND_WINDOW_OPTIONS: mockedContentState.trendWindowOptions,
    formatTrendWindowLabel: mockedContentState.formatTrendWindowLabel,
    normalizeTrendWindow: mockedContentState.normalizeTrendWindow,
    TeamInsightsScreen: function TeamInsightsScreen() {
      const [trendWindow, setTrendWindow] = useState(12);
      const [isSettingsOpen, setIsSettingsOpen] = useState(false);

      useEffect(() => {
        const handleTrendWindowChange = (event: Event) => {
          const detail = (event as CustomEvent<{ trendWindow?: number }>).detail;
          const requestedValue = Number.parseInt(String(detail?.trendWindow ?? ""), 10);
          if (Number.isNaN(requestedValue)) return;
          setTrendWindow(mockedContentState.normalizeTrendWindow(requestedValue));
        };
        const handleSettingsOpen = () => {
          setIsSettingsOpen(true);
        };

        window.addEventListener(mockedContentState.teamInsightsTrendWindowChangeEvent, handleTrendWindowChange as EventListener);
        window.addEventListener(mockedContentState.openTeamInsightsSettingsEvent, handleSettingsOpen);
        return () => {
          window.removeEventListener(mockedContentState.teamInsightsTrendWindowChangeEvent, handleTrendWindowChange as EventListener);
          window.removeEventListener(mockedContentState.openTeamInsightsSettingsEvent, handleSettingsOpen);
        };
      }, []);

      return (
        <section>
          <h3>{`Cards in Selected Window (${mockedContentState.formatTrendWindowLabel(trendWindow)})`}</h3>
          {isSettingsOpen ? (
            <div role="dialog" aria-label="Team Insights Settings">
              <button type="button" onClick={() => setIsSettingsOpen(false)}>
                Close
              </button>
            </div>
          ) : null}
        </section>
      );
    },
  };
});

vi.mock("../../src/components/content/screens/TeamDashboardScreen", async () => {
  const { useEffect, useState } = await import("preact/hooks");

  return {
    OPEN_TEAM_DASHBOARD_REPORTING_PERIOD_EVENT: mockedContentState.openTeamDashboardReportingPeriodEvent,
    OPEN_TEAM_DASHBOARD_INITIATIVE_CONFIG_EVENT: mockedContentState.openTeamDashboardInitiativeConfigEvent,
    EXPORT_TEAM_DASHBOARD_HTML_EVENT: mockedContentState.exportTeamDashboardHtmlEvent,
    TeamDashboardScreen: function TeamDashboardScreen() {
      const [isReportingOpen, setIsReportingOpen] = useState(false);
      const [isInitiativesOpen, setIsInitiativesOpen] = useState(false);
      const [exportCount, setExportCount] = useState(0);

      useEffect(() => {
        const handleReportingOpen = () => {
          setIsReportingOpen(true);
        };
        const handleInitiativesOpen = () => {
          setIsInitiativesOpen(true);
        };
        const handleExport = () => {
          setExportCount((current) => current + 1);
        };

        window.addEventListener(mockedContentState.openTeamDashboardReportingPeriodEvent, handleReportingOpen);
        window.addEventListener(mockedContentState.openTeamDashboardInitiativeConfigEvent, handleInitiativesOpen);
        window.addEventListener(mockedContentState.exportTeamDashboardHtmlEvent, handleExport);
        return () => {
          window.removeEventListener(mockedContentState.openTeamDashboardReportingPeriodEvent, handleReportingOpen);
          window.removeEventListener(mockedContentState.openTeamDashboardInitiativeConfigEvent, handleInitiativesOpen);
          window.removeEventListener(mockedContentState.exportTeamDashboardHtmlEvent, handleExport);
        };
      }, []);

      return (
        <section>
          <h3>Executive Summary</h3>
          <p>{`Exports: ${exportCount}`}</p>
          {isReportingOpen ? <div role="dialog" aria-label="Configure Reporting Period"></div> : null}
          {isInitiativesOpen ? <div role="dialog" aria-label="Configure Initiative Epics"></div> : null}
        </section>
      );
    },
  };
});

vi.mock("../../src/components/content/screens/InitiativesScreen", async () => {
  const { useEffect, useState } = await import("preact/hooks");

  return {
    OPEN_INITIATIVES_CONFIGURE_EVENT: mockedContentState.openInitiativesConfigureEvent,
    OPEN_INITIATIVES_REPORTING_PERIOD_EVENT: mockedContentState.openInitiativesReportingPeriodEvent,
    InitiativesScreen: function InitiativesScreen() {
      const [isReportingOpen, setIsReportingOpen] = useState(false);
      const [isConfigureOpen, setIsConfigureOpen] = useState(false);

      useEffect(() => {
        const handleReportingOpen = () => {
          setIsReportingOpen(true);
        };
        const handleConfigureOpen = () => {
          setIsConfigureOpen(true);
        };

        window.addEventListener(mockedContentState.openInitiativesReportingPeriodEvent, handleReportingOpen);
        window.addEventListener(mockedContentState.openInitiativesConfigureEvent, handleConfigureOpen);
        return () => {
          window.removeEventListener(mockedContentState.openInitiativesReportingPeriodEvent, handleReportingOpen);
          window.removeEventListener(mockedContentState.openInitiativesConfigureEvent, handleConfigureOpen);
        };
      }, []);

      return (
        <section>
          <p>Initiatives stub</p>
          {isReportingOpen ? <div role="dialog" aria-label="Configure Reporting Period"></div> : null}
          {isConfigureOpen ? <div role="dialog" aria-label="Configure Epic Metadata"></div> : null}
        </section>
      );
    },
  };
});

vi.mock("../../src/components/content/screens/IntegrationsScreen", () => ({
  IntegrationsScreen: function IntegrationsScreen() {
    return <p>Integrations stub</p>;
  },
}));

vi.mock("../../src/components/content/screens/NewsDashboardScreen", () => ({
  NewsDashboardScreen: function NewsDashboardScreen() {
    return <p>Daily briefing stub</p>;
  },
}));

vi.mock("../../src/components/content/screens/SprintBoardScreen", () => ({
  SprintBoardScreen: function SprintBoardScreen() {
    return <p>Sprint board stub</p>;
  },
}));

vi.mock("../../src/components/content/screens/SecurityScreen", () => ({
  SecurityScreen: function SecurityScreen() {
    return <p>Security stub</p>;
  },
}));

vi.mock("../../src/components/content/screens/IncidentResponseScreen", () => ({
  IncidentResponseScreen: function IncidentResponseScreen() {
    return <p>Incident response stub</p>;
  },
}));

vi.mock("../../src/components/content/screens/ReleasesScreen", () => ({
  ReleasesScreen: function ReleasesScreen() {
    return <p>Releases stub</p>;
  },
}));

import { Content } from "../../src/components/content";
import { TEAM_INSIGHTS_TREND_WINDOW_SYNC_EVENT as SYNC_EVENT_NAME } from "../../src/components/content/screens/TeamInsightsScreen";

describe("Content topbar controls", () => {
  it("supports trend-window keyboard controls, sync updates, and settings events", () => {
    render(<Content appName="TeamBeacon" />);

    fireEvent.click(screen.getByRole("button", { name: /Team Insights/ }));

    const trendWindowSelect = screen.getByRole("combobox", { name: "Trend Window" });
    expect(trendWindowSelect).toHaveTextContent("Last 12 sprints");

    fireEvent.click(trendWindowSelect);
    expect(screen.getByRole("listbox", { name: "Trend Window options" })).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("listbox", { name: "Trend Window options" })).not.toBeInTheDocument();

    fireEvent.keyDown(trendWindowSelect, { key: "ArrowDown" });
    expect(screen.getByRole("listbox", { name: "Trend Window options" })).toBeInTheDocument();

    trendWindowSelect.focus();
    fireEvent.keyDown(trendWindowSelect, { key: "ArrowUp" });
    expect(screen.getByRole("option", { name: "Last 10 sprints" })).toHaveFocus();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("listbox", { name: "Trend Window options" })).not.toBeInTheDocument();
    expect(trendWindowSelect).toHaveFocus();

    fireEvent.keyDown(trendWindowSelect, { key: "Enter" });
    const optionTwelve = screen.getByRole("option", { name: "Last 12 sprints" });
    fireEvent.keyDown(optionTwelve, { key: "ArrowUp" });
    expect(screen.getByRole("option", { name: "Last 10 sprints" })).toHaveFocus();

    const optionTen = screen.getByRole("option", { name: "Last 10 sprints" });
    fireEvent.keyDown(optionTen, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: "Last 12 sprints" })).toHaveFocus();

    fireEvent.keyDown(screen.getByRole("option", { name: "Last 12 sprints" }), { key: "Home" });
    expect(screen.getByRole("option", { name: "1 sprint" })).toHaveFocus();

    fireEvent.keyDown(screen.getByRole("option", { name: "1 sprint" }), { key: "End" });
    expect(screen.getByRole("option", { name: "Last 12 sprints" })).toHaveFocus();

    fireEvent.keyDown(screen.getByRole("option", { name: "Last 6 sprints" }), { key: " " });
    expect(screen.queryByRole("listbox", { name: "Trend Window options" })).not.toBeInTheDocument();
    expect(trendWindowSelect).toHaveTextContent("Last 6 sprints");
    expect(screen.getByRole("heading", { name: "Cards in Selected Window (Last 6 sprints)" })).toBeInTheDocument();

    fireEvent.keyDown(trendWindowSelect, { key: " " });
    fireEvent.keyDown(screen.getByRole("option", { name: "Last 6 sprints" }), { key: "Enter" });
    expect(screen.queryByRole("listbox", { name: "Trend Window options" })).not.toBeInTheDocument();
    expect(trendWindowSelect).toHaveTextContent("Last 6 sprints");

    fireEvent(window, new CustomEvent(SYNC_EVENT_NAME, { detail: { trendWindow: "bad" } }));
    expect(trendWindowSelect).toHaveTextContent("Last 6 sprints");

    fireEvent(window, new CustomEvent(SYNC_EVENT_NAME, { detail: { trendWindow: 1 } }));
    expect(trendWindowSelect).toHaveTextContent("1 sprint");

    fireEvent.click(screen.getByRole("button", { name: "Team Insights Settings" }));
    expect(screen.getByRole("dialog", { name: "Team Insights Settings" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Team Insights Settings" })).not.toBeInTheDocument();
  });

  it("renders active screens and keeps dormant dashboards out of navigation", () => {
    render(<Content appName="TeamBeacon" />);

    expect(screen.getByText("Daily briefing stub")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Initiative Insights/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Team Dashboard/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Sprint Insights/ }));
    expect(screen.getByText("Sprint board stub")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Operations Insights/ }));
    expect(screen.getByText("Incident response stub")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Release Insights/ }));
    expect(screen.getByText("Releases stub")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Security Insights/ }));
    expect(screen.getByText("Security stub")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Settings/ }));
    expect(screen.getByText("Integrations stub")).toBeInTheDocument();
  });
});
