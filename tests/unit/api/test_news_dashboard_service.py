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
        self.assertGreaterEqual(len(payload["trainingTips"]), 2)
        self.assertEqual(payload["trainingTip"], payload["trainingTips"][0])
        self.assertTrue(payload["trainingTips"][0]["id"])
        self.assertIn("working-line GSD", payload["trainingTips"][0]["description"])
        self.assertNotIn("reactive", payload["trainingTips"][0]["description"].lower())
        self.assertNotIn("overstimulated", payload["trainingTips"][0]["description"].lower())
        self.assertTrue(payload["trainingTips"][0]["skillName"])
        self.assertTrue(payload["trainingTips"][0]["skillArea"])

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

    def test_training_tips_are_daily_ordered_without_dropping_options(self) -> None:
        start = datetime(2026, 6, 1, 1, 0, tzinfo=timezone.utc)

        first = news_dashboard._build_training_tips(start)  # noqa: SLF001
        repeated = news_dashboard._build_training_tips(start.replace(hour=8))  # noqa: SLF001
        next_day = news_dashboard._build_training_tips(start + timedelta(days=1))  # noqa: SLF001

        self.assertEqual(first, repeated)
        self.assertEqual(len(first), len(news_dashboard._training_tip_catalog(first[0]["ageMonths"])))  # noqa: SLF001
        self.assertEqual(len({tip["id"] for tip in first}), len(first))
        self.assertNotEqual(first[0]["id"], next_day[0]["id"])
        self.assertTrue(all(tip.get("skillName") for tip in first))
        self.assertTrue(all(tip.get("skillArea") for tip in first))

    def test_training_tips_follow_puppy_current_age(self) -> None:
        nine_months = news_dashboard._build_training_tips(  # noqa: SLF001
            datetime(2026, 6, 1, 1, 0, tzinfo=timezone.utc)
        )
        twelve_months = news_dashboard._build_training_tips(  # noqa: SLF001
            datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc)
        )

        self.assertEqual(nine_months[0]["ageMonths"], 9)
        self.assertEqual(nine_months[0]["ageLabel"], "9-month-old")
        self.assertIn("adolescent working-line foundations", nine_months[0]["stageLabel"])
        self.assertEqual(twelve_months[0]["ageMonths"], 12)
        self.assertEqual(twelve_months[0]["ageLabel"], "12-month-old")
        self.assertIn("young dog proofing", twelve_months[0]["stageLabel"])
        self.assertNotEqual(
            {tip["id"] for tip in nine_months},
            {tip["id"] for tip in twelve_months},
        )

    def test_adolescent_training_tips_include_new_skills(self) -> None:
        tips = news_dashboard._build_training_tips(  # noqa: SLF001
            datetime(2026, 6, 1, 1, 0, tzinfo=timezone.utc)
        )
        skill_names = {tip["skillName"] for tip in tips}
        skill_areas = {tip["skillArea"] for tip in tips}

        self.assertIn("Nose-to-palm target", skill_names)
        self.assertIn("Go to mat", skill_names)
        self.assertIn("Leave it", skill_names)
        self.assertIn("Drop", skill_names)
        self.assertIn("Chin rest", skill_names)
        self.assertIn("Down stay", skill_names)
        self.assertIn("Wait at doors", skill_names)
        self.assertIn("Surface confidence", skill_names)
        self.assertEqual({"Obedience", "Life skills", "Confidence building"}, skill_areas)

    def test_every_age_band_has_named_skills(self) -> None:
        for age_months in (3, 9, 12, 18):
            with self.subTest(age_months=age_months):
                tips = news_dashboard._training_tip_catalog(age_months)  # noqa: SLF001
                self.assertTrue(tips)
                self.assertTrue(all(tip.get("skillName") for tip in tips))
                self.assertTrue(all(tip.get("skillArea") for tip in tips))


if __name__ == "__main__":
    unittest.main()
