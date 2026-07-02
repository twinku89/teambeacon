from __future__ import annotations

import html
import os
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 compatibility guard.
    ZoneInfo = None  # type: ignore[assignment]


NEWS_CACHE_SECONDS = 900
NEWS_TIMEOUT_SECONDS = 8
MAX_ITEMS_PER_SOURCE = 6
BOOK_ROTATION_EPOCH = date(2026, 1, 1)
DEFAULT_GSD_PUPPY_BIRTH_DATE = date(2025, 9, 1)


@dataclass(frozen=True)
class NewsFeed:
    category_id: str
    category_label: str
    description: str
    source: str
    url: str
    keywords: tuple[str, ...] = ()


FEEDS: tuple[NewsFeed, ...] = (
    NewsFeed(
        "world",
        "World News",
        "Global headlines from BBC News.",
        "BBC News",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
    ),
    NewsFeed(
        "world",
        "World News",
        "Global headlines from BBC News and The Guardian.",
        "The Guardian",
        "https://www.theguardian.com/world/rss",
    ),
    NewsFeed(
        "australia",
        "Australia News",
        "National Australian headlines from ABC and Guardian Australia.",
        "ABC News",
        "https://www.abc.net.au/news/feed/51120/rss.xml",
    ),
    NewsFeed(
        "australia",
        "Australia News",
        "National Australian headlines from ABC and Guardian Australia.",
        "The Guardian",
        "https://www.theguardian.com/australia-news/rss",
    ),
    NewsFeed(
        "tech",
        "Tech News",
        "Technology headlines from BBC News and The Guardian.",
        "BBC News",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ),
    NewsFeed(
        "tech",
        "Tech News",
        "Technology headlines from BBC News and The Guardian.",
        "The Guardian",
        "https://www.theguardian.com/technology/rss",
    ),
    NewsFeed(
        "manchesterUnited",
        "Manchester United",
        "Manchester United news for quick fan scanning.",
        "The Guardian",
        "https://www.theguardian.com/football/manchester-united/rss",
    ),
    NewsFeed(
        "manchesterUnited",
        "Manchester United",
        "Manchester United news for quick fan scanning.",
        "BBC Sport",
        "https://feeds.bbci.co.uk/sport/football/rss.xml",
        ("manchester united", "man utd", "old trafford", "amorim", "ten hag"),
    ),
    NewsFeed(
        "india",
        "India News",
        "India headlines from Times of India.",
        "Times of India",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    ),
)

CATEGORY_ORDER: tuple[tuple[str, str, str], ...] = (
    ("world", "World News", "Global headlines to start the day."),
    ("australia", "Australia News", "National headlines with Australian context."),
    ("tech", "Tech News", "Technology and industry headlines."),
    ("manchesterUnited", "Manchester United", "A dedicated United watchlist."),
    ("india", "India News", "India headlines and national updates."),
)

_news_cache: dict[str, Any] | None = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _melbourne_timezone() -> timezone:
    if ZoneInfo is None:
        return timezone.utc
    return ZoneInfo("Australia/Melbourne")


def _local_melbourne_date(now: datetime) -> date:
    return now.astimezone(_melbourne_timezone()).date()


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _puppy_birth_date() -> date:
    return _parse_iso_date(os.environ.get("DOG_TRAINING_PUPPY_BIRTH_DATE")) or DEFAULT_GSD_PUPPY_BIRTH_DATE


def _age_months_on(current_date: date, birth_date: date) -> int:
    month_count = (current_date.year - birth_date.year) * 12 + current_date.month - birth_date.month
    if current_date.day < birth_date.day:
        month_count -= 1
    return max(0, month_count)


def _age_label(age_months: int) -> str:
    if age_months < 24:
        return f"{age_months}-month-old"
    years = age_months // 12
    months = age_months % 12
    if months == 0:
        return f"{years}-year-old"
    return f"{years}-year, {months}-month-old"


def _training_stage_label(age_months: int) -> str:
    if age_months < 6:
        return "puppy foundations"
    if age_months < 12:
        return "adolescent working-line foundations"
    if age_months < 18:
        return "young dog proofing"
    return "young adult maintenance"


def _dog_training_profile(now: datetime) -> dict[str, Any]:
    local_date = _local_melbourne_date(now)
    birth_date = _puppy_birth_date()
    age_months = _age_months_on(local_date, birth_date)
    return {
        "birthDate": birth_date.isoformat(),
        "ageMonths": age_months,
        "ageDays": max(0, (local_date - birth_date).days),
        "ageLabel": _age_label(age_months),
        "stageLabel": _training_stage_label(age_months),
    }


