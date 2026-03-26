"""LobsterGym Eval — Task definitions and scoring for OpenClaw evaluation.

Each task defines:
- A natural-language instruction for the agent
- Setup steps (reset state, pre-seed data)
- Verification checks against /state endpoints
- A difficulty level and category

Tasks are grouped by capability:
- browser: browser-automation tasks against lobstergym-web
- api: API-interaction tasks against lobstergym-api
- memory: tasks that test ClawGraph memory persistence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class Category(str, Enum):
    BROWSER = "browser"
    API = "api"
    MEMORY = "memory"
    MULTI = "multi"  # cross-category


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class Check:
    """A single verification check against a state endpoint.

    Args:
        endpoint: URL path to hit (e.g. ``/flights/state``)
        service: Which service to query — ``web`` or ``api``
        field_path: Dot-separated path into the JSON response
        assertion: One of ``exists``, ``equals``, ``contains``,
                   ``length_gte``, ``length_eq``, ``not_empty``
        expected: Expected value for ``equals`` / ``contains`` checks
        description: Human-readable description of what this checks
    """

    endpoint: str
    service: str  # "web" or "api"
    field_path: str
    assertion: str
    expected: Any = None
    description: str = ""


@dataclass
class Task:
    """A single evaluation task.

    Args:
        id: Unique task identifier
        name: Short human-readable name
        instruction: Natural-language instruction sent to the agent
        category: Task category
        difficulty: Difficulty level
        checks: List of verification checks
        setup_reset: Whether to reset state before this task
        tags: Optional tags for filtering
    """

    id: str
    name: str
    instruction: str
    category: Category
    difficulty: Difficulty
    checks: list[Check] = field(default_factory=list)
    setup_reset: bool = True
    tags: list[str] = field(default_factory=list)


# ===================================================================
# Task Registry
# ===================================================================

TASKS: list[Task] = [
    # ----- BROWSER / EASY -----
    Task(
        id="browser-todo-add",
        name="Add a Todo",
        instruction=(
            "Use the browser tool to navigate to http://lobstergym-web:8080/todos. "
            'Add a todo item with the text "Buy lobster food" by typing into the input field and submitting the form. '
            "Confirm the item appears in the list."
        ),
        category=Category.BROWSER,
        difficulty=Difficulty.EASY,
        checks=[
            Check(
                endpoint="/todos/state",
                service="web",
                field_path="items",
                assertion="length_gte",
                expected=1,
                description="At least 1 todo item exists",
            ),
            Check(
                endpoint="/todos/state",
                service="web",
                field_path="items.[].text",
                assertion="contains",
                expected="Buy lobster food",
                description="Todo text matches expected",
            ),
        ],
    ),
    Task(
        id="browser-todo-multi",
        name="Add & Complete Todos",
        instruction=(
            "Use the browser tool to navigate to http://lobstergym-web:8080/todos. "
            'Add three todo items: "Clean the tank", "Feed the shrimp", '
            '"Update the wiki" by typing into the input field and submitting the form for each. '
            'Then mark "Feed the shrimp" as done by clicking its checkbox or done button.'
        ),
        category=Category.BROWSER,
        difficulty=Difficulty.MEDIUM,
        checks=[
            Check(
                endpoint="/todos/state",
                service="web",
                field_path="items",
                assertion="length_eq",
                expected=3,
                description="Exactly 3 todo items",
            ),
            Check(
                endpoint="/todos/state",
                service="web",
                field_path="items.[?done=true]",
                assertion="length_gte",
                expected=1,
                description="At least 1 item is marked done",
            ),
        ],
    ),
    # ----- BROWSER / MEDIUM -----
    Task(
        id="browser-flight-book",
        name="Book a Flight",
        instruction=(
            "Use the browser tool to navigate to http://lobstergym-web:8080/flights. "
            "Fill in the search form with origin SFO, destination JFK, and date 2026-04-10, then submit it. "
            "From the results, book the cheapest flight by clicking its Book button. "
            'On the booking form, enter passenger name "Molty Lobster" and email "molty@openclaw.ai", then submit.'
        ),
        category=Category.BROWSER,
        difficulty=Difficulty.MEDIUM,
        checks=[
            Check(
                endpoint="/flights/state",
                service="web",
                field_path="searches",
                assertion="length_gte",
                expected=1,
                description="At least 1 flight search was made",
            ),
            Check(
                endpoint="/flights/state",
                service="web",
                field_path="bookings",
                assertion="length_eq",
                expected=1,
                description="Exactly 1 booking was made",
            ),
            Check(
                endpoint="/flights/state",
                service="web",
                field_path="bookings.[0].flight_id",
                assertion="equals",
                expected="FL200",
                description="Cheapest flight FL200 was booked",
            ),
            Check(
                endpoint="/flights/state",
                service="web",
                field_path="bookings.[0].passenger_name",
                assertion="contains",
                expected="Molty",
                description="Passenger name includes Molty",
            ),
        ],
    ),
    Task(
        id="browser-contact-form",
        name="Submit Contact Form",
        instruction=(
            "Use the browser tool to navigate to http://lobstergym-web:8080/contact. "
            "This is a multi-step form. On each step, fill in the fields and click Next or Submit: "
            'Step 1 — Name: "Pinchy McSnip", Email: "pinchy@reef.com". '
            'Step 2 — Subject: "Partnership Inquiry", '
            'Message: "I would like to discuss a potential partnership for reef conservation." '
            "Then submit the form."
        ),
        category=Category.BROWSER,
        difficulty=Difficulty.MEDIUM,
        checks=[
            Check(
                endpoint="/contact/state",
                service="web",
                field_path="submissions",
                assertion="length_eq",
                expected=1,
                description="Exactly 1 submission",
            ),
            Check(
                endpoint="/contact/state",
                service="web",
                field_path="submissions.[0].name",
                assertion="contains",
                expected="Pinchy",
                description="Name contains Pinchy",
            ),
            Check(
                endpoint="/contact/state",
                service="web",
                field_path="submissions.[0].subject",
                assertion="contains",
                expected="Partnership",
                description="Subject mentions Partnership",
            ),
        ],
    ),
    # ----- BROWSER / HARD -----
    Task(
        id="browser-shop-checkout",
        name="E-Commerce Checkout",
        instruction=(
            "Use the browser tool to navigate to http://lobstergym-web:8080/shop. "
            'Find the "Lobster Plushie" product and add it to the cart twice (qty 2). '
            'Find the "Reef Keyboard" product and add it to the cart once (qty 1). '
            "Then go to the cart, proceed to checkout, and place the order. "
            'Ship to name "Molty Lobster", address "42 Ocean Drive, Coral Bay, CB 12345".'
        ),
        category=Category.BROWSER,
        difficulty=Difficulty.HARD,
        checks=[
            Check(
                endpoint="/shop/state",
                service="web",
                field_path="orders",
                assertion="length_eq",
                expected=1,
                description="Exactly 1 order placed",
            ),
            Check(
                endpoint="/shop/state",
                service="web",
                field_path="orders.[0].items",
                assertion="length_eq",
                expected=2,
                description="Order has 2 line items",
            ),
            Check(
                endpoint="/shop/state",
                service="web",
                field_path="orders.[0].shipping_name",
                assertion="contains",
                expected="Molty",
                description="Shipped to Molty",
            ),
            Check(
                endpoint="/shop/state",
                service="web",
                field_path="cart",
                assertion="length_eq",
                expected=0,
                description="Cart is empty after checkout",
            ),
        ],
    ),
    # ----- API / EASY -----
    Task(
        id="api-weather-check",
        name="Check Weather",
        instruction=(
            "IMPORTANT: Do NOT use web_fetch — it will fail on internal hosts. "
            "Use your exec tool to run curl commands instead. "
            "Run these two commands with exec: "
            "curl -s http://lobstergym-api:8090/weather/San%20Francisco "
            "and curl -s http://lobstergym-api:8090/weather/Tokyo "
            "Tell me the temperature and conditions in both cities."
        ),
        category=Category.API,
        difficulty=Difficulty.EASY,
        checks=[
            Check(
                endpoint="/weather/state",
                service="api",
                field_path="queries",
                assertion="length_gte",
                expected=2,
                description="At least 2 weather queries made",
            ),
        ],
    ),
    Task(
        id="api-email-read",
        name="Read Emails",
        instruction=(
            "IMPORTANT: Do NOT use web_fetch — it will fail on internal hosts. "
            "Use your exec tool to run curl commands instead. "
            "Run: exec curl -s http://lobstergym-api:8090/email/inbox "
            "Then read each email by its id: exec curl -s http://lobstergym-api:8090/email/inbox/<id> "
            "Give me a summary of what needs my attention."
        ),
        category=Category.API,
        difficulty=Difficulty.EASY,
        checks=[
            Check(
                endpoint="/email/state",
                service="api",
                field_path="inbox.[?read=true]",
                assertion="length_gte",
                expected=2,
                description="At least 2 emails marked as read",
            ),
        ],
    ),
    # ----- API / MEDIUM -----
    Task(
        id="api-calendar-schedule",
        name="Schedule Meeting",
        instruction=(
            "IMPORTANT: Do NOT use web_fetch — it will fail on internal hosts. "
            "Use your exec tool to run curl commands instead. "
            "1. Check my calendar: exec curl -s http://lobstergym-api:8090/calendar/events "
            '2. Schedule a new event: exec curl -s -X POST http://lobstergym-api:8090/calendar/events '
            '-H "Content-Type: application/json" '
            '-d \'{"title":"ClawGraph Demo","date":"2026-04-10","time":"14:00","duration_minutes":90,"description":"Demo graph memory to the team"}\' '
            "3. Tell me the full schedule for that day."
        ),
        category=Category.API,
        difficulty=Difficulty.MEDIUM,
        checks=[
            Check(
                endpoint="/calendar/state",
                service="api",
                field_path="events",
                assertion="length_gte",
                expected=4,
                description="At least 4 events (3 seeded + 1 new)",
            ),
            Check(
                endpoint="/calendar/state",
                service="api",
                field_path="events.[].title",
                assertion="contains",
                expected="ClawGraph Demo",
                description="New event title matches",
            ),
        ],
    ),
    Task(
        id="api-email-reply",
        name="Reply to Email",
        instruction=(
            "IMPORTANT: Do NOT use web_fetch — it will fail on internal hosts. "
            "Use your exec tool to run curl commands instead. "
            "1. Read the inbox: exec curl -s http://lobstergym-api:8090/email/inbox "
            "Then read the email from boss@acme.com by its id. "
            "2. Send a reply: exec curl -s -X POST http://lobstergym-api:8090/email/send "
            '-H "Content-Type: application/json" '
            '-d \'{"to":"boss@acme.com","subject":"Re: Q1 Report Needed","body":"..."}\' '
            "confirming you will have the Q1 report ready by Friday."
        ),
        category=Category.API,
        difficulty=Difficulty.MEDIUM,
        checks=[
            Check(
                endpoint="/email/state",
                service="api",
                field_path="inbox.[0].read",
                assertion="equals",
                expected=True,
                description="Boss email was read",
            ),
            Check(
                endpoint="/email/state",
                service="api",
                field_path="sent",
                assertion="length_gte",
                expected=1,
                description="At least 1 email sent",
            ),
            Check(
                endpoint="/email/state",
                service="api",
                field_path="sent.[0].to",
                assertion="contains",
                expected="boss@acme.com",
                description="Reply sent to boss",
            ),
        ],
    ),
    # ----- API / HARD -----
    Task(
        id="api-notes-organize",
        name="Organize Notes",
        instruction=(
            "IMPORTANT: Do NOT use web_fetch — it will fail on internal hosts. "
            "Use your exec tool to run curl commands instead. "
            "1. List all notes: exec curl -s http://lobstergym-api:8090/notes "
            "2. Create a new note: exec curl -s -X POST http://lobstergym-api:8090/notes "
            "-H 'Content-Type: application/json' "
            "-d '{\"title\":\"Meeting Notes - April 10\",\"content\":\"Summary of April 10 meetings\",\"tags\":[\"meetings\",\"april\"]}' "
            "3. Update the existing 'Project Ideas' note (id note-001): "
            "exec curl -s -X PATCH http://lobstergym-api:8090/notes/note-001 "
            "-H 'Content-Type: application/json' "
            "-d '{\"content\":\"... existing content ... 4. LobsterGym evaluation framework\"}' "
            "Read the note first to get the existing content before updating."
        ),
        category=Category.API,
        difficulty=Difficulty.HARD,
        checks=[
            Check(
                endpoint="/notes/state",
                service="api",
                field_path="notes",
                assertion="length_gte",
                expected=2,
                description="At least 2 notes exist",
            ),
            Check(
                endpoint="/notes/state",
                service="api",
                field_path="notes.[].title",
                assertion="contains",
                expected="Meeting Notes",
                description="New meeting notes created",
            ),
            Check(
                endpoint="/notes/state",
                service="api",
                field_path="notes.[?id='note-001'].content",
                assertion="contains",
                expected="LobsterGym",
                description="Project Ideas note updated",
            ),
        ],
    ),
    # ----- MEMORY / EASY -----
    Task(
        id="memory-store-recall",
        name="Store & Recall Fact",
        instruction=(
            "Use your ClawGraph memory skill to store this fact: "
            '"Alice is a senior engineer at Acme Corp who specializes in graph databases." '
            "Then query your memory to recall: Who works at Acme Corp?"
        ),
        category=Category.MEMORY,
        difficulty=Difficulty.EASY,
        tags=["clawgraph"],
        checks=[
            # Memory checks are done via clawgraph export, handled specially
            Check(
                endpoint="clawgraph://export",
                service="clawgraph",
                field_path="entities",
                assertion="length_gte",
                expected=1,
                description="At least 1 entity stored in memory",
            ),
        ],
    ),
    # ----- MULTI / HARD -----
    Task(
        id="multi-email-calendar-memory",
        name="Email Triage + Calendar + Memory",
        instruction=(
            "IMPORTANT: Do NOT use web_fetch — it will fail on internal hosts. "
            "Use your exec tool to run curl commands instead. "
            "1. Read all emails: exec curl -s http://lobstergym-api:8090/email/inbox "
            "Then read each by id: exec curl -s http://lobstergym-api:8090/email/inbox/<id> "
            "2. The email from boss@acme.com requires a meeting — schedule it: "
            "exec curl -s -X POST http://lobstergym-api:8090/calendar/events "
            '-H "Content-Type: application/json" '
            '-d \'{"title":"Q1 Report Review","date":"2026-04-12","time":"10:00","duration_minutes":60}\' '
            "3. Reply to boss confirming: exec curl -s -X POST http://lobstergym-api:8090/email/send "
            '-H "Content-Type: application/json" '
            '-d \'{"to":"boss@acme.com","subject":"Re: Q1 Report Needed","body":"Meeting scheduled for April 12 at 10am."}\' '
            "4. Use your ClawGraph memory skill to remember that "
            '"boss@acme.com requested the Q1 report, and a review meeting is scheduled for April 12".'
        ),
        category=Category.MULTI,
        difficulty=Difficulty.HARD,
        tags=["clawgraph"],
        checks=[
            Check(
                endpoint="/email/state",
                service="api",
                field_path="inbox.[0].read",
                assertion="equals",
                expected=True,
                description="Boss email read",
            ),
            Check(
                endpoint="/calendar/state",
                service="api",
                field_path="events.[].title",
                assertion="contains",
                expected="Q1",
                description="Q1 meeting scheduled",
            ),
            Check(
                endpoint="/email/state",
                service="api",
                field_path="sent",
                assertion="length_gte",
                expected=1,
                description="Reply sent",
            ),
            Check(
                endpoint="clawgraph://export",
                service="clawgraph",
                field_path="entities",
                assertion="length_gte",
                expected=1,
                description="Memory stored",
            ),
        ],
    ),
]


def get_tasks(
    category: Category | None = None,
    difficulty: Difficulty | None = None,
    tags: list[str] | None = None,
) -> list[Task]:
    """Filter tasks by category, difficulty, and/or tags.

    Args:
        category: Filter by category.
        difficulty: Filter by difficulty.
        tags: Filter by tags (any match).

    Returns:
        Matching tasks.
    """
    result = TASKS
    if category:
        result = [t for t in result if t.category == category]
    if difficulty:
        result = [t for t in result if t.difficulty == difficulty]
    if tags:
        result = [t for t in result if any(tag in t.tags for tag in tags)]
    return result
