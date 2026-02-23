"""Tests for BlackRoad Ticket System."""
import pytest
from datetime import datetime, timedelta
from ticket_system import TicketSystem, Ticket, Comment, DEFAULT_SLA


@pytest.fixture
def ts():
    s = TicketSystem(":memory:")
    yield s
    s.close()


@pytest.fixture
def open_ticket(ts):
    t = Ticket(title="Login broken", description="production outage critical",
               requester="user@example.com", priority=1, sla_hours=4)
    return ts.create_ticket(t)


# ── test 1: create and retrieve ticket ──────────────────────────────────────
def test_create_and_get_ticket(ts):
    t = Ticket(title="Slow dashboard", description="page load > 10s",
               requester="bob@example.com", priority=3)
    ts.create_ticket(t)
    fetched = ts.get_ticket(t.id)
    assert fetched is not None
    assert fetched.title == "Slow dashboard"
    assert fetched.status == "open"


# ── test 2: assign ticket changes status ────────────────────────────────────
def test_assign_ticket(ts, open_ticket):
    ok = ts.assign_ticket(open_ticket.id, "agent1")
    assert ok
    fetched = ts.get_ticket(open_ticket.id)
    assert fetched.assignee == "agent1"
    assert fetched.status == "in_progress"


# ── test 3: status transitions ───────────────────────────────────────────────
def test_status_transitions(ts, open_ticket):
    ts.assign_ticket(open_ticket.id, "agent1")
    ts.update_status(open_ticket.id, "review")
    ts.update_status(open_ticket.id, "resolved")
    fetched = ts.get_ticket(open_ticket.id)
    assert fetched.status == "resolved"
    assert fetched.resolved_at is not None


# ── test 4: invalid transition raises ValueError ─────────────────────────────
def test_invalid_transition(ts, open_ticket):
    with pytest.raises(ValueError, match="Invalid transition"):
        ts.update_status(open_ticket.id, "resolved")   # must go through in_progress


# ── test 5: SLA breach detection ─────────────────────────────────────────────
def test_sla_breach_detection(ts):
    # Create ticket with past creation time (SLA already overdue)
    t = Ticket(title="Old ticket", description="very old",
               requester="user@example.com", priority=2, sla_hours=1,
               created_at=datetime.utcnow() - timedelta(hours=3))
    ts.create_ticket(t)
    sla_info = ts.check_sla_breach(t.id)
    assert sla_info["is_breached"] is True
    assert sla_info["hours_remaining"] < 0


# ── test 6: auto-priority keyword rules ──────────────────────────────────────
def test_auto_priority(ts):
    p, sla = ts.auto_priority("production outage — system is completely down")
    assert p == 1
    assert sla == DEFAULT_SLA[1]

    p2, sla2 = ts.auto_priority("feature request for dark mode")
    assert p2 == 4
    assert sla2 == DEFAULT_SLA[4]


# ── test 7: queue filtering ───────────────────────────────────────────────────
def test_get_queue(ts):
    t1 = Ticket(title="A", description="a", requester="u", priority=1)
    t2 = Ticket(title="B", description="b", requester="u", priority=3)
    ts.create_ticket(t1)
    ts.create_ticket(t2)
    ts.assign_ticket(t1.id, "agent1")
    queue = ts.get_queue(assignee="agent1")
    assert len(queue) == 1
    assert queue[0].title == "A"
    all_open = ts.get_queue()
    assert len(all_open) >= 1


# ── test 8: weekly report ─────────────────────────────────────────────────────
def test_generate_report(ts):
    for i in range(3):
        t = Ticket(title=f"Ticket {i}", description="desc",
                   requester="user@example.com", priority=(i % 3) + 1)
        ts.create_ticket(t)
        ts.assign_ticket(t.id, f"agent{i}")
        ts.update_status(t.id, "review")
        ts.update_status(t.id, "resolved")
    report = ts.generate_report(days=7)
    assert report["total_opened"] >= 3
    assert report["total_resolved"] >= 3
    assert "by_priority" in report
    assert "open_by_assignee" in report


# ── test 9: escalation ───────────────────────────────────────────────────────
def test_escalate(ts):
    t = Ticket(title="Slow query", description="medium issue",
               requester="user@example.com", priority=3)
    ts.create_ticket(t)
    ts.escalate(t.id, reason="customer escalated")
    fetched = ts.get_ticket(t.id)
    assert fetched.priority == 2
    assert fetched.sla_hours == DEFAULT_SLA[2]
    comments = ts.get_comments(t.id, include_internal=True)
    assert any("escalat" in c.body.lower() for c in comments)
