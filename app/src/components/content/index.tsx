/**
 * @license
 * Copyright (c) 2014, 2026, Oracle and/or its affiliates.
 * Licensed under The Universal Permissive License (UPL), Version 1.0
 * as shown at https://oss.oracle.com/licenses/upl/
 * @ignore
 */
import { h } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { IncidentResponseScreen } from "./screens/IncidentResponseScreen";
import { IntegrationsScreen } from "./screens/IntegrationsScreen";
import { NewsDashboardScreen } from "./screens/NewsDashboardScreen";
import { ReleasesScreen } from "./screens/ReleasesScreen";
import { SecurityScreen } from "./screens/SecurityScreen";
import { SprintBoardScreen } from "./screens/SprintBoardScreen";
import {
  OPEN_TEAM_INSIGHTS_SETTINGS_EVENT,
  TEAM_INSIGHTS_TREND_WINDOW_CHANGE_EVENT,
  TEAM_INSIGHTS_TREND_WINDOW_SYNC_EVENT,
  TeamInsightsScreen,
  TREND_WINDOW_OPTIONS,
  formatTrendWindowLabel,
  normalizeTrendWindow,
} from "./screens/TeamInsightsScreen";

type ScreenId =
  | "integrations"
  | "news"
  | "team"
  | "sprint"
  | "security"
  | "incidents"
  | "releases";

type NavItem = {
  id: ScreenId;
  label: string;
  blurb: string;
  showConstruction: boolean;
};

type Props = {
  appName: string;
};

const NAV_ITEMS: NavItem[] = [
  { id: "news", label: "Daily Briefing", blurb: "World / AU / India / Books / Dog Training", showConstruction: false },
  { id: "sprint", label: "Sprint Insights", blurb: "Overview / Progress / Scope Creep / Blockers", showConstruction: false },
  { id: "team", label: "Team Insights", blurb: "Sprint Trend / Cycle Time", showConstruction: false },
  { id: "security", label: "Security Insights", blurb: "Scan / Vulnerability Posture", showConstruction: true },
  { id: "incidents", label: "Operations Insights", blurb: "Incidents / DR / Observability", showConstruction: true },
  { id: "releases", label: "Release Insights", blurb: "Cycle Time / Readiness / Risk", showConstruction: false },
  { id: "integrations", label: "Settings", blurb: "Connections / Metadata Configuration", showConstruction: false },
];

function screenTitle(id: ScreenId): string {
  const mapping: Record<ScreenId, string> = {
    integrations: "Settings",
    news: "Daily Briefing",
    team: "Team Insights",
    sprint: "Sprint Insights",
    security: "Security Insights",
    incidents: "Operations Insights",
    releases: "Release Insights",
  };
  return mapping[id];
}

function renderScreen(id: ScreenId) {
  switch (id) {
    case "integrations":
      return <IntegrationsScreen />;
    case "news":
      return <NewsDashboardScreen />;
    case "team":
      return <TeamInsightsScreen />;
    case "sprint":
      return <SprintBoardScreen />;
    case "security":
      return <SecurityScreen />;
    case "incidents":
      return <IncidentResponseScreen />;
    case "releases":
      return <ReleasesScreen />;
    default:
      return <IntegrationsScreen />;
  }
}

type TrendWindowDropdownProps = {
  value: number;
  onChange: (value: number) => void;
};

