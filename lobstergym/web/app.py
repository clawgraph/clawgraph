"""LobsterGym Web — Mock websites for OpenClaw browser-automation evaluation.

Serves deterministic HTML pages that simulate real-world web tasks.
Each scenario exposes a ``/state`` endpoint so the eval harness can
verify whether the agent completed the task correctly.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, url_for

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Shared state — inspectable via /state endpoints
# ---------------------------------------------------------------------------


@dataclass
class BookingState:
    """Tracks flight-booking scenario state."""

    searches: list[dict[str, Any]] = field(default_factory=list)
    bookings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TodoState:
    """Tracks todo-app scenario state."""

    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ContactState:
    """Tracks contact-form scenario state."""

    submissions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ShopState:
    """Tracks e-commerce scenario state."""

    cart: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)


booking_state = BookingState()
todo_state = TodoState()
contact_state = ContactState()
shop_state = ShopState()

# ---------------------------------------------------------------------------
# Pre-seeded data
# ---------------------------------------------------------------------------

FLIGHTS = [
    {
        "id": "FL100",
        "airline": "SkyLobster Air",
        "from": "SFO",
        "to": "JFK",
        "depart": "2026-04-10 08:00",
        "arrive": "2026-04-10 16:30",
        "price": 349,
        "seats": 42,
    },
    {
        "id": "FL200",
        "airline": "CrustAir",
        "from": "SFO",
        "to": "JFK",
        "depart": "2026-04-10 11:15",
        "arrive": "2026-04-10 19:45",
        "price": 289,
        "seats": 7,
    },
    {
        "id": "FL300",
        "airline": "PinchWing",
        "from": "SFO",
        "to": "JFK",
        "depart": "2026-04-10 14:00",
        "arrive": "2026-04-10 22:30",
        "price": 415,
        "seats": 118,
    },
    {
        "id": "FL400",
        "airline": "SkyLobster Air",
        "from": "LAX",
        "to": "ORD",
        "depart": "2026-04-12 06:30",
        "arrive": "2026-04-12 12:15",
        "price": 199,
        "seats": 23,
    },
]

PRODUCTS = [
    {"id": "P001", "name": "Lobster Plushie", "price": 24.99, "stock": 50},
    {"id": "P002", "name": "Claw Grip Mouse", "price": 59.99, "stock": 30},
    {"id": "P003", "name": "Shell Case (13-inch)", "price": 39.99, "stock": 15},
    {"id": "P004", "name": "Antenna Headphones", "price": 89.99, "stock": 8},
    {"id": "P005", "name": "Reef Keyboard", "price": 129.99, "stock": 20},
]


# ===================================================================
# Index
# ===================================================================


@app.route("/")
def index() -> str:
    """Landing page with links to each scenario."""
    return render_template("index.html")


# ===================================================================
# Scenario 1 — Flight Booking
# ===================================================================


@app.route("/flights")
def flights_search_page() -> str:
    """Flight search form."""
    return render_template("flights/search.html")


@app.route("/flights/results", methods=["GET", "POST"])
def flights_results() -> str:
    """Show matching flights."""
    origin = request.values.get("origin", "").upper()
    dest = request.values.get("destination", "").upper()
    date = request.values.get("date", "")
    booking_state.searches.append(
        {"origin": origin, "destination": dest, "date": date}
    )
    results = [
        f
        for f in FLIGHTS
        if f["from"] == origin and f["to"] == dest
    ]
    return render_template(
        "flights/results.html", flights=results, origin=origin, dest=dest, date=date
    )


@app.route("/flights/book/<flight_id>")
def flights_book_form(flight_id: str) -> str:
    """Passenger details form."""
    flight = next((f for f in FLIGHTS if f["id"] == flight_id), None)
    if not flight:
        return "Flight not found", 404
    return render_template("flights/book.html", flight=flight)


@app.route("/flights/confirm", methods=["POST"])
def flights_confirm() -> str:
    """Process booking."""
    data = {
        "confirmation": f"BK-{uuid.uuid4().hex[:8].upper()}",
        "flight_id": request.form.get("flight_id"),
        "passenger_name": request.form.get("name"),
        "passenger_email": request.form.get("email"),
        "booked_at": datetime.utcnow().isoformat(),
    }
    booking_state.bookings.append(data)
    return render_template("flights/confirmation.html", booking=data)


@app.route("/flights/state")
def flights_state() -> Any:
    """Inspection endpoint for eval harness."""
    return jsonify(
        {
            "searches": booking_state.searches,
            "bookings": booking_state.bookings,
        }
    )


# ===================================================================
# Scenario 2 — Todo App
# ===================================================================


@app.route("/todos")
def todos_page() -> str:
    """Todo list UI."""
    return render_template("todos/list.html", items=todo_state.items)


@app.route("/todos/add", methods=["POST"])
def todos_add() -> Any:
    """Add a todo item."""
    text = request.form.get("text", "").strip()
    if text:
        item = {
            "id": str(uuid.uuid4()),
            "text": text,
            "done": False,
            "created_at": datetime.utcnow().isoformat(),
        }
        todo_state.items.append(item)
    return redirect(url_for("todos_page"))


@app.route("/todos/toggle/<item_id>", methods=["POST"])
def todos_toggle(item_id: str) -> Any:
    """Toggle done state."""
    for item in todo_state.items:
        if item["id"] == item_id:
            item["done"] = not item["done"]
            break
    return redirect(url_for("todos_page"))


@app.route("/todos/delete/<item_id>", methods=["POST"])
def todos_delete(item_id: str) -> Any:
    """Delete a todo item."""
    todo_state.items = [i for i in todo_state.items if i["id"] != item_id]
    return redirect(url_for("todos_page"))


@app.route("/todos/state")
def todos_state() -> Any:
    """Inspection endpoint for eval harness."""
    return jsonify({"items": todo_state.items})


# ===================================================================
# Scenario 3 — Contact Form (multi-step)
# ===================================================================


@app.route("/contact")
def contact_page() -> str:
    """Multi-step contact form — step 1."""
    return render_template("contact/step1.html")


@app.route("/contact/step2", methods=["POST"])
def contact_step2() -> str:
    """Step 2 — message details."""
    name = request.form.get("name", "")
    email = request.form.get("email", "")
    return render_template("contact/step2.html", name=name, email=email)


@app.route("/contact/submit", methods=["POST"])
def contact_submit() -> str:
    """Final submission."""
    data = {
        "id": str(uuid.uuid4()),
        "name": request.form.get("name", ""),
        "email": request.form.get("email", ""),
        "subject": request.form.get("subject", ""),
        "message": request.form.get("message", ""),
        "submitted_at": datetime.utcnow().isoformat(),
    }
    contact_state.submissions.append(data)
    return render_template("contact/thankyou.html", submission=data)


@app.route("/contact/state")
def contact_state_endpoint() -> Any:
    """Inspection endpoint for eval harness."""
    return jsonify({"submissions": contact_state.submissions})


# ===================================================================
# Scenario 4 — E-commerce Shop
# ===================================================================


@app.route("/shop")
def shop_page() -> str:
    """Product listing."""
    return render_template("shop/products.html", products=PRODUCTS)


@app.route("/shop/product/<product_id>")
def shop_product_detail(product_id: str) -> str:
    """Product detail page."""
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        return "Product not found", 404
    return render_template("shop/detail.html", product=product)


@app.route("/shop/cart/add", methods=["POST"])
def shop_add_to_cart() -> Any:
    """Add item to cart."""
    pid = request.form.get("product_id", "")
    qty = int(request.form.get("quantity", "1"))
    product = next((p for p in PRODUCTS if p["id"] == pid), None)
    if product:
        # Check if already in cart
        existing = next((c for c in shop_state.cart if c["product_id"] == pid), None)
        if existing:
            existing["quantity"] += qty
        else:
            shop_state.cart.append(
                {"product_id": pid, "name": product["name"], "price": product["price"], "quantity": qty}
            )
    return redirect(url_for("shop_cart"))


@app.route("/shop/cart")
def shop_cart() -> str:
    """Cart page."""
    total = sum(item["price"] * item["quantity"] for item in shop_state.cart)
    return render_template("shop/cart.html", cart=shop_state.cart, total=total)


@app.route("/shop/checkout", methods=["GET", "POST"])
def shop_checkout() -> str:
    """Checkout page / process order."""
    if request.method == "GET":
        total = sum(item["price"] * item["quantity"] for item in shop_state.cart)
        return render_template("shop/checkout.html", cart=shop_state.cart, total=total)

    # POST — process order
    order = {
        "order_id": f"ORD-{uuid.uuid4().hex[:8].upper()}",
        "items": list(shop_state.cart),
        "total": sum(item["price"] * item["quantity"] for item in shop_state.cart),
        "shipping_name": request.form.get("name", ""),
        "shipping_address": request.form.get("address", ""),
        "ordered_at": datetime.utcnow().isoformat(),
    }
    shop_state.orders.append(order)
    shop_state.cart.clear()
    return render_template("shop/order_confirmation.html", order=order)


@app.route("/shop/state")
def shop_state_endpoint() -> Any:
    """Inspection endpoint for eval harness."""
    return jsonify(
        {
            "cart": shop_state.cart,
            "orders": shop_state.orders,
        }
    )


# ===================================================================
# Global state reset (for eval runs)
# ===================================================================


@app.route("/reset", methods=["POST"])
def reset_all() -> Any:
    """Reset every scenario to clean state."""
    booking_state.searches.clear()
    booking_state.bookings.clear()
    todo_state.items.clear()
    contact_state.submissions.clear()
    shop_state.cart.clear()
    shop_state.orders.clear()
    return jsonify({"status": "reset"})


@app.route("/health")
def health() -> Any:
    """Health check."""
    return jsonify({"status": "ok"})


# ===================================================================
# Run
# ===================================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
