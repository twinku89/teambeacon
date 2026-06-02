/**
 * @license
 * Copyright (c) 2014, 2026, Oracle and/or its affiliates.
 * Licensed under The Universal Permissive License (UPL), Version 1.0
 * as shown at https://oss.oracle.com/licenses/upl/
 * @ignore
 */
import { h } from "preact";
import { useCallback, useEffect, useMemo, useState } from "preact/hooks";
import type {
  BookOfTheDay,
  DogTrainingTip,
  NewsArticle,
  NewsCategory,
  NewsDashboardResponse,
} from "../../../lib/api";
import {
  fetchNewsDashboard,
} from "../../../lib/api";

const TRAINING_TIP_COUNT_STORAGE_PREFIX = "teambeacon.dailyBriefing.trainingTipCount";

function formatTimestamp(value?: string | null): string {
  if (!value) return "No timestamp";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "No timestamp";
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  }).format(parsed);
}

function countArticles(categories: NewsCategory[]): number {
  return categories.reduce((sum, category) => sum + category.articles.length, 0);
}

function categoryById(categories: NewsCategory[], categoryId: string): NewsCategory | undefined {
  return categories.find((category) => category.id === categoryId);
}

function headlineLabel(articleCount: number): string {
  if (articleCount === 1) return "1 headline";
  return `${articleCount} headlines`;
}

function newsSectionId(categoryId: string): string {
  return `news-${categoryId}`;
}

function localDateKey(value?: string | null, timezone = "Australia/Melbourne"): string {
  if (!value) return "unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value.slice(0, 10) || "unknown";

  try {
    const parts = new Intl.DateTimeFormat("en", {
      day: "2-digit",
      month: "2-digit",
      timeZone: timezone,
      year: "numeric",
    }).formatToParts(parsed);
    const part = (type: string) => parts.find((candidate) => candidate.type === type)?.value;
    const year = part("year");
    const month = part("month");
    const day = part("day");
    if (year && month && day) return `${year}-${month}-${day}`;
  } catch {
    // Fall back to the API timestamp when the runtime does not support the named timezone.
  }

  return value.slice(0, 10) || "unknown";
}

function trainingTipCountStorageKey(payload: NewsDashboardResponse): string {
  return `${TRAINING_TIP_COUNT_STORAGE_PREFIX}.${localDateKey(payload.generatedAt, payload.timezone)}`;
}

function clampTrainingTipCount(value: number, maxCount: number): number {
  if (maxCount <= 0) return 0;
  if (!Number.isFinite(value)) return 1;
  return Math.max(1, Math.min(maxCount, Math.floor(value)));
}

function readTrainingTipCount(storageKey: string | null, maxCount: number): number {
  if (!storageKey || typeof window === "undefined") return maxCount > 0 ? 1 : 0;
  const stored = window.localStorage.getItem(storageKey);
  if (!stored) return maxCount > 0 ? 1 : 0;
  return clampTrainingTipCount(Number.parseInt(stored, 10), maxCount);
}

function writeTrainingTipCount(storageKey: string | null, count: number): void {
  if (!storageKey || typeof window === "undefined") return;
  window.localStorage.setItem(storageKey, String(count));
}

