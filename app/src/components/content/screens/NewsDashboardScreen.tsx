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

function DogTrainingPanel({ tip }: { tip: DogTrainingTip }) {
  return (
    <article id="news-dog-training" class="tb-news-panel tb-news-training-panel">
      <header>
        <div>
          <h3>{tip.label}</h3>
          <p>{tip.description}</p>
        </div>
        <span>Daily focus</span>
      </header>
      <div class="tb-news-training-body">
        <h4>{tip.title}</h4>
        <p>{tip.focus}</p>
        <ol>
          {tip.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        {tip.note ? <p class="tb-muted-note">{tip.note}</p> : null}
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
  const sectionLinks = [
    ...newsCategories.map((category) => ({ href: `#${newsSectionId(category.id)}`, label: category.label })),
    ...(payload?.bookOfTheDay ? [{ href: "#news-book-of-the-day", label: payload.bookOfTheDay.label }] : []),
    ...(payload?.trainingTip ? [{ href: "#news-dog-training", label: payload.trainingTip.label }] : []),
  ];

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

      {payload?.trainingTip ? <DogTrainingPanel tip={payload.trainingTip} /> : null}

      {loading && !payload ? <p class="tb-muted-note">Loading today's news feeds...</p> : null}
    </div>
  );
}
