"""LobsterGym API — Mock REST integrations for OpenClaw agent evaluation.

Simulates common API services (weather, calendar, email, notes) that an
AI agent might interact with via ``exec`` (curl) or ``web_fetch`` tools.
Each service has a ``/state`` endpoint the eval harness uses to verify
the agent's actions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="LobsterGym API",
    description="Mock API integrations for OpenClaw agent evaluation",
    version="0.1.0",
)

# ===================================================================
# Shared models
# ===================================================================


class MessageResponse(BaseModel):
    """Generic response for mutating endpoints."""
    status: str = "ok"
    id: str | None = None
    message: str | None = None


# ===================================================================
# 1. Weather API
# ===================================================================

WEATHER_DATA: dict[str, dict[str, Any]] = {
    "san francisco": {"temp_f": 62, "temp_c": 17, "condition": "Foggy", "humidity": 78, "wind_mph": 12},
    "new york": {"temp_f": 45, "temp_c": 7, "condition": "Cloudy", "humidity": 65, "wind_mph": 8},
    "london": {"temp_f": 50, "temp_c": 10, "condition": "Rainy", "humidity": 85, "wind_mph": 15},
    "tokyo": {"temp_f": 68, "temp_c": 20, "condition": "Sunny", "humidity": 55, "wind_mph": 5},
    "sydney": {"temp_f": 78, "temp_c": 26, "condition": "Partly Cloudy", "humidity": 60, "wind_mph": 10},
}

weather_queries: list[dict[str, Any]] = []


@app.get("/weather/{city}")
def get_weather(city: str) -> dict[str, Any]:
    """Get current weather for a city."""
    key = city.lower().strip()
    weather_queries.append({"city": city, "queried_at": datetime.utcnow().isoformat()})
    if key not in WEATHER_DATA:
        raise HTTPException(status_code=404, detail=f"No weather data for '{city}'")
    return {"city": city, **WEATHER_DATA[key]}


@app.get("/weather/state")
def weather_state() -> dict[str, Any]:
    """Eval harness inspection."""
    return {"queries": weather_queries}


# ===================================================================
# 2. Calendar API
# ===================================================================


class CalendarEvent(BaseModel):
    """Calendar event input."""
    title: str
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    duration_minutes: int = 60
    description: str = ""


calendar_events: list[dict[str, Any]] = [
    {
        "id": "evt-001",
        "title": "Team Standup",
        "date": "2026-04-10",
        "time": "09:00",
        "duration_minutes": 30,
        "description": "Daily standup with the lobster crew",
    },
    {
        "id": "evt-002",
        "title": "Lunch with Molty",
        "date": "2026-04-10",
        "time": "12:00",
        "duration_minutes": 60,
        "description": "Reef Café, table for two",
    },
    {
        "id": "evt-003",
        "title": "Deploy v2.0",
        "date": "2026-04-11",
        "time": "15:00",
        "duration_minutes": 120,
        "description": "Production deployment with rollback plan",
    },
]


@app.get("/calendar/events")
def list_events(date: str | None = None) -> dict[str, Any]:
    """List calendar events, optionally filtered by date."""
    events = calendar_events
    if date:
        events = [e for e in events if e["date"] == date]
    return {"events": events, "count": len(events)}


@app.get("/calendar/events/{event_id}")
def get_event(event_id: str) -> dict[str, Any]:
    """Get a specific event."""
    event = next((e for e in calendar_events if e["id"] == event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.post("/calendar/events")
def create_event(event: CalendarEvent) -> MessageResponse:
    """Create a new calendar event."""
    new_event = {
        "id": f"evt-{uuid.uuid4().hex[:6]}",
        **event.model_dump(),
        "created_at": datetime.utcnow().isoformat(),
    }
    calendar_events.append(new_event)
    return MessageResponse(id=new_event["id"], message="Event created")


@app.delete("/calendar/events/{event_id}")
def delete_event(event_id: str) -> MessageResponse:
    """Delete a calendar event."""
    global calendar_events
    before = len(calendar_events)
    calendar_events = [e for e in calendar_events if e["id"] != event_id]
    if len(calendar_events) == before:
        raise HTTPException(status_code=404, detail="Event not found")
    return MessageResponse(message="Event deleted")


@app.get("/calendar/state")
def calendar_state() -> dict[str, Any]:
    """Eval harness inspection."""
    return {"events": calendar_events}


# ===================================================================
# 3. Email API
# ===================================================================


class EmailSend(BaseModel):
    """Email send input."""
    to: str
    subject: str
    body: str


email_inbox: list[dict[str, Any]] = [
    {
        "id": "mail-001",
        "from": "boss@acme.com",
        "to": "me@lobster.ai",
        "subject": "Q1 Report Needed",
        "body": "Hi, can you prepare the Q1 report by end of week? Include revenue and churn numbers.",
        "date": "2026-04-09",
        "read": False,
    },
    {
        "id": "mail-002",
        "from": "hr@acme.com",
        "to": "me@lobster.ai",
        "subject": "Team Offsite - RSVP",
        "body": "The team offsite is April 15. Please RSVP by replying to this email.",
        "date": "2026-04-08",
        "read": True,
    },
    {
        "id": "mail-003",
        "from": "newsletter@techdigest.com",
        "to": "me@lobster.ai",
        "subject": "This Week in AI",
        "body": "Top stories: LLM costs drop 50%, new graph databases, lobster-themed AI assistants trending.",
        "date": "2026-04-09",
        "read": False,
    },
]

email_sent: list[dict[str, Any]] = []


@app.get("/email/inbox")
def list_inbox(unread_only: bool = False) -> dict[str, Any]:
    """List inbox emails."""
    emails = email_inbox
    if unread_only:
        emails = [e for e in emails if not e["read"]]
    return {"emails": emails, "count": len(emails)}


@app.get("/email/inbox/{email_id}")
def get_email(email_id: str) -> dict[str, Any]:
    """Read a specific email (marks as read)."""
    email = next((e for e in email_inbox if e["id"] == email_id), None)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    email["read"] = True
    return email


@app.post("/email/send")
def send_email(email: EmailSend) -> MessageResponse:
    """Send an email."""
    sent = {
        "id": f"sent-{uuid.uuid4().hex[:6]}",
        **email.model_dump(),
        "from": "me@lobster.ai",
        "sent_at": datetime.utcnow().isoformat(),
    }
    email_sent.append(sent)
    return MessageResponse(id=sent["id"], message="Email sent")


@app.get("/email/sent")
def list_sent() -> dict[str, Any]:
    """List sent emails."""
    return {"emails": email_sent, "count": len(email_sent)}


@app.get("/email/state")
def email_state() -> dict[str, Any]:
    """Eval harness inspection."""
    return {
        "inbox": email_inbox,
        "sent": email_sent,
    }


# ===================================================================
# 4. Notes API
# ===================================================================


class NoteCreate(BaseModel):
    """Note input."""
    title: str
    content: str
    tags: list[str] = []


class NoteUpdate(BaseModel):
    """Note update input."""
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None


notes: list[dict[str, Any]] = [
    {
        "id": "note-001",
        "title": "Project Ideas",
        "content": "1. Graph-based memory for AI\n2. Browser eval framework\n3. Lobster-themed everything",
        "tags": ["ideas", "projects"],
        "created_at": "2026-04-01T10:00:00",
        "updated_at": "2026-04-01T10:00:00",
    },
]


@app.get("/notes")
def list_notes(tag: str | None = None) -> dict[str, Any]:
    """List all notes, optionally filtered by tag."""
    result = notes
    if tag:
        result = [n for n in notes if tag in n.get("tags", [])]
    return {"notes": result, "count": len(result)}


@app.get("/notes/{note_id}")
def get_note(note_id: str) -> dict[str, Any]:
    """Get a specific note."""
    note = next((n for n in notes if n["id"] == note_id), None)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.post("/notes")
def create_note(note: NoteCreate) -> MessageResponse:
    """Create a new note."""
    new_note = {
        "id": f"note-{uuid.uuid4().hex[:6]}",
        **note.model_dump(),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    notes.append(new_note)
    return MessageResponse(id=new_note["id"], message="Note created")


@app.patch("/notes/{note_id}")
def update_note(note_id: str, update: NoteUpdate) -> MessageResponse:
    """Update a note."""
    note = next((n for n in notes if n["id"] == note_id), None)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    for key, val in update.model_dump(exclude_unset=True).items():
        note[key] = val
    note["updated_at"] = datetime.utcnow().isoformat()
    return MessageResponse(id=note_id, message="Note updated")


@app.delete("/notes/{note_id}")
def delete_note(note_id: str) -> MessageResponse:
    """Delete a note."""
    global notes
    before = len(notes)
    notes = [n for n in notes if n["id"] != note_id]
    if len(notes) == before:
        raise HTTPException(status_code=404, detail="Note not found")
    return MessageResponse(message="Note deleted")


@app.get("/notes/state")
def notes_state() -> dict[str, Any]:
    """Eval harness inspection."""
    return {"notes": notes}


# ===================================================================
# Global reset & health
# ===================================================================


@app.post("/reset")
def reset_all() -> MessageResponse:
    """Reset all services to initial state."""
    weather_queries.clear()
    # Reset calendar to seed data
    calendar_events.clear()
    calendar_events.extend([
        {
            "id": "evt-001",
            "title": "Team Standup",
            "date": "2026-04-10",
            "time": "09:00",
            "duration_minutes": 30,
            "description": "Daily standup with the lobster crew",
        },
        {
            "id": "evt-002",
            "title": "Lunch with Molty",
            "date": "2026-04-10",
            "time": "12:00",
            "duration_minutes": 60,
            "description": "Reef Café, table for two",
        },
        {
            "id": "evt-003",
            "title": "Deploy v2.0",
            "date": "2026-04-11",
            "time": "15:00",
            "duration_minutes": 120,
            "description": "Production deployment with rollback plan",
        },
    ])
    # Reset email
    email_inbox.clear()
    email_inbox.extend([
        {
            "id": "mail-001",
            "from": "boss@acme.com",
            "to": "me@lobster.ai",
            "subject": "Q1 Report Needed",
            "body": "Hi, can you prepare the Q1 report by end of week? Include revenue and churn numbers.",
            "date": "2026-04-09",
            "read": False,
        },
        {
            "id": "mail-002",
            "from": "hr@acme.com",
            "to": "me@lobster.ai",
            "subject": "Team Offsite - RSVP",
            "body": "The team offsite is April 15. Please RSVP by replying to this email.",
            "date": "2026-04-08",
            "read": True,
        },
        {
            "id": "mail-003",
            "from": "newsletter@techdigest.com",
            "to": "me@lobster.ai",
            "subject": "This Week in AI",
            "body": "Top stories: LLM costs drop 50%, new graph databases, lobster-themed AI assistants trending.",
            "date": "2026-04-09",
            "read": False,
        },
    ])
    email_sent.clear()
    # Reset notes
    notes.clear()
    notes.append({
        "id": "note-001",
        "title": "Project Ideas",
        "content": "1. Graph-based memory for AI\n2. Browser eval framework\n3. Lobster-themed everything",
        "tags": ["ideas", "projects"],
        "created_at": "2026-04-01T10:00:00",
        "updated_at": "2026-04-01T10:00:00",
    })
    return MessageResponse(message="All services reset")


@app.get("/health")
def health() -> MessageResponse:
    """Health check."""
    return MessageResponse(message="healthy")
