# blackroad-ticket-system

[![PyPI version](https://img.shields.io/pypi/v/blackroad-ticket-system.svg)](https://pypi.org/project/blackroad-ticket-system/)
[![Python](https://img.shields.io/pypi/pyversions/blackroad-ticket-system.svg)](https://pypi.org/project/blackroad-ticket-system/)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](#testing)

> **Production-grade Python helpdesk ticket engine** — SLA tracking, auto-prioritisation, queue management, Stripe billing, and weekly reporting.  
> Part of the [BlackRoad Foundation](https://github.com/BlackRoad-Foundation) platform.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [API Reference](#api-reference)
   - [TicketSystem](#ticketsystem)
   - [Ticket](#ticket)
   - [Comment](#comment)
7. [SLA Reference](#sla-reference)
8. [Status Workflow](#status-workflow)
9. [Stripe Integration](#stripe-integration)
10. [Reporting](#reporting)
11. [Testing](#testing)
12. [Publishing to PyPI](#publishing-to-pypi)
13. [Contributing](#contributing)
14. [License](#license)

---

## Overview

`blackroad-ticket-system` is a self-contained, SQLite-backed helpdesk engine designed for teams that need reliable ticket management without external service dependencies. Drop it into any Python application — web framework, CLI tool, or serverless function — and get a full support workflow in minutes.

**Why BlackRoad Ticket System?**

- Zero runtime dependencies — ships with Python's standard library only.
- Persistent SQLite backend with indexed queries for fast queue retrieval.
- SLA breach detection that works in any timezone-aware or naive datetime environment.
- First-class Stripe billing hooks for usage-based or subscription support plans.
- 100 % type-annotated, `dataclass`-based models that serialize cleanly to JSON.

---

## Features

| Category | Capability |
|---|---|
| **Ticket Lifecycle** | Full state machine: `open` → `in_progress` → `review` → `resolved` → `closed` |
| **SLA Tracking** | Per-priority SLA hours, breach detection, history log |
| **Auto-Priority** | Keyword-scoring inference from ticket description text |
| **Queue Management** | Filter by assignee, status, and priority with priority-sorted results |
| **Escalation** | Bump priority one level, auto-adjust SLA, append internal comment |
| **Comment System** | Public and internal notes with full ticket history audit trail |
| **Reporting** | Weekly resolution stats, SLA breach rates, per-assignee load |
| **Stripe Billing** | Usage-based and subscription billing hooks for paid support plans |

---

## Installation

**Requirements:** Python 3.9 or higher.

```bash
pip install blackroad-ticket-system
```

For development (includes `pytest`):

```bash
pip install "blackroad-ticket-system[dev]"
```

Install from source:

```bash
git clone https://github.com/BlackRoad-Foundation/blackroad-ticket-system.git
cd blackroad-ticket-system
pip install -e ".[dev]"
```

---

## Quick Start

```python
from ticket_system import TicketSystem, Ticket

# Persistent SQLite database (use ":memory:" for tests)
ts = TicketSystem("tickets.db")

# Auto-detect priority from description text
priority, sla_hours = ts.auto_priority("production outage — login is completely broken")

ticket = Ticket(
    title="Login Outage",
    description="Users cannot log in. Production system affected.",
    requester="user@example.com",
    priority=priority,
    sla_hours=sla_hours,
)

ts.create_ticket(ticket)
ts.assign_ticket(ticket.id, "agent1")

# Check SLA status
sla = ts.check_sla_breach(ticket.id)
print(f"Breached: {sla['is_breached']}  Hours remaining: {sla['hours_remaining']}")

# Fetch agent queue
queue = ts.get_queue(assignee="agent1")

# Weekly summary report
report = ts.generate_report(days=7)
print(f"Opened: {report['total_opened']}  Resolved: {report['total_resolved']}")

ts.close()
```

---

## Configuration

`TicketSystem` accepts a single constructor argument:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `db_path` | `str` | `":memory:"` | Path to the SQLite database file. Use `":memory:"` for ephemeral/test usage. |

```python
# Production — persisted database
ts = TicketSystem("/var/data/support/tickets.db")

# Testing — ephemeral in-memory database
ts = TicketSystem(":memory:")
```

---

## API Reference

### TicketSystem

#### `create_ticket(ticket: Ticket) -> Ticket`

Persist a new ticket and log the initial SLA event.

```python
ticket = Ticket(title="Billing Error", description="Charge failed",
                requester="alice@example.com", priority=2)
ts.create_ticket(ticket)
```

---

#### `get_ticket(ticket_id: str) -> Optional[Ticket]`

Retrieve a ticket by its UUID. Returns `None` if not found.

```python
t = ts.get_ticket("some-uuid-here")
```

---

#### `assign_ticket(ticket_id: str, assignee: str) -> bool`

Assign an open ticket to an agent and transition its status to `in_progress`. Returns `True` on success.

```python
ts.assign_ticket(ticket.id, "agent1")
```

---

#### `update_status(ticket_id: str, status: str, author: str = "system", note: str = "") -> bool`

Transition a ticket to a new status. Raises `ValueError` for invalid transitions. An optional `note` is saved as an internal comment.

```python
ts.update_status(ticket.id, "review", author="agent1", note="Fix deployed to staging.")
ts.update_status(ticket.id, "resolved")
```

---

#### `escalate(ticket_id: str, reason: str = "") -> bool`

Bump a ticket's priority by one level (toward critical) and recalculate its SLA deadline.

```python
ts.escalate(ticket.id, reason="Customer requested manager callback.")
```

---

#### `check_sla_breach(ticket_id: str) -> dict`

Return a SLA status snapshot for the ticket.

```python
sla = ts.check_sla_breach(ticket.id)
# {
#   "ticket_id": "...",
#   "priority": 1,
#   "priority_label": "critical",
#   "sla_hours": 4,
#   "created_at": "2024-01-15T10:00:00",
#   "sla_deadline": "2024-01-15T14:00:00",
#   "is_breached": False,
#   "hours_remaining": 2.5
# }
```

---

#### `get_breached_tickets() -> list[dict]`

Return all active (non-resolved) tickets that have exceeded their SLA deadline, sorted by most overdue first.

```python
breached = ts.get_breached_tickets()
for b in breached:
    print(f"{b['title']}  overdue by {b['overdue_hours']}h  assignee={b['assignee']}")
```

---

#### `auto_priority(description: str) -> tuple[int, int]`

Score a description string against keyword lists and return `(priority, sla_hours)`.

```python
priority, sla_hours = ts.auto_priority("system is down — production outage")
# priority=1, sla_hours=4
```

---

#### `add_comment(comment: Comment) -> Comment`

Attach a comment (public or internal) to a ticket and update its `updated_at` timestamp.

```python
from ticket_system import Comment
ts.add_comment(Comment(ticket_id=ticket.id, author="agent1",
                        body="Investigated — root cause identified.", is_internal=False))
```

---

#### `get_comments(ticket_id: str, include_internal: bool = True) -> list[Comment]`

Retrieve all comments for a ticket, optionally filtering out internal notes.

```python
public_notes = ts.get_comments(ticket.id, include_internal=False)
```

---

#### `get_queue(assignee=None, status=None, priority=None) -> list[Ticket]`

Return a priority-sorted list of tickets. All parameters are optional filters.

```python
# All open unassigned tickets
unassigned = ts.get_queue()

# Agent's current workload
my_tickets = ts.get_queue(assignee="agent1")

# All critical open tickets
critical = ts.get_queue(priority=1)
```

---

#### `generate_report(days: int = 7) -> dict`

Generate a summary report covering the past `days` calendar days.

```python
report = ts.generate_report(days=30)
# {
#   "report_days": 30,
#   "generated_at": "...",
#   "total_opened": 142,
#   "total_resolved": 138,
#   "avg_resolution_hours": 6.4,
#   "sla_breach_rate_pct": 3.2,
#   "by_priority": {"critical": {"opened": 5, "resolved": 5}, ...},
#   "open_by_assignee": {"agent1": 4, "agent2": 2, "unassigned": 1},
#   "currently_open": 7
# }
```

---

#### `close() -> None`

Close the underlying SQLite connection. Call this when you are done with the instance.

---

### Ticket

```python
@dataclass
class Ticket:
    title: str
    description: str
    requester: str
    id: str                        # UUID, auto-generated
    priority: int = 3              # 1=critical, 2=high, 3=medium, 4=low
    status: str = "open"
    assignee: Optional[str] = None
    sla_hours: int = 72
    created_at: datetime           # UTC, auto-set
    updated_at: datetime           # UTC, auto-set
    resolved_at: Optional[datetime] = None
    tags: List[str] = []
```

**Helper methods:**

| Method | Returns | Description |
|---|---|---|
| `sla_deadline()` | `datetime` | `created_at + sla_hours` |
| `is_breached()` | `bool` | Whether the SLA has been exceeded |
| `time_to_sla()` | `timedelta` | Positive = time remaining; negative = overdue |
| `age_hours()` | `float` | Hours since ticket creation |

---

### Comment

```python
@dataclass
class Comment:
    ticket_id: str
    author: str
    body: str
    id: str                  # UUID, auto-generated
    created_at: datetime     # UTC, auto-set
    is_internal: bool = False
```

---

## SLA Reference

Default SLA windows applied by `auto_priority` and `escalate`:

| Priority | Label    | SLA Window  | Typical Use Case |
|----------|----------|-------------|------------------|
| 1        | Critical | 4 hours     | Production outage, security breach, data loss |
| 2        | High     | 24 hours    | Major feature broken, high business impact |
| 3        | Medium   | 72 hours    | Degraded performance, non-critical bug |
| 4        | Low      | 168 hours   | Feature requests, questions, enhancements |

---

## Status Workflow

```
                        ┌─────────┐
              ┌─────────│  open   │─────────┐
              │         └────┬────┘         │
              ▼              │              ▼
         ┌─────────┐         │        ┌──────────┐
         │ on_hold │◄────────┤        │cancelled │
         └────┬────┘         │        └──────────┘
              │              ▼
              │       ┌─────────────┐
              └──────►│ in_progress │
                       └──────┬──────┘
                              │
                              ▼
                         ┌────────┐
                         │ review │
                         └───┬────┘
                             │
                             ▼
                        ┌──────────┐     ┌────────┐
                        │ resolved │────►│ closed │
                        └──────────┘     └────────┘
```

Valid transitions are enforced by `update_status`. Attempting an invalid transition raises `ValueError`.

---

## Stripe Integration

`blackroad-ticket-system` ships with documented hooks for **Stripe** billing, enabling:

- **Subscription support plans** — charge customers monthly for a support tier (e.g., Standard / Pro / Enterprise) and enforce SLA windows based on their plan.
- **Usage-based billing** — meter ticket volume and bill at the end of each period via Stripe Metered Billing.
- **Invoiced escalations** — automatically generate a Stripe invoice line item when a critical-priority ticket is opened.

### Prerequisites

```bash
pip install stripe
```

Set your Stripe secret key as an environment variable:

```bash
export STRIPE_SECRET_KEY="sk_live_..."
```

### Subscription Plan Mapping

Map Stripe product/price IDs to SLA hours in your application layer:

```python
import stripe
import os
from ticket_system import TicketSystem, Ticket

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

PLAN_SLA: dict[str, int] = {
    "price_standard": 72,   # Standard plan  → medium SLA
    "price_pro":      24,   # Pro plan        → high SLA
    "price_enterprise": 4,  # Enterprise plan → critical SLA
}

def get_sla_for_customer(stripe_customer_id: str) -> int:
    """Look up the customer's active subscription and return their SLA hours."""
    subs = stripe.Subscription.list(customer=stripe_customer_id, status="active", limit=1)
    if not subs.data:
        return 168  # Free tier → low priority
    price_id = subs.data[0]["items"]["data"][0]["price"]["id"]
    return PLAN_SLA.get(price_id, 72)

ts = TicketSystem("tickets.db")

# Create a ticket with SLA derived from the customer's Stripe plan
sla_hours = get_sla_for_customer("cus_ABC123")
ticket = Ticket(
    title="Cannot access dashboard",
    description="Getting 403 error on login.",
    requester="alice@enterprise.com",
    priority=2,
    sla_hours=sla_hours,
)
ts.create_ticket(ticket)
```

### Usage-Based Billing (Metered)

Report ticket opens to a Stripe metered subscription item:

```python
def report_ticket_usage(stripe_subscription_item_id: str, quantity: int = 1) -> None:
    """Increment the usage counter on a Stripe metered billing item."""
    stripe.SubscriptionItem.create_usage_record(
        stripe_subscription_item_id,
        quantity=quantity,
        action="increment",
    )

# Call after ts.create_ticket(ticket) for metered customers
report_ticket_usage("si_XYZ789")
```

### Webhook Handler (Flask example)

Process Stripe events to react to subscription changes:

```python
import stripe
import os
from flask import Flask, request, jsonify
from ticket_system import TicketSystem

app = Flask(__name__)
ts  = TicketSystem("tickets.db")

@app.post("/stripe/webhook")
def stripe_webhook():
    payload = request.data
    sig     = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, os.environ["STRIPE_WEBHOOK_SECRET"]
        )
    except stripe.error.SignatureVerificationError:
        return jsonify(error="Invalid signature"), 400

    if event["type"] == "customer.subscription.deleted":
        # Downgrade open tickets to low priority when plan is cancelled
        customer_id = event["data"]["object"]["customer"]
        for ticket in ts.get_queue():
            if ticket.requester == customer_id and ticket.status not in ("resolved", "closed"):
                # escalate() bumps priority toward critical — apply only when warranted
                ts.escalate(ticket.id, reason="Subscription cancelled — notifying agent.")

    return jsonify(ok=True)
```

---

## Reporting

`generate_report(days=7)` returns a dictionary suitable for email digests, dashboards, or Stripe-based billing summaries:

```python
report = ts.generate_report(days=7)
```

**Report fields:**

| Field | Type | Description |
|---|---|---|
| `report_days` | `int` | Number of days covered |
| `generated_at` | `str` | ISO 8601 UTC timestamp |
| `total_opened` | `int` | Tickets created in the period |
| `total_resolved` | `int` | Tickets resolved in the period |
| `avg_resolution_hours` | `float \| None` | Mean time to resolution |
| `sla_breach_rate_pct` | `float` | Percentage of transitions that were in breach |
| `by_priority` | `dict` | Opened / resolved counts per priority label |
| `open_by_assignee` | `dict` | Open ticket count per agent |
| `currently_open` | `int` | Total active (non-terminal) tickets right now |

---

## Testing

Install dev dependencies and run the full suite:

```bash
pip install "blackroad-ticket-system[dev]"
# or from source:
pip install pytest
PYTHONPATH=src pytest tests/ -v
```

The test suite covers:

| Test | Description |
|---|---|
| `test_create_and_get_ticket` | Create and retrieve a ticket by ID |
| `test_assign_ticket` | Assign a ticket and verify status change |
| `test_status_transitions` | Walk through the full lifecycle |
| `test_invalid_transition` | Confirm `ValueError` on illegal transitions |
| `test_sla_breach_detection` | Detect SLA breach on a backdated ticket |
| `test_auto_priority` | Keyword-based priority inference |
| `test_get_queue` | Filtered queue retrieval |
| `test_generate_report` | Weekly report aggregation |
| `test_escalate` | Priority escalation and SLA recalculation |

---

## Publishing to PyPI

This package uses [PEP 517/518](https://peps.python.org/pep-0517/) `pyproject.toml` for packaging. To build and publish a new release:

```bash
# Install build tools
pip install build twine

# Build sdist + wheel
python -m build

# Upload to PyPI (set TWINE_USERNAME / TWINE_PASSWORD or use API token)
twine upload dist/*
```

Tag the release first:

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## Contributing

1. Fork the repository and create a feature branch.
2. Make your changes with accompanying tests.
3. Run `PYTHONPATH=src pytest tests/ -v` and confirm all tests pass.
4. Open a pull request against `main` with a clear description of the change.

Please follow the existing code style — type annotations, `dataclass` models, and descriptive docstrings are required for all public APIs.

---

## License

© BlackRoad OS, Inc. All rights reserved.