function NewsArticleList({ articles }: { articles: NewsArticle[] }) {
  if (articles.length === 0) {
    return <p class="tb-news-empty">No fresh items were returned for this category.</p>;
  }

  return (
    <ul class="tb-news-list">
      {articles.map((article) => (
        <li key={`${article.source}-${article.id}`} class="tb-news-item">
          <a href={article.url} target="_blank" rel="noreferrer">
            {article.title}
          </a>
          <div class="tb-news-meta">
            <span>{article.source}</span>
            <span>{formatTimestamp(article.publishedAt)}</span>
          </div>
          {article.summary ? <p>{article.summary}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function NewsCategoryPanel({ category }: { category: NewsCategory }) {
  return (
    <article id={newsSectionId(category.id)} class="tb-news-panel">
      <header>
        <div>
          <h3>{category.label}</h3>
          <p>{category.description}</p>
        </div>
        <span>{headlineLabel(category.articles.length)}</span>
      </header>
      <NewsArticleList articles={category.articles} />
      {category.errors && category.errors.length > 0 ? (
        <p class="tb-error-note">{category.errors[0]}</p>
      ) : null}
    </article>
  );
}

function DogTrainingPanel({
  canAddTip,
  onAddTip,
  tips,
  totalTipCount,
}: {
  canAddTip: boolean;
  onAddTip: () => void;
  tips: DogTrainingTip[];
  totalTipCount: number;
}) {
  const firstTip = tips[0];
  if (!firstTip) return null;
  const remainingTipCount = Math.max(0, totalTipCount - tips.length);

  return (
    <article id="news-dog-training" class="tb-news-panel tb-news-training-panel">
      <header>
        <div>
          <h3>{firstTip.label}</h3>
          <p>{firstTip.description}</p>
        </div>
        <span>{tips.length === 1 ? "1 daily focus" : `${tips.length} daily focuses`}</span>
      </header>
      <div class="tb-news-training-body">
        {tips.map((tip, index) => (
          <section class="tb-news-training-tip" key={tip.id ?? `${tip.title}-${index}`}>
            <div class="tb-news-training-tip-heading">
              <span>Tip {index + 1}</span>
              <h4>{tip.title}</h4>
            </div>
            {tip.skillName || tip.skillArea ? (
              <div class="tb-news-training-tags">
                {tip.skillArea ? <span class="tb-news-training-skill">Area: {tip.skillArea}</span> : null}
                {tip.skillName ? <span class="tb-news-training-skill">Skill: {tip.skillName}</span> : null}
              </div>
            ) : null}
            <p>{tip.focus}</p>
            <ol>
              {tip.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            {tip.note ? <p class="tb-muted-note">{tip.note}</p> : null}
          </section>
        ))}
        <div class="tb-news-training-actions">
          <button type="button" class="tb-btn tb-btn-sm" onClick={onAddTip} disabled={!canAddTip}>
            {canAddTip ? "Add another tip" : "All daily tips added"}
          </button>
          {remainingTipCount > 0 ? <small>{remainingTipCount} more available today</small> : null}
        </div>
      </div>
    </article>
  );
}

function BookOfTheDayPanel({ book }: { book: BookOfTheDay }) {
  return (
    <article id="news-book-of-the-day" class="tb-news-panel tb-news-books-panel">
      <header>
        <div>
          <h3>{book.label}</h3>
          <p>One focused summary for today's reading queue.</p>
        </div>
        <span>{book.readingTimeMinutes ? `${book.readingTimeMinutes} min read` : "Daily read"}</span>
      </header>
      <div class="tb-news-book-feature">
        <strong>{book.title}</strong>
        <span>{book.author}</span>
        <p>{book.detailedSummary || book.summary}</p>
        {book.keyIdeas && book.keyIdeas.length > 0 ? (
          <div class="tb-news-book-ideas">
            <h4>Key Ideas</h4>
            <ul>
              {book.keyIdeas.map((idea) => (
                <li key={idea}>{idea}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <small>{book.whyRead}</small>
        {book.tryToday ? <small class="tb-news-book-action">Try today: {book.tryToday}</small> : null}
      </div>
    </article>
  );
}

export function NewsDashboardScreen() {
  const [payload, setPayload] = useState<NewsDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visibleTrainingTipCount, setVisibleTrainingTipCount] = useState(1);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const nextPayload = await fetchNewsDashboard();
      setPayload(nextPayload);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load daily briefing.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const articleCount = useMemo(() => countArticles(payload?.categories ?? []), [payload]);
  const world = categoryById(payload?.categories ?? [], "world");
  const australia = categoryById(payload?.categories ?? [], "australia");
  const tech = categoryById(payload?.categories ?? [], "tech");
  const manchesterUnited = categoryById(payload?.categories ?? [], "manchesterUnited");
  const india = categoryById(payload?.categories ?? [], "india");
  const newsCategories = [world, australia, tech, manchesterUnited, india]
    .filter((category): category is NewsCategory => Boolean(category));
  const trainingTips = useMemo(() => {
    if (payload?.trainingTips && payload.trainingTips.length > 0) return payload.trainingTips;
    return payload?.trainingTip ? [payload.trainingTip] : [];
  }, [payload]);
  const trainingTipStorageKey = useMemo(
    () => (payload ? trainingTipCountStorageKey(payload) : null),
    [payload],
  );
  const visibleTrainingTips = useMemo(
    () => trainingTips.slice(0, clampTrainingTipCount(visibleTrainingTipCount, trainingTips.length)),
    [trainingTips, visibleTrainingTipCount],
  );
  const canAddTrainingTip = visibleTrainingTips.length < trainingTips.length;
  const sectionLinks = [
    ...newsCategories.map((category) => ({ href: `#${newsSectionId(category.id)}`, label: category.label })),
    ...(payload?.bookOfTheDay ? [{ href: "#news-book-of-the-day", label: payload.bookOfTheDay.label }] : []),
    ...(trainingTips.length > 0 ? [{ href: "#news-dog-training", label: trainingTips[0].label }] : []),
  ];

  useEffect(() => {
    setVisibleTrainingTipCount(readTrainingTipCount(trainingTipStorageKey, trainingTips.length));
  }, [trainingTipStorageKey, trainingTips.length]);

  const addTrainingTip = useCallback(() => {
    setVisibleTrainingTipCount((currentCount) => {
      const nextCount = clampTrainingTipCount(currentCount + 1, trainingTips.length);
      writeTrainingTipCount(trainingTipStorageKey, nextCount);
      return nextCount;
    });
  }, [trainingTipStorageKey, trainingTips.length]);

  return (
    <div class="tb-content-stack">
      <section class="tb-screen-panel">
        <div class="tb-screen-header-row">
          <div>
            <p class="tb-section-kicker">Daily briefing</p>
            <h3>Daily Briefing</h3>
            <p class="tb-muted-note">
              Latest headlines grouped for a quick morning scan, with a daily book and dog training at the end.
            </p>
          </div>
          <button type="button" class="tb-btn tb-btn-sm" onClick={() => void loadDashboard()} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh News"}
          </button>
        </div>

        <div class="tb-metrics-grid tb-four-up">
          <article class="tb-metric-card">
            <h4>Total Headlines</h4>
            <strong class="tb-value">{loading && !payload ? "..." : articleCount}</strong>
            <p>Across active news feeds.</p>
          </article>
          <article class="tb-metric-card">
            <h4>United Watch</h4>
            <strong class="tb-value">
              {loading && !payload ? "..." : manchesterUnited?.articles.length ?? 0}
            </strong>
            <p>Manchester United headlines.</p>
          </article>
          <article class="tb-metric-card">
            <h4>Tech Watch</h4>
            <strong class="tb-value">
              {loading && !payload ? "..." : tech?.articles.length ?? 0}
            </strong>
            <p>Technology headlines.</p>
          </article>
          <article class="tb-metric-card">
            <h4>Last Updated</h4>
            <strong class="tb-value tb-news-updated">{payload ? formatTimestamp(payload.generatedAt) : "..."}</strong>
            <p>{payload?.cached ? "Served from cache." : "Live API refresh."}</p>
          </article>
        </div>

        {sectionLinks.length > 0 ? (
          <nav class="tb-news-section-links" aria-label="Daily briefing sections">
            {sectionLinks.map((link) => (
              <a key={link.href} href={link.href}>
                {link.label}
              </a>
            ))}
          </nav>
        ) : null}

        {error ? <p class="tb-error-note">Daily briefing: {error}</p> : null}
      </section>

      <section class="tb-news-grid" aria-label="News categories">
        {newsCategories.map((category) => (
          <NewsCategoryPanel key={category.id} category={category} />
        ))}
      </section>

      {payload?.bookOfTheDay ? <BookOfTheDayPanel book={payload.bookOfTheDay} /> : null}

      {visibleTrainingTips.length > 0 ? (
        <DogTrainingPanel
          canAddTip={canAddTrainingTip}
          onAddTip={addTrainingTip}
          tips={visibleTrainingTips}
          totalTipCount={trainingTips.length}
        />
      ) : null}

      {loading && !payload ? <p class="tb-muted-note">Loading today's news feeds...</p> : null}
    </div>
  );
}
