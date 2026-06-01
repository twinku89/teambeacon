from __future__ import annotations

import html
import os
import re
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


def _fetch_feed(feed: NewsFeed) -> tuple[NewsFeed, list[dict[str, Any]], str | None]:
    timeout = int(os.environ.get("NEWS_DASHBOARD_TIMEOUT_SECONDS", str(NEWS_TIMEOUT_SECONDS)))
    request = Request(feed.url, headers={"User-Agent": "TeamBeacon/1.0 news dashboard"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured public feeds only.
            raw = response.read()
    except HTTPError as exc:
        return feed, [], f"{feed.source} returned HTTP {exc.code}."
    except URLError as exc:
        return feed, [], f"{feed.source} request failed: {exc.reason}"
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


def _build_training_tip(now: datetime) -> dict[str, Any]:
    day_index = now.astimezone(_melbourne_timezone()).timetuple().tm_yday % 5
    tips = [
        {
            "title": "Distance-first trigger work",
            "focus": "Keep him far enough from triggers that he can still think, sniff, and take food.",
            "steps": [
                "Start where he notices the trigger but does not bark or lunge.",
                "Mark and reward calm check-ins, then move away before intensity builds.",
                "End after 3 to 5 successful repetitions, not when he is already overloaded.",
            ],
        },
        {
            "title": "Decompression before training",
            "focus": "Give the adolescent brain an outlet before asking for polished behaviour.",
            "steps": [
                "Use a quiet sniff walk or long-line wander before skills work.",
                "Avoid busy dog parks and tight footpaths on high-energy days.",
                "Reward voluntary disengagement from movement, dogs, bikes, and people.",
            ],
        },
        {
            "title": "Short settle reps",
            "focus": "Teach recovery as a skill, especially after excitement.",
            "steps": [
                "Practise mat or place work for 30 to 90 seconds at a time.",
                "Pay for relaxed hips, slow breathing, and head turns back to you.",
                "Release him while he is calm so the pattern stays easy.",
            ],
        },
        {
            "title": "Pattern games around triggers",
            "focus": "Predictable food patterns can lower arousal without forcing confrontation.",
            "steps": [
                "Use one-two-three treat or find-it scatters at safe distance.",
                "Let him turn away after each repetition instead of staring longer.",
                "Increase difficulty by location, duration, or distance, one variable at a time.",
            ],
        },
        {
            "title": "Recovery audit",
            "focus": "A reactive working-line puppy needs sleep and quiet as much as training.",
            "steps": [
                "Track the day after big outings; reactivity often rises when recovery is short.",
                "Use food puzzles or calm chewing after walks to downshift.",
                "Choose one training goal per outing so sessions stay clean.",
            ],
        },
    ]
    return {
        "categoryId": "dogTraining",
        "label": "Dog Training",
        "description": "Daily coaching for a reactive, overstimulated 9-month working-line German Shepherd.",
        **tips[day_index],
        "note": "If reactions escalate, work with a qualified force-free behaviour professional.",
    }


def _daily_rotation_index(now: datetime, item_count: int) -> int:
    local_date = now.astimezone(_melbourne_timezone()).date()
    return (local_date - BOOK_ROTATION_EPOCH).days % item_count


def _build_book_of_the_day(now: datetime) -> dict[str, Any]:
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
    ]
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

    payload = {
        "source": "rss",
        "generatedAt": now.isoformat(),
        "timezone": "Australia/Melbourne",
        "categories": categories,
        "bookOfTheDay": _build_book_of_the_day(now),
        "trainingTip": _build_training_tip(now),
        "error": None,
    }
    _news_cache = dict(payload)
    return payload
