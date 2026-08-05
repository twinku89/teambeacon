import { fireEvent, render, screen } from "@testing-library/preact";
import { beforeEach } from "vitest";
import { NewsDashboardScreen } from "../../src/components/content/screens/NewsDashboardScreen";
import { setupFetchMock } from "../utils/fetchMock";

const TRAINING_TIP_COUNT_STORAGE_KEY = "teambeacon.dailyBriefing.trainingTipCount.2026-06-01";

function setupNewsDashboardFetchMock() {
  setupFetchMock({
    "/api/news/dashboard": {
      source: "rss",
      generatedAt: "2026-06-01T00:30:00+00:00",
      timezone: "Australia/Melbourne",
      categories: [],
      bookOfTheDay: {
        label: "Book of the Day",
        topic: "Personal development",
        title: "Range",
        author: "David Epstein",
        summary: "A practical case for broad learning.",
        whyRead: "Useful when personal growth feels too narrowly optimized.",
      },
      trainingTip: {
        categoryId: "dogTraining",
        id: "engagement-check-ins",
        label: "Dog Training",
        description: "Training tips for this 9-month-old working-line GSD, tuned for adolescent working-line foundations.",
        title: "Engagement check-ins",
        skillName: "Voluntary check-in",
        skillArea: "Life skills",
        focus: "Teach your adolescent working-line GSD that checking in is always worth it.",
        steps: ["Reward calm check-ins.", "Resume walking after each reward."],
        note: "Keep sessions short, reward-based, and matched to health, energy, and recovery.",
      },
      trainingTips: [
        {
          categoryId: "dogTraining",
          id: "engagement-check-ins",
          label: "Dog Training",
          description: "Training tips for this 9-month-old working-line GSD, tuned for adolescent working-line foundations.",
          title: "Engagement check-ins",
          skillName: "Voluntary check-in",
          skillArea: "Life skills",
          focus: "Teach your adolescent working-line GSD that checking in is always worth it.",
          steps: ["Reward calm check-ins.", "Resume walking after each reward."],
          note: "Keep sessions short, reward-based, and matched to health, energy, and recovery.",
        },
        {
          categoryId: "dogTraining",
          id: "place-cue-with-release",
          label: "Dog Training",
          description: "Training tips for this 9-month-old working-line GSD, tuned for adolescent working-line foundations.",
          title: "Place cue with release",
          skillName: "Go to mat",
          skillArea: "Life skills",
          focus: "Teach a clear stationing behaviour for meals, visitors, calls, and recovery.",
          steps: ["Reward all four paws on the mat.", "Release before he steps off."],
          note: "Keep sessions short, reward-based, and matched to health, energy, and recovery.",
        },
      ],
      error: null,
    },
  });
}

describe("NewsDashboardScreen", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("adds another dog training tip on demand", async () => {
    setupNewsDashboardFetchMock();

    render(<NewsDashboardScreen />);

    expect(await screen.findByText("Engagement check-ins")).toBeInTheDocument();
    expect(screen.getByText("Personal development")).toBeInTheDocument();
    expect(screen.getAllByText("Area: Life skills").length).toBeGreaterThan(0);
    expect(screen.getByText("Skill: Voluntary check-in")).toBeInTheDocument();
    expect(screen.queryByText("Place cue with release")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add another tip" }));

    expect(screen.getByText("Place cue with release")).toBeInTheDocument();
    expect(screen.getByText("Skill: Go to mat")).toBeInTheDocument();
    expect(window.localStorage.getItem(TRAINING_TIP_COUNT_STORAGE_KEY)).toBe("2");
  });

  it("restores the selected daily dog training tip count", async () => {
    window.localStorage.setItem(TRAINING_TIP_COUNT_STORAGE_KEY, "2");
    setupNewsDashboardFetchMock();

    render(<NewsDashboardScreen />);

    expect(await screen.findByText("Engagement check-ins")).toBeInTheDocument();
    expect(await screen.findByText("Place cue with release")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All daily tips added" })).toBeDisabled();
  });
});