def _strip_markup(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _child_text(element: ElementTree.Element, name: str) -> str:
    child = element.find(name)
    return _strip_markup(child.text if child is not None else None)


def _parse_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _article_id(url: str, title: str) -> str:
    seed = url.strip() or title.strip()
    return re.sub(r"[^a-zA-Z0-9]+", "-", seed.lower()).strip("-")[:96]


def _matches_keywords(article: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    if not keywords:
        return True
    haystack = f"{article.get('title') or ''} {article.get('summary') or ''}".lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def _is_dns_error(reason: Any) -> bool:
    reason_errno = getattr(reason, "errno", None)
    if reason_errno in {socket.EAI_AGAIN, socket.EAI_NONAME}:
        return True
    reason_text = str(reason).lower()
    return any(
        marker in reason_text
        for marker in (
            "nodename nor servname",
            "name or service not known",
            "temporary failure in name resolution",
            "no address associated with hostname",
        )
    )


def _feed_request_error(feed: NewsFeed, reason: Any) -> str:
    if _is_dns_error(reason):
        return (
            f"{feed.source} feed is temporarily unavailable because the RSS host could not be resolved. "
            "Check network or DNS and refresh."
        )
    return f"{feed.source} feed is temporarily unavailable. Try refreshing again shortly."


def _fetch_feed(feed: NewsFeed) -> tuple[NewsFeed, list[dict[str, Any]], str | None]:
    timeout = int(os.environ.get("NEWS_DASHBOARD_TIMEOUT_SECONDS", str(NEWS_TIMEOUT_SECONDS)))
    request = Request(feed.url, headers={"User-Agent": "TeamBeacon/1.0 news dashboard"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured public feeds only.
            raw = response.read()
    except HTTPError as exc:
        return feed, [], f"{feed.source} returned HTTP {exc.code}."
    except URLError as exc:
        return feed, [], _feed_request_error(feed, exc.reason)
    except TimeoutError:
        return feed, [], f"{feed.source} request timed out."

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        return feed, [], f"{feed.source} feed could not be parsed: {exc}"

    articles: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = _child_text(item, "title")
        url = _child_text(item, "link")
        if not title or not url:
            continue
        article = {
            "id": _article_id(url, title),
            "categoryId": feed.category_id,
            "title": title,
            "source": feed.source,
            "url": url,
            "publishedAt": _parse_datetime(_child_text(item, "pubDate")),
            "summary": _strip_markup(_child_text(item, "description"))[:360],
        }
        if _matches_keywords(article, feed.keywords):
            articles.append(article)
        if len(articles) >= MAX_ITEMS_PER_SOURCE:
            break

    return feed, articles, None


def _article_sort_key(article: dict[str, Any]) -> float:
    published_at = article.get("publishedAt")
    if isinstance(published_at, str):
        try:
            return datetime.fromisoformat(published_at).timestamp()
        except ValueError:
            return 0
    return 0


def _training_tip_catalog(age_months: int) -> list[dict[str, Any]]:
    if age_months < 6:
        return [
            {
                "id": "name-game-foundations",
                "title": "Name game foundations",
                "skillName": "Name response",
                "skillArea": "Obedience",
                "focus": "Build fast orientation to his name before adding bigger distractions.",
                "steps": [
                    "Say his name once, mark the head turn, then feed close to you.",
                    "Practise in two quiet rooms before trying the garden or footpath.",
                    "Stop after 6 to 8 clean responses so the cue stays bright.",
                ],
            },
            {
                "id": "handling-consent-reps",
                "title": "Handling consent reps",
                "skillName": "Handling consent",
                "skillArea": "Life skills",
                "focus": "Make grooming, paws, ears, collar grabs, and vet-style handling predictable.",
                "steps": [
                    "Touch for one second, feed, then release before he pulls away.",
                    "Practise paws, ears, collar, harness clips, and mouth checks separately.",
                    "Keep sessions short enough that he chooses to re-engage.",
                ],
            },
            {
                "id": "crate-and-mat-comfort",
                "title": "Crate and mat comfort",
                "skillName": "Settle on mat",
                "skillArea": "Life skills",
                "focus": "Create safe rest locations before adolescence makes settling harder.",
                "steps": [
                    "Feed treats on the mat or in the crate with the door open.",
                    "Add tiny duration only while his body stays loose.",
                    "Release him calmly so rest spots do not feel like traps.",
                ],
            },
            {
                "id": "tiny-recall-parties",
                "title": "Tiny recall parties",
                "skillName": "Puppy recall",
                "skillArea": "Obedience",
                "focus": "Make coming back feel better than continuing whatever he was doing.",
                "steps": [
                    "Call once from a few steps away in a low-distraction space.",
                    "Move backward, praise, and feed several small rewards when he arrives.",
                    "Let him return to exploring when it is safe, so recall does not always end fun.",
                ],
            },
            {
                "id": "socialization-observation",
                "title": "Socialization by observation",
                "skillName": "Calm observation",
                "skillArea": "Confidence building",
                "focus": "Show him the world without forcing greetings or busy interactions.",
                "steps": [
                    "Watch people, traffic, surfaces, and dogs from comfortable distance.",
                    "Feed for checking in and for calm curiosity.",
                    "Leave before he becomes tired, worried, or frantic.",
                ],
            },
        ]

    if age_months < 12:
        return [
            {
                "id": "engagement-check-ins",
                "title": "Engagement check-ins",
                "skillName": "Voluntary check-in",
                "skillArea": "Life skills",
                "focus": "Teach your adolescent working-line GSD to offer attention without being nagged.",
                "steps": [
                    "Stand still in a quiet area and wait for a head turn or eye contact.",
                    "Mark the instant he checks in, then feed close to your leg.",
                    "Move again so checking in becomes a way to restart the walk.",
                ],
            },
            {
                "id": "hand-target",
                "title": "Hand target",
                "skillName": "Nose-to-palm target",
                "skillArea": "Life skills",
                "focus": "Build a simple way to move, redirect, and position him without lead pressure.",
                "steps": [
                    "Present an open palm a few centimetres from his nose.",
                    "Mark the nose touch, feed from the other hand, then reset.",
                    "Add the cue once he is confidently moving to touch your palm.",
                ],
            },
            {
                "id": "place-cue-with-release",
                "title": "Place cue with release",
                "skillName": "Go to mat",
                "skillArea": "Life skills",
                "focus": "Teach a clear stationing behaviour for meals, visitors, calls, and recovery.",
                "steps": [
                    "Drop a treat on the mat and mark when all four paws are on it.",
                    "Feed two or three calm treats while he stays there.",
                    "Use a release cue before he steps off so the finish is clear.",
                ],
            },
            {
                "id": "loose-leash-follow-me",
                "title": "Loose-leash follow me",
                "skillName": "Loose-leash walking",
                "skillArea": "Obedience",
                "focus": "Teach him that staying near you makes forward motion continue.",
                "steps": [
                    "Start in a low-distraction space and reward at your trouser seam every few steps.",
                    "Change direction before the lead tightens and reward when he catches up.",
                    "Keep reps to 30 to 60 seconds, then release him to sniff.",
                ],
            },
            {
                "id": "recall-away-from-movement",
                "title": "Recall away from movement",
                "skillName": "Recall from distraction",
                "skillArea": "Obedience",
                "focus": "Practise turning away from movement before it becomes too hard.",
                "steps": [
                    "Use a long line and choose movement at a distance where he can still eat.",
                    "Say the recall cue once, move backward, and reward when he turns with you.",
                    "Release him back to safe exploring after some recalls so coming back does not always end fun.",
                ],
            },
            {
                "id": "leave-it-foundations",
                "title": "Leave it foundations",
                "skillName": "Leave it",
                "skillArea": "Life skills",
                "focus": "Teach disengagement from food, objects, and movement as a rewarded choice.",
                "steps": [
                    "Place boring food under your foot and wait without repeating the cue.",
                    "Mark the moment he backs off or looks at you, then feed a better reward from your hand.",
                    "Add the verbal cue only after he understands that leaving makes better things happen.",
                ],
            },
            {
                "id": "drop-and-trade",
                "title": "Drop and trade",
                "skillName": "Drop",
                "skillArea": "Obedience",
                "focus": "Build a clean release of toys and found objects without conflict.",
                "steps": [
                    "Offer a low-value toy, then present food at his nose.",
                    "Mark when the mouth opens, feed, and give the toy back.",
                    "Add the cue once the trade is smooth and predictable.",
                ],
            },
            {
                "id": "middle-position",
                "title": "Middle position",
                "skillName": "Middle",
                "skillArea": "Confidence building",
                "focus": "Teach him to come between your legs as a useful station and confidence skill.",
                "steps": [
                    "Lure him between your legs from behind and feed while he is centred.",
                    "Reset by tossing a treat forward, then invite him back through.",
                    "Add the cue after the path is fluent and his body stays relaxed.",
                ],
            },
            {
                "id": "scent-search-cue",
                "title": "Scent search cue",
                "skillName": "Find it",
                "skillArea": "Confidence building",
                "focus": "Give the working brain a structured search game with a clear start and finish.",
                "steps": [
                    "Let him watch you place three treats in easy grass or around one room.",
                    "Cue the search, then stay quiet while he works.",
                    "Use an all-done cue and move to calm chewing or water after the last find.",
                ],
            },
            {
                "id": "chin-rest-care",
                "title": "Chin rest for care",
                "skillName": "Chin rest",
                "skillArea": "Life skills",
                "focus": "Teach a cooperative-care position for grooming, checks, and calm handling.",
                "steps": [
                    "Hold a flat palm or towel at chest height and reward any chin contact.",
                    "Feed for one second of stillness, then release before he lifts away.",
                    "Gradually add tiny ear, collar, paw, or brush movements while the chin stays down.",
                ],
            },
            {
                "id": "down-stay-with-release",
                "title": "Down stay with release",
                "skillName": "Down stay",
                "skillArea": "Obedience",
                "focus": "Build a calm position that has a clear start, duration, and finish.",
                "steps": [
                    "Cue down, feed between his paws, and release after one quiet second.",
                    "Add duration before distance so the behaviour stays easy to win.",
                    "Use the release cue every time so he learns not to self-release.",
                ],
            },
            {
                "id": "sit-to-greet",
                "title": "Sit to greet",
                "skillName": "Polite greeting",
                "skillArea": "Life skills",
                "focus": "Turn greetings into a predictable pattern instead of a burst of jumping.",
                "steps": [
                    "Practise with one calm person before trying visitors or busy paths.",
                    "Reward four paws on the floor, then ask for a simple sit.",
                    "End the greeting and reset if he launches forward or cannot take food.",
                ],
            },
            {
                "id": "doorway-boundary",
                "title": "Doorway boundary",
                "skillName": "Wait at doors",
                "skillArea": "Life skills",
                "focus": "Teach him to pause at thresholds until released.",
                "steps": [
                    "Stand at a door, reward stillness, and open it only a small amount.",
                    "Close the door calmly if he moves forward before the release.",
                    "Release him through when the lead is loose and his body is settled.",
                ],
            },
            {
                "id": "body-awareness-ladder",
                "title": "Body awareness ladder",
                "skillName": "Rear-foot awareness",
                "skillArea": "Confidence building",
                "focus": "Help the adolescent body learn careful feet and thoughtful movement.",
                "steps": [
                    "Lay poles, broom handles, or safe low objects on the ground.",
                    "Lure slowly so he steps over one foot at a time instead of bouncing.",
                    "Reward pauses and careful choices more than speed.",
                ],
            },
            {
                "id": "novel-surface-confidence",
                "title": "Novel surface confidence",
                "skillName": "Surface confidence",
                "skillArea": "Confidence building",
                "focus": "Build confidence around safe textures, sounds, and unstable-looking surfaces.",
                "steps": [
                    "Start with easy surfaces such as cardboard, towels, rubber mats, or low platforms.",
                    "Reward investigation, one paw, two paws, then relaxed movement.",
                    "Let him step off whenever he chooses so confidence stays voluntary.",
                ],
            },
            {
                "id": "toy-impulse-control",
                "title": "Toy impulse control",
                "skillName": "Wait for toy release",
                "skillArea": "Obedience",
                "focus": "Use toy drive to practise listening before the game starts.",
                "steps": [
                    "Hold the toy still and reward a sit, down, or eye contact before movement begins.",
                    "Use a clear release word to start the tug or chase.",
                    "Pause often for drop, reset, and another release so control predicts more play.",
                ],
            },
            {
                "id": "settle-while-life-happens",
                "title": "Settle while life happens",
                "skillName": "Everyday settle",
                "skillArea": "Life skills",
                "focus": "Practise calm while normal household movement happens around him.",
                "steps": [
                    "Send him to a mat while you make tea, fold laundry, or answer a short call.",
                    "Feed for relaxed body shifts, chin dips, or quiet watching.",
                    "Release before he gets up so the session ends with success.",
                ],
            },
            {
                "id": "platform-pivot",
                "title": "Platform pivot",
                "skillName": "Pivot awareness",
                "skillArea": "Confidence building",
                "focus": "Build confidence, coordination, and handler focus with a small platform.",
                "steps": [
                    "Reward front paws on a stable low platform or thick book.",
                    "Lure a tiny side step and mark any rear-foot movement.",
                    "Keep it playful and slow so he learns body control without frustration.",
                ],
            },
        ]

    if age_months < 18:
        return [
            {
                "id": "proofed-recall-layers",
                "title": "Proofed recall layers",
                "skillName": "Proofed recall",
                "skillArea": "Obedience",
                "focus": "Move recall from puppy enthusiasm into reliable young-dog habit.",
                "steps": [
                    "Practise on a long line before expecting off-leash reliability.",
                    "Reward heavily for turning away from sniffing, toys, or movement.",
                    "Release him back to safe exploration after some recalls.",
                ],
            },
            {
                "id": "place-duration-with-release",
                "title": "Place duration with release",
                "skillName": "Place duration",
                "skillArea": "Life skills",
                "focus": "Build a practical settle that can survive household movement.",
                "steps": [
                    "Send him to the mat, feed calmly, and add duration in small increments.",
                    "Walk one step away and return before he breaks position.",
                    "Use a clear release cue so he learns when the job is finished.",
                ],
            },
            {
                "id": "heel-position-refresh",
                "title": "Heel position refresh",
                "skillName": "Heel position",
                "skillArea": "Obedience",
                "focus": "Keep position clear without drilling so long that enthusiasm drops.",
                "steps": [
                    "Reward the first step in position before asking for longer sequences.",
                    "Use turns and pace changes to make the exercise active.",
                    "Break after 30 to 60 seconds and let him sniff.",
                ],
            },
            {
                "id": "cooperative-care-proofing",
                "title": "Cooperative care proofing",
                "skillName": "Cooperative care",
                "skillArea": "Life skills",
                "focus": "Make adult-size handling easier before strength and confidence peak.",
                "steps": [
                    "Practise chin rest, paw hold, ear check, and collar hold separately.",
                    "Feed for stillness, then release before he opts out.",
                    "Add grooming tools only after the body behavior is relaxed.",
                ],
            },
            {
                "id": "scent-search-control",
                "title": "Scent search control",
                "skillName": "Controlled scent search",
                "skillArea": "Confidence building",
                "focus": "Give the working brain a job while practising starts, pauses, and finishes.",
                "steps": [
                    "Hide food or a toy in one easy area and cue the search.",
                    "Pause between searches so arousal can drop.",
                    "Finish with a clear all-done cue and a calm activity.",
                ],
            },
        ]

    return [
        {
            "id": "adult-maintenance-audit",
            "title": "Adult maintenance audit",
            "skillName": "Core skill maintenance",
            "skillArea": "Obedience",
            "focus": "Keep core skills fluent instead of waiting until they fade.",
            "steps": [
                "Pick one skill each day: recall, leash, settle, handling, or toy rules.",
                "Practise in an easy context before adding difficulty.",
                "Record the weakest skill and make tomorrow's version simpler.",
            ],
        },
        {
            "id": "fitness-and-recovery-balance",
            "title": "Fitness and recovery balance",
            "skillName": "Conditioning balance",
            "skillArea": "Confidence building",
            "focus": "Match work, conditioning, and rest to a high-drive young adult body.",
            "steps": [
                "Alternate intense training days with lower-impact sniffing or search days.",
                "Watch for sloppy movement, slower responses, or irritability as fatigue signals.",
                "Keep jumping and hard turns appropriate for his conditioning and vet guidance.",
            ],
        },
        {
            "id": "advanced-neutrality-practice",
            "title": "Advanced neutrality practice",
            "skillName": "Neutrality",
            "skillArea": "Life skills",
            "focus": "Maintain calm around dogs, people, traffic, and movement without requiring greetings.",
            "steps": [
                "Choose one everyday distraction and work at a distance where he can stay loose.",
                "Reward check-ins, quiet observation, and disengagement.",
                "End before he gets bored or starts inventing his own job.",
            ],
        },
        {
            "id": "toy-rules-for-drive",
            "title": "Toy rules for drive",
            "skillName": "Toy control",
            "skillArea": "Obedience",
            "focus": "Use tug and fetch to build control, not just intensity.",
            "steps": [
                "Ask for a short start behavior before the toy appears.",
                "Practise drop, re-grip, and restart with calm timing.",
                "Finish with food scatters or sniffing so drive has an off-ramp.",
            ],
        },
        {
            "id": "real-world-settle",
            "title": "Real-world settle",
            "skillName": "Public settle",
            "skillArea": "Life skills",
            "focus": "Turn maturity into practical calm in cafes, parks, friends' homes, or training fields.",
            "steps": [
                "Bring a mat and start in a low-traffic corner.",
                "Reward relaxed body shifts, chin downs, and quiet observation.",
                "Leave after a successful short session instead of stretching until failure.",
            ],
        },
    ]


def _with_training_tip_metadata(tip: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "categoryId": "dogTraining",
        "label": "Dog Training",
        "description": (
            f"Training tips for this {profile['ageLabel']} working-line GSD, "
            f"tuned for {profile['stageLabel']}."
        ),
        "ageMonths": profile["ageMonths"],
        "ageDays": profile["ageDays"],
        "ageLabel": profile["ageLabel"],
        "stageLabel": profile["stageLabel"],
        **tip,
        "note": "Keep sessions short, reward-based, and matched to health, energy, and recovery.",
    }


def _daily_rotation_index(now: datetime, item_count: int) -> int:
    local_date = _local_melbourne_date(now)
    return (local_date - BOOK_ROTATION_EPOCH).days % item_count


def _build_training_tips(now: datetime) -> list[dict[str, Any]]:
    profile = _dog_training_profile(now)
    tips = _training_tip_catalog(int(profile["ageMonths"]))
    day_index = _daily_rotation_index(now, len(tips))
    ordered_tips = [*tips[day_index:], *tips[:day_index]]
    return [_with_training_tip_metadata(tip, profile) for tip in ordered_tips]


def _build_training_tip(now: datetime) -> dict[str, Any]:
    return _build_training_tips(now)[0]


def _book_catalog() -> list[dict[str, Any]]:
    books = [
        {
            "title": "Atomic Habits",
            "author": "James Clear",
            "summary": "A practical guide to making tiny behavior changes compound into durable habits.",
            "whyRead": "Useful when you want training, fitness, work routines, or learning goals to survive busy weeks.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Atomic Habits argues that meaningful change is usually the result of small systems repeated "
                "consistently, not dramatic bursts of motivation. Clear frames habits as a loop of cue, craving, "
                "response, and reward. If you want a better habit, make the cue obvious, the action attractive, "
                "the behavior easy, and the reward satisfying. If you want to break a habit, invert those steps: "
                "hide the cue, make the habit unattractive, add friction, and make the reward less immediate. "
                "The strongest idea is identity-based change: instead of asking what outcome you want, ask what "
                "kind of person would naturally do the behavior. A runner runs, a reader reads, a calm handler "
                "practises calm reps. Each small repetition becomes evidence for that identity. The book is useful "
                "because it turns self-improvement into environment design. You do not need perfect discipline; "
                "you need a setup where the next good action is visible, small, and repeatable."
            ),
            "keyIdeas": [
                "Focus on systems, not only goals.",
                "Make good habits obvious, attractive, easy, and satisfying.",
                "Use tiny repetitions as votes for the identity you want.",
                "Reduce friction for good habits and add friction to habits you want to avoid.",
            ],
            "tryToday": "Pick one habit and shrink it to a two-minute starter version you can do even on a busy day.",
        },
        {
            "title": "Deep Work",
            "author": "Cal Newport",
            "summary": "A focused argument for protecting distraction-free time for cognitively hard work.",
            "whyRead": "Good for engineering leaders and makers who need more deliberate thinking time.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Deep Work is built around a simple claim: the ability to focus without distraction is becoming "
                "rarer at the same time it is becoming more valuable. Newport separates shallow work, such as "
                "reactive email, status pings, and small administrative tasks, from deep work that creates durable "
                "value through concentration. The book is less about being busy and more about protecting your best "
                "attention for work that changes outcomes. It recommends scheduling deep work, setting clear rules "
                "for availability, and treating focus like a trained capacity rather than a mood. For engineering, "
                "this maps neatly to design reviews, architecture decisions, debugging, writing, and strategic "
                "planning. The big takeaway is that attention leaks quietly. A day can feel full while producing "
                "little that matters. Deep work gives you permission to build boundaries, batch communication, and "
                "measure the quality of output instead of the volume of activity."
            ),
            "keyIdeas": [
                "Protect uninterrupted blocks for cognitively demanding work.",
                "Batch shallow work so it does not fragment the whole day.",
                "Define what done looks like before starting a focus block.",
                "Treat attention as a scarce engineering resource.",
            ],
            "tryToday": "Block 45 minutes for one hard task and close every input that can interrupt it.",
        },
        {
            "title": "Team Topologies",
            "author": "Matthew Skelton and Manuel Pais",
            "summary": "A modern operating model for shaping software teams around flow, ownership, and cognitive load.",
            "whyRead": "Useful when DevOps, platform ownership, and team boundaries start feeling messy.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Team Topologies says software architecture and team architecture are tied together. If team "
                "boundaries are unclear, ownership becomes slow, dependencies multiply, and delivery flow suffers. "
                "The book defines four team types: stream-aligned teams that own a flow of customer or business "
                "value, platform teams that provide internal products, enabling teams that coach or unblock, and "
                "complicated-subsystem teams that own specialist areas. It also defines interaction modes: "
                "collaboration, X-as-a-service, and facilitating. The practical point is not to draw an org chart "
                "for beauty; it is to reduce cognitive load and make work move. Teams should know what they own, "
                "how they interact, and when a collaboration mode should end. For DevOps, this is especially useful "
                "because platform work often fails when it becomes a ticket queue instead of a product with clear "
                "interfaces. The book helps you ask whether slow delivery is really a people problem, or a team "
                "design and ownership problem."
            ),
            "keyIdeas": [
                "Optimize teams for flow of change, not only reporting lines.",
                "Keep cognitive load within what a team can realistically own.",
                "Use platform teams as internal product teams, not generic support queues.",
                "Be explicit about interaction modes between teams.",
            ],
            "tryToday": "Pick one recurring cross-team dependency and label the current interaction mode.",
        },
        {
            "title": "The Design of Everyday Things",
            "author": "Don Norman",
            "summary": "A classic on how affordances, feedback, and constraints make products understandable.",
            "whyRead": "Sharpens how you think about dashboards, workflows, and user-facing tooling.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "The Design of Everyday Things explains why confusing products are usually design failures, not "
                "user failures. Norman focuses on affordances, signifiers, mapping, feedback, constraints, and "
                "conceptual models. In plain terms: a user should be able to see what actions are possible, predict "
                "what will happen, perform the action, and receive clear feedback. When a door needs a sign that "
                "says push, the design has already missed a chance to communicate. For dashboards and internal "
                "tools, the lesson is direct: labels, states, actions, errors, and navigation should reduce guesswork. "
                "Good design does not mean decoration; it means the system teaches itself through structure. The "
                "book also encourages empathy. If users make mistakes, ask what the interface made easy, what it "
                "hid, and what feedback arrived too late. It is a strong reminder that polished software is not "
                "only about features, but about making the correct next action feel natural."
            ),
            "keyIdeas": [
                "Make possible actions visible and understandable.",
                "Give fast, clear feedback after every important action.",
                "Treat user mistakes as design signals.",
                "Use constraints and mapping to make the right action easier.",
            ],
            "tryToday": "Choose one confusing screen and ask what the next action should be without reading instructions.",
        },
        {
            "title": "Decoding Your Dog",
            "author": "American College of Veterinary Behaviorists",
            "summary": "A science-grounded overview of common dog behavior challenges and humane interventions.",
            "whyRead": "A sensible companion read for adolescent reactivity, overarousal, and behavior plans.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Decoding Your Dog is useful because it treats behavior as communication, learning history, genetics, "
                "health, and environment working together. For a reactive adolescent working-line German Shepherd, "
                "that framing matters. Reactivity is not simply disobedience; it can be fear, frustration, arousal, "
                "lack of recovery, insufficient distance, or a pattern that has been rehearsed too often. The book "
                "leans toward humane, evidence-based approaches: understand triggers, manage the environment, reward "
                "the behavior you want, and get professional help when the dog or handler is struggling. The practical "
                "lesson is to train below threshold. A dog who is already barking, lunging, or scanning hard is not "
                "in the best state to learn. Create distance, lower intensity, reward calm choices, and end sessions "
                "before the dog tips over. For working-line dogs, it is also a reminder that more stimulation is not "
                "always the answer. Recovery, predictable routines, sniffing, chewing, and short skill sessions can "
                "do more for behavior than another high-intensity outing."
            ),
            "keyIdeas": [
                "Behavior has emotional and environmental causes, not just obedience causes.",
                "Train under threshold so the dog can still think and choose.",
                "Management is part of training, especially for adolescent reactivity.",
                "Humane professional support is appropriate when reactions intensify.",
            ],
            "tryToday": "On the next walk, reward three calm check-ins before your puppy has a chance to escalate.",
        },
        {
            "title": "Accelerate",
            "author": "Nicole Forsgren, Jez Humble, and Gene Kim",
            "summary": "A research-backed look at what predicts high-performing technology organizations.",
            "whyRead": "Useful when delivery speed, quality, reliability, and culture need to improve together.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Accelerate connects software delivery performance to measurable practices rather than folklore. "
                "The book argues that strong organizations ship faster and more safely because they invest in "
                "technical capabilities such as version control, continuous delivery, test automation, deployment "
                "automation, trunk-based development, observability, and loosely coupled architecture. It also "
                "links those practices to culture: teams need psychological safety, clear ownership, and the "
                "ability to improve their own systems. The useful part is the measurement model. Deployment "
                "frequency, lead time for changes, change failure rate, and time to restore service give a compact "
                "view of delivery health. They are not vanity metrics; they show whether the system can absorb "
                "change without drama. For TeamBeacon-style dashboards, Accelerate is a reminder that engineering "
                "health should be visible as flow, feedback, and recovery."
            ),
            "keyIdeas": [
                "Measure delivery with speed and stability together.",
                "Continuous delivery is an organizational capability, not just tooling.",
                "Loose architecture and team autonomy reinforce each other.",
                "Good culture shows up in faster learning and safer change.",
            ],
            "tryToday": "Pick one service and write down its deployment frequency, lead time, failure rate, and recovery time.",
        },
        {
            "title": "Thinking in Systems",
            "author": "Donella H. Meadows",
            "summary": "A clear introduction to feedback loops, constraints, delays, and leverage points.",
            "whyRead": "Helpful when a problem keeps returning after local fixes.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Thinking in Systems teaches you to look past isolated events and inspect the structure producing "
                "them. Meadows describes systems as stocks, flows, feedback loops, delays, goals, and rules. A "
                "team missing dates is not only a planning problem; it may be a feedback delay, an overloaded "
                "queue, a hidden incentive, or an unmanaged constraint. The book is valuable because it slows down "
                "the instinct to blame people or patch symptoms. Instead, it asks what the system rewards, what it "
                "hides, where information arrives late, and which loops are reinforcing the current behavior. The "
                "best leverage points are often not the loudest ones. Changing goals, information flows, rules, or "
                "constraints can matter more than pushing harder. For product and engineering work, it gives a calm "
                "way to diagnose recurring operational messes."
            ),
            "keyIdeas": [
                "Recurring problems usually come from system structure.",
                "Feedback loops and delays explain many surprising outcomes.",
                "Local optimization can make the whole system worse.",
                "Look for leverage points before adding more effort.",
            ],
            "tryToday": "Choose one recurring issue and map the feedback loop that keeps recreating it.",
        },
        {
            "title": "The Staff Engineer's Path",
            "author": "Tanya Reilly",
            "summary": "A practical guide to technical leadership without pretending management is the only path.",
            "whyRead": "Good for senior engineers balancing influence, execution, mentoring, and judgment.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "The Staff Engineer's Path explains that senior technical leadership is less about being the best "
                "individual contributor in every room and more about changing the quality of decisions around you. "
                "Reilly covers technical strategy, project leadership, communication, sponsorship, glue work, and "
                "the trap of becoming a bottleneck. The book is especially useful because it treats influence as a "
                "craft. Staff engineers create context, make tradeoffs visible, align people around a path, and "
                "notice risks before they become expensive. They also need boundaries: saying yes to every urgent "
                "request can make them indispensable in the worst possible way. The strongest lesson is to choose "
                "where your attention compounds. Good staff work helps many people move with more clarity."
            ),
            "keyIdeas": [
                "Technical leadership is multiplied judgment, not heroic solo output.",
                "Make tradeoffs and decision context explicit.",
                "Avoid becoming the routing layer for every problem.",
                "Invest in work that raises the capability of the group.",
            ],
            "tryToday": "Write one decision note that makes options, tradeoffs, and recommendation clear.",
        },
        {
            "title": "A Philosophy of Software Design",
            "author": "John Ousterhout",
            "summary": "A compact argument for reducing complexity through deep modules and clear interfaces.",
            "whyRead": "Useful when code feels easy to add to but hard to reason about later.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "A Philosophy of Software Design focuses on complexity as the central enemy of software. "
                "Ousterhout distinguishes between tactical programming, where you patch the next issue quickly, "
                "and strategic programming, where you spend time preserving simplicity. One of the book's strongest "
                "ideas is deep modules: interfaces should be simple while hiding substantial implementation detail. "
                "Shallow modules, by contrast, expose almost as much complexity as they contain. The book also "
                "warns against information leakage, needless special cases, and comments that repeat code instead "
                "of explaining intent. It is practical because it gives vocabulary for code review. Instead of "
                "arguing taste, you can ask whether a change reduces cognitive load, hides complexity well, and "
                "keeps future changes easier."
            ),
            "keyIdeas": [
                "Complexity accumulates quietly and must be managed deliberately.",
                "Prefer deep modules with simple interfaces.",
                "Design twice before committing to an interface.",
                "Use comments to capture intent and non-obvious reasoning.",
            ],
            "tryToday": "Find one shallow helper and ask whether it hides enough complexity to deserve existing.",
        },
        {
            "title": "Turn the Ship Around!",
            "author": "L. David Marquet",
            "summary": "A leadership story about moving from command-and-control to intent-based ownership.",
            "whyRead": "Useful when you want teams to make better decisions without waiting for permission.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Turn the Ship Around! argues that leaders create stronger organizations by moving authority to "
                "the people closest to the information. Marquet describes replacing permission-seeking language "
                "with intent: instead of asking to do something, people say what they intend to do and why. That "
                "small shift forces clarity, encourages ownership, and lets leaders inspect thinking rather than "
                "micromanage action. The model depends on competence and clarity. People need enough skill to make "
                "good calls and enough context to know what good means. For engineering teams, this maps cleanly to "
                "incident response, design decisions, and delivery tradeoffs. A team that understands the goal and "
                "has the skills can move faster than one waiting for every approval."
            ),
            "keyIdeas": [
                "Push authority to where the information is.",
                "Use intent language to surface reasoning before action.",
                "Autonomy needs both competence and clarity.",
                "Leadership is designing conditions for better decisions.",
            ],
            "tryToday": "Replace one approval request with an intent statement and the reasoning behind it.",
        },
        {
            "title": "The Pragmatic Programmer",
            "author": "David Thomas and Andrew Hunt",
            "summary": "A durable collection of habits for writing, maintaining, and thinking about software well.",
            "whyRead": "Good when you want sharp reminders about craft, ownership, and practical judgment.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "The Pragmatic Programmer is less a single thesis than a set of engineering instincts. It pushes "
                "developers to take responsibility for their work, avoid broken windows, automate repetitive tasks, "
                "learn continuously, and keep designs flexible. The book's advice holds up because it lives at the "
                "level of habits: do not duplicate knowledge, make code easy to change, test assumptions, use plain "
                "text where possible, and treat estimates as communication rather than prophecy. It also encourages "
                "active thinking. Good programmers do not just follow process; they notice friction, improve tools, "
                "and choose techniques that fit the problem. For a working codebase, the useful question is simple: "
                "what small act would leave the system easier to understand tomorrow?"
            ),
            "keyIdeas": [
                "Own the quality and consequences of your work.",
                "Avoid duplicated knowledge and hidden assumptions.",
                "Automate the boring, error-prone parts.",
                "Keep learning and adapting your tools.",
            ],
            "tryToday": "Remove one repeated manual step from your workflow or write down how to automate it.",
        },
        {
            "title": "The Manager's Path",
            "author": "Camille Fournier",
            "summary": "A grounded guide to engineering management from mentoring through senior leadership.",
            "whyRead": "Useful for understanding what good technical management should provide to teams.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "The Manager's Path explains engineering leadership as a progression of responsibilities: mentoring, "
                "tech leading, managing individuals, managing teams, and leading organizations. Fournier is direct "
                "about the work: managers create clarity, give feedback, grow people, handle conflict, and make "
                "execution sustainable. The book is useful even for non-managers because it clarifies what support "
                "healthy teams should expect. Good management is not status meetings and vague encouragement; it is "
                "the removal of ambiguity, the development of people, and the creation of conditions where teams can "
                "make commitments they can keep. It also shows why tech leads and managers need a clean partnership. "
                "Delivery suffers when ownership of technical direction, people growth, and priorities is fuzzy."
            ),
            "keyIdeas": [
                "Management is a craft of clarity, feedback, and context.",
                "Tech leads and managers need explicit ownership boundaries.",
                "People development is part of delivery health.",
                "Sustainable execution beats constant urgency.",
            ],
            "tryToday": "Name one ambiguity your team is carrying and decide who owns clearing it.",
        },
        {
            "title": "Factfulness",
            "author": "Hans Rosling, Ola Rosling, and Anna Rosling Ronnlund",
            "summary": "A clear guide to reading the world with better data and fewer dramatic assumptions.",
            "whyRead": "Useful when headlines make the world feel simpler, scarier, or more divided than it is.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Factfulness is about replacing reflexive pessimism and snap judgments with a calmer habit of "
                "checking proportions, trends, and base rates. The authors describe common instincts that distort "
                "how people read the world: dividing everything into two camps, noticing only bad news, assuming "
                "straight-line trends, or blaming a single cause. The book is not naive optimism. It asks you to "
                "look at data carefully enough to notice both progress and real problems. That makes it useful for "
                "general knowledge because it gives a practical mental toolkit for news, policy, health, economics, "
                "and global development. The everyday lesson is simple: before reacting, ask what the comparison "
                "set is, whether the trend is changing, and what the data actually says."
            ),
            "keyIdeas": [
                "Check trends and proportions before trusting a dramatic impression.",
                "Avoid dividing complex issues into only two groups.",
                "Progress and serious problems can both be true at the same time.",
                "Use data as a thinking aid, not as decoration for a fixed opinion.",
            ],
            "tryToday": "Pick one surprising headline and look for the long-term trend behind it.",
        },
        {
            "title": "A Short History of Nearly Everything",
            "author": "Bill Bryson",
            "summary": "An accessible tour through science, discovery, geology, biology, and the scale of deep time.",
            "whyRead": "Good for widening general knowledge without turning the morning read into homework.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "A Short History of Nearly Everything is a broad, readable journey through how humans came to "
                "understand the universe, Earth, life, and ourselves. Bryson moves from atoms and astronomy to "
                "fossils, volcanoes, oceans, cells, and extinction, often pausing on the strange human stories "
                "behind scientific discoveries. The value of the book is not memorising facts. It helps you feel "
                "the scale of things: how old the planet is, how recent humans are, how much luck and observation "
                "sit behind ordinary knowledge, and how much remains unknown. It is a good Daily Briefing pick "
                "because it gives the day a wider frame than tasks and tickets. A few pages can make familiar life "
                "feel freshly improbable."
            ),
            "keyIdeas": [
                "Scientific knowledge is built from curiosity, error, rivalry, and patient evidence.",
                "Deep time changes how ordinary human concerns feel.",
                "The natural world is both more fragile and more astonishing than it appears.",
                "Good explanations make complex ideas easier without making them shallow.",
            ],
            "tryToday": "Learn one fact about the age, scale, or origin of something you use every day.",
        },
        {
            "title": "Sapiens",
            "author": "Yuval Noah Harari",
            "summary": "A sweeping history of how humans built shared stories, societies, economies, and institutions.",
            "whyRead": "Useful for connecting everyday systems to longer patterns in culture and history.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Sapiens looks at human history through big shifts: cognitive, agricultural, imperial, scientific, "
                "and economic. One of its central ideas is that humans coordinate at scale through shared stories: "
                "money, nations, companies, laws, rights, and institutions all depend on collective belief. The book "
                "is intentionally broad, so it is best read as a set of lenses rather than a final answer to every "
                "historical debate. Its strength for general knowledge is that it connects biology, myth, economics, "
                "power, and technology into one conversation. It helps you ask why certain systems feel inevitable "
                "when they are actually built, maintained, and changed by people."
            ),
            "keyIdeas": [
                "Shared stories let humans cooperate at very large scale.",
                "History often changes through new systems of belief and coordination.",
                "Progress can create new tradeoffs rather than only solving old problems.",
                "Institutions feel solid because many people keep acting as if they are.",
            ],
            "tryToday": "Notice one invisible shared agreement that quietly shapes your day.",
        },
        {
            "title": "Prisoners of Geography",
            "author": "Tim Marshall",
            "summary": "A geopolitical primer on how mountains, rivers, seas, borders, and resources shape nations.",
            "whyRead": "Helpful when world news needs more map-awareness and less noise.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Prisoners of Geography explains international politics through the physical constraints that "
                "countries operate within. Geography is not destiny, but it shapes incentives: ports matter, energy "
                "routes matter, mountains protect and divide, and flat plains can make borders feel exposed. The book "
                "is useful because it brings a map back into world news. Conflicts, alliances, trade routes, and "
                "security decisions often make more sense when you ask what terrain, resources, and access points are "
                "in play. It is a good general-knowledge rotation book because it turns abstract foreign policy into "
                "something more concrete and spatial."
            ),
            "keyIdeas": [
                "Geography influences national choices even when leaders change.",
                "Ports, choke points, borders, energy routes, and terrain shape strategy.",
                "Maps can explain why some problems keep returning.",
                "Geography is a constraint, not a complete explanation.",
            ],
            "tryToday": "Open a map for one world-news story and identify the nearest border, port, or route that matters.",
        },
        {
            "title": "The Art of Travel",
            "author": "Alain de Botton",
            "summary": "A reflective book on why we travel, what we notice, and how places change attention.",
            "whyRead": "Good when you want travel inspiration that is thoughtful rather than checklist-driven.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "The Art of Travel treats travel as a way of paying attention, not only a way of moving between "
                "destinations. De Botton explores anticipation, curiosity, beauty, unfamiliarity, art, hotels, "
                "landscapes, and the strange fact that we carry our own moods with us wherever we go. The book is "
                "useful because it makes travel less about collecting places and more about changing how you see. "
                "It also works when you are not travelling. A commuter street, local cafe, or park can become more "
                "interesting when approached with the attention people usually reserve for somewhere far away. For "
                "a Daily Briefing, it adds a softer, more observant rhythm to the morning."
            ),
            "keyIdeas": [
                "Travel changes attention as much as location.",
                "Anticipation and memory are part of the journey.",
                "Unfamiliar places can reveal familiar habits.",
                "You can practise a traveller's attention close to home.",
            ],
            "tryToday": "Look at one familiar route as if you were visiting it for the first time.",
        },
        {
            "title": "The Geography of Bliss",
            "author": "Eric Weiner",
            "summary": "A travel memoir that explores how different cultures understand happiness and meaning.",
            "whyRead": "Good for mixing travel, culture, and personal reflection in a light but thoughtful way.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "The Geography of Bliss follows a search for what happiness looks like in different places. Weiner "
                "uses travel writing, interviews, humour, and social observation to compare how culture shapes "
                "contentment. The point is not that one country has solved happiness. It is that environment, "
                "expectations, relationships, trust, pace, money, weather, and public life all influence what people "
                "call a good life. The book is useful for personal development because it makes happiness feel less "
                "like a private productivity project and more like a relationship between habits, community, place, "
                "and values. It is also a pleasant reminder that travel can be a way to question your defaults."
            ),
            "keyIdeas": [
                "Different cultures define and support happiness differently.",
                "Place, trust, pace, and relationships shape wellbeing.",
                "Travel can reveal assumptions you did not know you had.",
                "Happiness is not only an individual optimization problem.",
            ],
            "tryToday": "Borrow one small wellbeing habit from another culture and try it without over-engineering it.",
        },
        {
            "title": "In Patagonia",
            "author": "Bruce Chatwin",
            "summary": "A classic travel narrative built from fragments, encounters, landscape, myth, and memory.",
            "whyRead": "Useful when you want a more literary travel pick that feels different from advice books.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "In Patagonia is less a conventional itinerary and more a collage of place, story, rumour, and "
                "encounter. Chatwin moves through remote landscapes and eccentric histories, collecting fragments "
                "that make Patagonia feel both real and mythic. The book's value is its texture. It shows travel "
                "writing as attention to landscape, voice, silence, and odd human detail rather than a list of "
                "recommendations. In the Daily Briefing rotation, it breaks the pattern of practical nonfiction and "
                "adds a little wonder. It is a reminder that not every useful book needs to tell you how to improve; "
                "some widen the imagination by taking you somewhere unfamiliar."
            ),
            "keyIdeas": [
                "A place can be understood through fragments and encounters.",
                "Travel writing can preserve mystery instead of explaining everything.",
                "Landscape shapes the mood and memory of a story.",
                "Curiosity can be a valid reason to read.",
            ],
            "tryToday": "Write three observations about a place without turning them into advice.",
        },
        {
            "title": "The Psychology of Money",
            "author": "Morgan Housel",
            "summary": "A practical look at how behavior, risk, luck, and time shape financial decisions.",
            "whyRead": "Useful personal finance without turning money into spreadsheets only.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "The Psychology of Money argues that financial success depends heavily on behavior. Knowledge "
                "matters, but patience, humility, risk awareness, and emotional control often matter more. Housel "
                "explains why two people can make different financial choices because they lived through different "
                "histories, why compounding needs time and restraint, and why enough is a powerful concept. The book "
                "is useful for personal development because it frames money as part of life design: security, "
                "flexibility, independence, and peace of mind. It encourages decisions that survive uncertainty "
                "instead of decisions that look clever only in hindsight."
            ),
            "keyIdeas": [
                "Personal finance is deeply behavioral.",
                "Compounding rewards time, restraint, and consistency.",
                "Knowing what is enough protects better decisions.",
                "Good plans leave room for uncertainty and mistakes.",
            ],
            "tryToday": "Name one money decision where peace of mind matters more than optimization.",
        },
        {
            "title": "Range",
            "author": "David Epstein",
            "summary": "A case for broad learning, experimentation, and connecting ideas across domains.",
            "whyRead": "Good when personal growth feels too narrowly optimized.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Range challenges the idea that early specialization is always the best path. Epstein argues that "
                "many complex fields reward breadth, experimentation, analogical thinking, and the ability to move "
                "ideas between domains. The book does not reject expertise. It says that in uncertain or messy "
                "environments, people often benefit from sampling widely before narrowing, and from keeping enough "
                "range to recognize patterns others miss. As a personal-development pick, it gives permission to "
                "learn beyond the immediate job title or current goal. It fits a Daily Briefing because it nudges "
                "the reader toward curiosity, cross-training, and less anxious comparison."
            ),
            "keyIdeas": [
                "Broad sampling can improve judgment in complex environments.",
                "Analogies help transfer ideas between fields.",
                "Late specialization can still produce strong expertise.",
                "Curiosity outside your lane can become practical advantage.",
            ],
            "tryToday": "Connect one idea from a hobby, book, or trip to a current problem.",
        },
        {
            "title": "Braiding Sweetgrass",
            "author": "Robin Wall Kimmerer",
            "summary": "A blend of ecology, Indigenous knowledge, science, gratitude, and attention to the living world.",
            "whyRead": "Good for a calmer nature-and-perspective day in the reading rotation.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "Braiding Sweetgrass brings together botany, Indigenous wisdom, teaching, motherhood, restoration, "
                "and gratitude. Kimmerer writes about plants and ecosystems with scientific precision and emotional "
                "generosity, asking what it would mean to relate to the natural world through reciprocity rather "
                "than extraction alone. The book is a useful counterweight to productivity-heavy reading because it "
                "slows attention down. It makes ordinary plants, seasons, gifts, waste, and care feel ethically and "
                "beautifully connected. For the Daily Briefing, it adds nature, reflection, and a more grounded way "
                "to think about responsibility."
            ),
            "keyIdeas": [
                "Science and traditional knowledge can deepen each other.",
                "Reciprocity changes how responsibility feels.",
                "Attention is a form of respect.",
                "Gratitude can be practical, not sentimental.",
            ],
            "tryToday": "Notice one living thing you usually pass without naming or thanking.",
        },
        {
            "title": "The Creative Act",
            "author": "Rick Rubin",
            "summary": "A reflective guide to creativity as attention, receptivity, practice, and editing.",
            "whyRead": "Useful when you want a creative reset without making creativity feel corporate.",
            "readingTimeMinutes": 5,
            "detailedSummary": (
                "The Creative Act treats creativity less as a rare talent and more as a way of being available to "
                "ideas. Rubin writes about attention, taste, patience, experimentation, editing, and the value of "
                "making space for signal to appear. The book is not a step-by-step system; it is more like a set of "
                "meditations for people who make things. In a mixed Book of the Day rotation, it helps balance "
                "practical work books with something more inward and imaginative. Its daily usefulness is simple: "
                "create conditions where you notice more, judge a little later, and keep refining what feels alive."
            ),
            "keyIdeas": [
                "Creativity starts with attention and receptivity.",
                "Taste develops through making, listening, and revising.",
                "Editing is part of creation, not the opposite of it.",
                "Space and quiet can improve the quality of ideas.",
            ],
            "tryToday": "Spend ten minutes collecting ideas before judging whether any of them are good.",
        },
    ]

    topics_by_title = {
        "Atomic Habits": "Personal development",
        "Deep Work": "Productivity",
        "Team Topologies": "Work & leadership",
        "The Design of Everyday Things": "Design & creativity",
        "Decoding Your Dog": "Dog training",
        "Accelerate": "Work & leadership",
        "Thinking in Systems": "General knowledge",
        "The Staff Engineer's Path": "Work & leadership",
        "A Philosophy of Software Design": "Work & leadership",
        "Turn the Ship Around!": "Work & leadership",
        "The Pragmatic Programmer": "Work & leadership",
        "The Manager's Path": "Work & leadership",
        "Factfulness": "General knowledge",
        "A Short History of Nearly Everything": "General knowledge",
        "Sapiens": "General knowledge",
        "Prisoners of Geography": "General knowledge",
        "The Art of Travel": "Travel",
        "The Geography of Bliss": "Travel",
        "In Patagonia": "Travel",
        "The Psychology of Money": "Personal finance",
        "Range": "Personal development",
        "Braiding Sweetgrass": "Nature",
        "The Creative Act": "Design & creativity",
    }
    for book in books:
        book["topic"] = topics_by_title.get(book["title"], "General reading")
    return books


