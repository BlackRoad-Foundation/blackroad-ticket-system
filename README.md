# blackroad-ticket-system

> Production Python helpdesk ticket system — part of [BlackRoad Foundation](https://github.com/BlackRoad-Foundation).

## Features

- **Ticket Lifecycle** — Full status machine: open → in_progress → review → resolved → closed
- **SLA Tracking** — Per-priority SLA hours, breach detection, history log
- **Auto-Priority** — Keyword-based inference from ticket description
- **Queue Management** — Filter by assignee, status, priority
- **Escalation** — Bump priority + auto-adjust SLA + internal comment
- **Comment System** — Public and internal notes with ticket history
- **Weekly Reports** — Resolution stats, breach rates, per-assignee load

## Quick Start

```python
from src.ticket_system import TicketSystem, Ticket

ts = TicketSystem("tickets.db")

# Auto-detect priority from description
priority, sla_hours = ts.auto_priority("production outage — login is completely broken")
ticket = Ticket(
    title="Login Outage", description="...",
    requester="user@example.com",
    priority=priority, sla_hours=sla_hours
)
ts.create_ticket(ticket)
ts.assign_ticket(ticket.id, "agent1")

sla = ts.check_sla_breach(ticket.id)
queue = ts.get_queue(assignee="agent1")
report = ts.generate_report(days=7)
```

## SLA Defaults

| Priority | Label    | SLA       |
|----------|----------|-----------|
| 1        | Critical | 4 hours   |
| 2        | High     | 24 hours  |
| 3        | Medium   | 72 hours  |
| 4        | Low      | 168 hours |

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## License

© BlackRoad OS, Inc. All rights reserved.