function TrendWindowDropdown({ value, onChange }: TrendWindowDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const optionRefs = useRef<Record<number, HTMLButtonElement | null>>({});

  const focusOption = (optionValue: number) => {
    optionRefs.current[optionValue]?.focus();
  };

  const focusOptionByOffset = (optionValue: number, offset: number) => {
    const currentIndex = TREND_WINDOW_OPTIONS.indexOf(optionValue as typeof TREND_WINDOW_OPTIONS[number]);
    if (currentIndex < 0) return;
    const nextIndex = Math.min(Math.max(currentIndex + offset, 0), TREND_WINDOW_OPTIONS.length - 1);
    focusOption(TREND_WINDOW_OPTIONS[nextIndex]);
  };

  const closeMenu = () => {
    setIsOpen(false);
  };

  const selectValue = (nextValue: number) => {
    const normalizedValue = normalizeTrendWindow(nextValue);
    if (normalizedValue !== value) {
      onChange(normalizedValue);
    }
    closeMenu();
    triggerRef.current?.focus();
  };

  useEffect(() => {
    if (!isOpen) return undefined;

    const handlePointerDown = (event: MouseEvent) => {
      if (dropdownRef.current?.contains(event.target as Node)) return;
      closeMenu();
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeMenu();
      triggerRef.current?.focus();
    };

    document.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    focusOption(value);
  }, [isOpen, value]);

  return (
    <div class="tb-topbar-trend-window">
      <span id="tb-trend-window-label">Trend Window</span>
      <div class="tb-topbar-trend-window-dropdown" ref={dropdownRef}>
        <button
          ref={triggerRef}
          type="button"
          class={`tb-topbar-trend-window-trigger${isOpen ? " is-open" : ""}`}
          role="combobox"
          aria-labelledby="tb-trend-window-label"
          aria-describedby="tb-trend-window-value"
          aria-expanded={isOpen ? "true" : "false"}
          aria-haspopup="listbox"
          aria-controls="tb-trend-window-listbox"
          onClick={() => setIsOpen((current) => !current)}
          onKeyDown={(event) => {
            switch (event.key) {
              case "ArrowDown":
                event.preventDefault();
                if (!isOpen) {
                  setIsOpen(true);
                  return;
                }
                focusOptionByOffset(value, 1);
                return;
              case "ArrowUp":
                event.preventDefault();
                if (!isOpen) {
                  setIsOpen(true);
                  return;
                }
                focusOptionByOffset(value, -1);
                return;
              case "Enter":
              case " ":
                event.preventDefault();
                if (!isOpen) {
                  setIsOpen(true);
                }
                return;
              default:
                return;
            }
          }}
        >
          <span id="tb-trend-window-value" class="tb-topbar-trend-window-value">
            {formatTrendWindowLabel(value)}
          </span>
          <span class={`tb-topbar-trend-window-chevron${isOpen ? " is-open" : ""}`} aria-hidden="true"></span>
        </button>

        {isOpen ? (
          <div
            id="tb-trend-window-listbox"
            class="tb-topbar-trend-window-menu"
            role="listbox"
            aria-label="Trend Window options"
          >
            {TREND_WINDOW_OPTIONS.map((optionValue) => {
              const selected = optionValue === value;
              return (
                <button
                  key={optionValue}
                  id={`tb-trend-window-option-${optionValue}`}
                  ref={(node) => {
                    optionRefs.current[optionValue] = node;
                  }}
                  type="button"
                  role="option"
                  class={`tb-topbar-trend-window-option${selected ? " is-selected" : ""}`}
                  aria-selected={selected ? "true" : "false"}
                  onClick={() => selectValue(optionValue)}
                  onKeyDown={(event) => {
                    switch (event.key) {
                      case "ArrowDown":
                        event.preventDefault();
                        focusOptionByOffset(optionValue, 1);
                        return;
                      case "ArrowUp":
                        event.preventDefault();
                        focusOptionByOffset(optionValue, -1);
                        return;
                      case "Home":
                        event.preventDefault();
                        focusOption(TREND_WINDOW_OPTIONS[0]);
                        return;
                      case "End":
                        event.preventDefault();
                        focusOption(TREND_WINDOW_OPTIONS[TREND_WINDOW_OPTIONS.length - 1]);
                        return;
                      case "Enter":
                      case " ":
                        event.preventDefault();
                        selectValue(optionValue);
                        return;
                      default:
                        return;
                    }
                  }}
                >
                  <span>{formatTrendWindowLabel(optionValue)}</span>
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function Content({ appName }: Props) {
  const [active, setActive] = useState<ScreenId>("news");
  const [teamTrendWindowSelection, setTeamTrendWindowSelection] = useState<number>(12);
  const heading = useMemo(() => screenTitle(active), [active]);

  const updateTeamTrendWindowSelection = (nextValue: number) => {
    setTeamTrendWindowSelection(nextValue);
    window.dispatchEvent(new CustomEvent(TEAM_INSIGHTS_TREND_WINDOW_CHANGE_EVENT, {
      detail: { trendWindow: nextValue },
    }));
  };

  useEffect(() => {
    const handleTeamInsightsTrendWindowSync = (event: Event) => {
      const detail = (event as CustomEvent<{ trendWindow?: number }>).detail;
      const requestedTrendWindow = Number.parseInt(String(detail?.trendWindow ?? ""), 10);
      if (Number.isNaN(requestedTrendWindow)) return;
      setTeamTrendWindowSelection(normalizeTrendWindow(requestedTrendWindow));
    };
    window.addEventListener(TEAM_INSIGHTS_TREND_WINDOW_SYNC_EVENT, handleTeamInsightsTrendWindowSync as EventListener);
    return () => {
      window.removeEventListener(TEAM_INSIGHTS_TREND_WINDOW_SYNC_EVENT, handleTeamInsightsTrendWindowSync as EventListener);
    };
  }, []);

  return (
    <div class="tb-app-frame">
      <aside class="tb-sidebar">
        <div class="tb-brand">
          <div class="tb-brand-mark" aria-hidden="true">TB</div>
          <div>
            <p class="tb-eyebrow">{appName}</p>
            <h1>DevOps Console</h1>
            <small>Illuminating Engineering Insights</small>
          </div>
        </div>
        <nav class="tb-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              class={`tb-nav-item${active === item.id ? " is-active" : ""}`}
              onClick={() => setActive(item.id)}
            >
              <div class="tb-nav-title-row">
                <span class="tb-nav-title">{item.label}</span>
                {item.showConstruction ? (
                  <span
                    class="tb-nav-construction"
                    title="Under construction"
                    aria-label={`${item.label} is under construction`}
                  >
                    🚧
                  </span>
                ) : null}
              </div>
              <small>{item.blurb}</small>
            </button>
          ))}
        </nav>
      </aside>

      <main class="tb-main">
        <header class="tb-topbar">
          <h2>{heading}</h2>
          {active === "team" ? (
            <div class="tb-topbar-actions">
              <TrendWindowDropdown
                value={teamTrendWindowSelection}
                onChange={updateTeamTrendWindowSelection}
              />
              <button
                type="button"
                class="tb-btn tb-btn-sm tb-no-print"
                aria-label="Team Insights Settings"
                onClick={() => window.dispatchEvent(new CustomEvent(OPEN_TEAM_INSIGHTS_SETTINGS_EVENT))}
              >
                Settings
              </button>
            </div>
          ) : null}
        </header>
        <section class="tb-screen-body">{renderScreen(active)}</section>
      </main>
    </div>
  );
}
