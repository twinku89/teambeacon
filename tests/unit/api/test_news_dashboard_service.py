from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services.api import news_dashboard


class NewsDashboardServiceTests(unittest.TestCase):
    def tearDown(self) -> None:
        news_dashboard._news_cache = None  # noqa: SLF001

    def test_groups_feed_items_and_adds_training_tip(self) -> None:
        def fake_fetch(feed: news_dashboard.NewsFeed):
            return (
                feed,
                [
                    {
                        "id": f"{feed.category_id}-1",
                        "categoryId": feed.category_id,
                        "title": f"{feed.category_label} headline",
                        "source": feed.source,
                        "url": f"https://example.com/{feed.category_id}",
                        "publishedAt": "2026-05-25T07:00:00+00:00",
                        "summary": "Summary",
                    }
                ],
                None,
            )

        with patch.object(news_dashboard, "_fetch_feed", side_effect=fake_fetch):
            payload = news_dashboard.get_news_dashboard()

        self.assertEqual(payload["source"], "rss")
        categories = {category["id"]: category for category in payload["categories"]}
        self.assertIn("world", categories)
        self.assertIn("tech", categories)
        self.assertNotIn("melbourne", categories)
        self.assertNotIn("premierLeague", categories)
        self.assertNotIn("cricket", categories)
        self.assertGreaterEqual(len(categories["world"]["articles"]), 1)
        self.assertEqual(payload["bookOfTheDay"]["label"], "Book of the Day")
        self.assertTrue(payload["bookOfTheDay"]["title"])
        self.assertEqual(payload["bookOfTheDay"]["readingTimeMinutes"], 5)
        self.assertTrue(payload["bookOfTheDay"]["detailedSummary"])
        self.assertGreaterEqual(len(payload["bookOfTheDay"]["keyIdeas"]), 1)
        self.assertTrue(payload["bookOfTheDay"]["tryToday"])
        self.assertEqual(payload["trainingTip"]["categoryId"], "dogTraining")
        self.assertGreaterEqual(len(payload["trainingTip"]["steps"]), 1)

    def test_returns_cached_payload_with_cached_marker(self) -> None:
        news_dashboard._news_cache = {  # noqa: SLF001
            "source": "rss",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "timezone": "Australia/Melbourne",
            "categories": [],
            "bookOfTheDay": {"label": "Book of the Day", "title": "Atomic Habits"},
            "trainingTip": {"categoryId": "dogTraining", "steps": []},
            "error": None,
        }

        payload = news_dashboard.get_news_dashboard()

        self.assertTrue(payload["cached"])

    def test_book_rotation_is_stable_per_day_without_short_repeats(self) -> None:
        start = datetime(2026, 6, 1, 1, 0, tzinfo=timezone.utc)

        first = news_dashboard._build_book_of_the_day(start)  # noqa: SLF001
        repeated = news_dashboard._build_book_of_the_day(start.replace(hour=8))  # noqa: SLF001
        titles = [
            news_dashboard._build_book_of_the_day(start + timedelta(days=offset))["title"]  # noqa: SLF001
            for offset in range(10)
        ]

        self.assertEqual(first["title"], repeated["title"])
        self.assertEqual(len(titles), len(set(titles)))


if __name__ == "__main__":
    unittest.main()