def _build_book_of_the_day(now: datetime) -> dict[str, Any]:
    books = _book_catalog()
    day_index = _daily_rotation_index(now, len(books))
    selected = dict(books[day_index])
    selected["label"] = "Book of the Day"
    return selected


def _cached_news() -> dict[str, Any] | None:
    if _news_cache is None:
        return None
    generated_at = _news_cache.get("generatedAt")
    if not isinstance(generated_at, str):
        return None
    try:
        generated = datetime.fromisoformat(generated_at)
    except ValueError:
        return None
    ttl = int(os.environ.get("NEWS_DASHBOARD_CACHE_SECONDS", str(NEWS_CACHE_SECONDS)))
    if (_now_utc() - generated).total_seconds() > ttl:
        return None
    payload = dict(_news_cache)
    payload["cached"] = True
    return payload


def get_news_dashboard() -> dict[str, Any]:
    global _news_cache

    cached = _cached_news()
    if cached is not None:
        return cached

    now = _now_utc()
    articles_by_category: dict[str, list[dict[str, Any]]] = {category_id: [] for category_id, _, _ in CATEGORY_ORDER}
    errors_by_category: dict[str, list[str]] = {category_id: [] for category_id, _, _ in CATEGORY_ORDER}

    with ThreadPoolExecutor(max_workers=min(8, len(FEEDS))) as executor:
        futures = [executor.submit(_fetch_feed, feed) for feed in FEEDS]
        for future in as_completed(futures):
            feed, articles, error = future.result()
            articles_by_category.setdefault(feed.category_id, []).extend(articles)
            if error:
                errors_by_category.setdefault(feed.category_id, []).append(error)

    categories: list[dict[str, Any]] = []
    for category_id, label, description in CATEGORY_ORDER:
        seen: set[str] = set()
        unique_articles: list[dict[str, Any]] = []
        for article in sorted(articles_by_category.get(category_id, []), key=_article_sort_key, reverse=True):
            dedupe_key = str(article.get("url") or article.get("title") or "").strip().lower()
            if not dedupe_key or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            unique_articles.append(article)
            if len(unique_articles) >= 6:
                break
        categories.append(
            {
                "id": category_id,
                "label": label,
                "description": description,
                "articles": unique_articles,
                "errors": errors_by_category.get(category_id, []),
            }
        )

    training_tips = _build_training_tips(now)
    payload = {
        "source": "rss",
        "generatedAt": now.isoformat(),
        "timezone": "Australia/Melbourne",
        "categories": categories,
        "bookOfTheDay": _build_book_of_the_day(now),
        "trainingTip": training_tips[0],
        "trainingTips": training_tips,
        "error": None,
    }
    _news_cache = dict(payload)
    return payload
