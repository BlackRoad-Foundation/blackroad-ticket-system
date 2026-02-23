"""
BlackRoad Ticket System — production implementation.
SLA tracking, auto-priority, queue management, weekly reports.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import uuid


# ─────────────────────────── data models ────────────────────────────────────

PRIORITY_LABELS = {1: "critical", 2: "high", 3: "medium", 4: "low"}
STATUS_FLOW = {
    "open":        ["in_progress", "on_hold", "cancelled"],
    "in_progress": ["review", "on_hold", "resolved"],
    "review":      ["resolved", "in_progress"],
    "on_hold":     ["open", "cancelled"],
    "resolved":    ["closed", "open"],
    "closed":      [],
    "cancelled":   [],
}

DEFAULT_SLA: Dict[int, int] = {
    1: 4,    # critical → 4 hours
    2: 24,   # high     → 24 hours
    3: 72,   # medium   → 72 hours
    4: 168,  # low      → 1 week
}

PRIORITY_KEYWORDS: Dict[int, List[str]] = {
    1: ["down", "outage", "crash", "critical", "emergency", "production", "breach"],
    2: ["broken", "error", "fail", "urgent", "security", "data loss", "high"],
    3: ["slow", "degraded", "incorrect", "issue", "bug", "medium"],
    4: ["feature", "enhancement", "request", "question", "low"],
}


@dataclass
class Ticket:
    title: str
    description: str
    requester: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 3                # 1=critical … 4=low
    status: str = "open"
    assignee: Optional[str] = None
    sla_hours: int = 72
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)

    def sla_deadline(self) -> datetime:
        return self.created_at + timedelta(hours=self.sla_hours)

    def is_breached(self) -> bool:
        if self.status in ("resolved", "closed", "cancelled"):
            ref = self.resolved_at or self.updated_at
            return ref > self.sla_deadline()
        return datetime.utcnow() > self.sla_deadline()

    def time_to_sla(self) -> timedelta:
        """Positive = time left; negative = overdue."""
        return self.sla_deadline() - datetime.utcnow()

    def age_hours(self) -> float:
        return (datetime.utcnow() - self.created_at).total_seconds() / 3600


@dataclass
class Comment:
    ticket_id: str
    author: str
    body: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_internal: bool = False


# ──────────────────────────── database layer ────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS tickets (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    requester   TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 3,
    status      TEXT NOT NULL DEFAULT 'open',
    assignee    TEXT,
    sla_hours   INTEGER NOT NULL DEFAULT 72,
    tags        TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS comments (
    id          TEXT PRIMARY KEY,
    ticket_id   TEXT NOT NULL REFERENCES tickets(id),
    author      TEXT NOT NULL,
    body        TEXT NOT NULL,
    is_internal INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sla_history (
    id          TEXT PRIMARY KEY,
    ticket_id   TEXT NOT NULL REFERENCES tickets(id),
    event       TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    sla_hours   INTEGER,
    was_breached INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tickets_status   ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_assignee ON tickets(assignee);
CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);
CREATE INDEX IF NOT EXISTS idx_comments_ticket  ON comments(ticket_id);
"""


class TicketSystem:
    """
    Production helpdesk ticket system backed by SQLite.
    Handles SLA monitoring, auto-prioritisation, queue filtering,
    assignment workflow, and weekly report generation.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(DDL)
        self.conn.commit()

    # ── ticket CRUD ──────────────────────────────────────────────────────────

    def create_ticket(self, ticket: Ticket) -> Ticket:
        self.conn.execute(
            "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticket.id, ticket.title, ticket.description, ticket.requester,
             ticket.priority, ticket.status, ticket.assignee, ticket.sla_hours,
             ",".join(ticket.tags),
             ticket.created_at.isoformat(), ticket.updated_at.isoformat(),
             ticket.resolved_at.isoformat() if ticket.resolved_at else None),
        )
        self._log_sla_event(ticket.id, "created", ticket.sla_hours)
        self.conn.commit()
        return ticket

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        row = self.conn.execute(
            "SELECT * FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()
        return self._row_to_ticket(row) if row else None

    def _row_to_ticket(self, row: sqlite3.Row) -> Ticket:
        return Ticket(
            id=row["id"], title=row["title"], description=row["description"],
            requester=row["requester"], priority=row["priority"],
            status=row["status"], assignee=row["assignee"],
            sla_hours=row["sla_hours"],
            tags=[t for t in (row["tags"] or "").split(",") if t],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"])
                        if row["resolved_at"] else None,
        )

    def assign_ticket(self, ticket_id: str, assignee: str) -> bool:
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            "UPDATE tickets SET assignee=?, updated_at=?, status=? "
            "WHERE id=? AND status='open'",
            (assignee, now, "in_progress", ticket_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def update_status(self, ticket_id: str, status: str,
                      author: str = "system", note: str = "") -> bool:
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            return False
        allowed = STATUS_FLOW.get(ticket.status, [])
        if status not in allowed:
            raise ValueError(
                f"Invalid transition {ticket.status!r} → {status!r}. "
                f"Allowed: {allowed}"
            )
        now = datetime.utcnow()
        resolved_at = now.isoformat() if status in ("resolved", "closed") else None
        self.conn.execute(
            "UPDATE tickets SET status=?, updated_at=?, resolved_at=? WHERE id=?",
            (status, now.isoformat(), resolved_at, ticket_id),
        )
        self._log_sla_event(ticket_id, f"status→{status}", ticket.sla_hours,
                            was_breached=ticket.is_breached())
        if note:
            self.add_comment(
                Comment(ticket_id=ticket_id, author=author, body=note,
                        is_internal=True)
            )
        self.conn.commit()
        return True

    def escalate(self, ticket_id: str, reason: str = "") -> bool:
        """Bump priority by one level (min 1 = critical)."""
        row = self.conn.execute(
            "SELECT priority FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()
        if not row:
            return False
        new_prio = max(1, row["priority"] - 1)
        new_sla = DEFAULT_SLA[new_prio]
        self.conn.execute(
            "UPDATE tickets SET priority=?, sla_hours=?, updated_at=? WHERE id=?",
            (new_prio, new_sla, datetime.utcnow().isoformat(), ticket_id),
        )
        self._log_sla_event(ticket_id, "escalated", new_sla)
        if reason:
            self.add_comment(
                Comment(ticket_id=ticket_id, author="system",
                        body=f"Escalated: {reason}", is_internal=True)
            )
        self.conn.commit()
        return True

    # ── SLA ──────────────────────────────────────────────────────────────────

    def _log_sla_event(self, ticket_id: str, event: str,
                       sla_hours: Optional[int] = None,
                       was_breached: bool = False) -> None:
        self.conn.execute(
            "INSERT INTO sla_history VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), ticket_id, event,
             datetime.utcnow().isoformat(), sla_hours, int(was_breached)),
        )

    def check_sla_breach(self, ticket_id: str) -> Dict[str, Any]:
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id!r} not found")
        deadline = ticket.sla_deadline()
        breached = ticket.is_breached()
        remaining = ticket.time_to_sla()
        return {
            "ticket_id": ticket_id,
            "priority": ticket.priority,
            "priority_label": PRIORITY_LABELS[ticket.priority],
            "sla_hours": ticket.sla_hours,
            "created_at": ticket.created_at.isoformat(),
            "sla_deadline": deadline.isoformat(),
            "is_breached": breached,
            "hours_remaining": round(remaining.total_seconds() / 3600, 2),
        }

    def get_breached_tickets(self) -> List[Dict[str, Any]]:
        """Return all open tickets that have breached their SLA."""
        rows = self.conn.execute(
            "SELECT * FROM tickets WHERE status NOT IN ('resolved','closed','cancelled')"
        ).fetchall()
        result = []
        for row in rows:
            ticket = self._row_to_ticket(row)
            if ticket.is_breached():
                deadline = ticket.sla_deadline()
                overdue_hrs = (datetime.utcnow() - deadline).total_seconds() / 3600
                result.append({
                    "ticket_id": ticket.id,
                    "title": ticket.title,
                    "priority": PRIORITY_LABELS[ticket.priority],
                    "assignee": ticket.assignee,
                    "overdue_hours": round(overdue_hrs, 1),
                })
        result.sort(key=lambda x: x["overdue_hours"], reverse=True)
        return result

    # ── auto-priority ─────────────────────────────────────────────────────────

    def auto_priority(self, description: str) -> Tuple[int, int]:
        """
        Infer ticket priority and SLA hours from description text using
        keyword scoring.  Returns (priority, sla_hours).
        """
        text = description.lower()
        scores: Dict[int, int] = defaultdict(int)
        for priority, keywords in PRIORITY_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[priority] += 1
        if scores:
            # Pick highest priority (lowest number) with score > 0
            best_priority = min(p for p, s in scores.items() if s > 0)
        else:
            best_priority = 3   # default: medium
        return best_priority, DEFAULT_SLA[best_priority]

    # ── comments ─────────────────────────────────────────────────────────────

    def add_comment(self, comment: Comment) -> Comment:
        self.conn.execute(
            "INSERT INTO comments VALUES (?,?,?,?,?,?)",
            (comment.id, comment.ticket_id, comment.author, comment.body,
             int(comment.is_internal), comment.created_at.isoformat()),
        )
        self.conn.execute(
            "UPDATE tickets SET updated_at=? WHERE id=?",
            (comment.created_at.isoformat(), comment.ticket_id),
        )
        self.conn.commit()
        return comment

    def get_comments(self, ticket_id: str,
                     include_internal: bool = True) -> List[Comment]:
        if include_internal:
            rows = self.conn.execute(
                "SELECT * FROM comments WHERE ticket_id=? ORDER BY created_at",
                (ticket_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM comments WHERE ticket_id=? AND is_internal=0 "
                "ORDER BY created_at",
                (ticket_id,),
            ).fetchall()
        return [
            Comment(
                id=r["id"], ticket_id=r["ticket_id"], author=r["author"],
                body=r["body"], is_internal=bool(r["is_internal"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    # ── queue management ──────────────────────────────────────────────────────

    def get_queue(
        self,
        assignee: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> List[Ticket]:
        """
        Return filtered, priority-sorted ticket queue.
        Unassigned tickets appear when assignee is omitted.
        """
        clauses: List[str] = []
        params: List[Any] = []
        if assignee:
            clauses.append("assignee=?")
            params.append(assignee)
        if status:
            clauses.append("status=?")
            params.append(status)
        elif not assignee:
            clauses.append("status NOT IN ('resolved','closed','cancelled')")
        if priority:
            clauses.append("priority=?")
            params.append(priority)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM tickets {where} ORDER BY priority ASC, created_at ASC",
            params,
        ).fetchall()
        return [self._row_to_ticket(r) for r in rows]

    # ── weekly report ─────────────────────────────────────────────────────────

    def generate_report(self, days: int = 7) -> Dict[str, Any]:
        """
        Generate a summary report for the past *days* days.
        Includes open/closed counts, avg resolution time,
        SLA breach rate, and per-priority breakdown.
        """
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()

        total_opened = self.conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE created_at >= ?", (since,)
        ).fetchone()[0]

        total_resolved = self.conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE resolved_at >= ?", (since,)
        ).fetchone()[0]

        # Average resolution time in hours
        rows = self.conn.execute(
            "SELECT created_at, resolved_at FROM tickets "
            "WHERE resolved_at >= ? AND status IN ('resolved','closed')",
            (since,),
        ).fetchall()
        if rows:
            res_times = [
                (datetime.fromisoformat(r["resolved_at"]) -
                 datetime.fromisoformat(r["created_at"])).total_seconds() / 3600
                for r in rows
            ]
            avg_resolution_hrs = round(sum(res_times) / len(res_times), 1)
        else:
            avg_resolution_hrs = None

        # SLA breach rate
        all_resolved = self.conn.execute(
            "SELECT COUNT(*) FROM sla_history "
            "WHERE event LIKE 'status→%' AND occurred_at >= ?",
            (since,),
        ).fetchone()[0]
        breached = self.conn.execute(
            "SELECT COUNT(*) FROM sla_history "
            "WHERE was_breached=1 AND occurred_at >= ?",
            (since,),
        ).fetchone()[0]
        breach_rate = round(breached / all_resolved * 100, 1) if all_resolved else 0

        # Per-priority breakdown
        prio_rows = self.conn.execute(
            "SELECT priority, COUNT(*) as cnt, "
            "       SUM(CASE WHEN status IN ('resolved','closed') THEN 1 ELSE 0 END) as done "
            "FROM tickets WHERE created_at >= ? GROUP BY priority",
            (since,),
        ).fetchall()
        by_priority = {
            PRIORITY_LABELS.get(r["priority"], str(r["priority"])): {
                "opened": r["cnt"], "resolved": r["done"],
            }
            for r in prio_rows
        }

        # Currently open by assignee
        assignee_rows = self.conn.execute(
            "SELECT assignee, COUNT(*) as cnt FROM tickets "
            "WHERE status NOT IN ('resolved','closed','cancelled') "
            "GROUP BY assignee ORDER BY cnt DESC",
        ).fetchall()
        by_assignee = {
            (r["assignee"] or "unassigned"): r["cnt"] for r in assignee_rows
        }

        return {
            "report_days": days,
            "generated_at": datetime.utcnow().isoformat(),
            "total_opened": total_opened,
            "total_resolved": total_resolved,
            "avg_resolution_hours": avg_resolution_hrs,
            "sla_breach_rate_pct": breach_rate,
            "by_priority": by_priority,
            "open_by_assignee": by_assignee,
            "currently_open": self.conn.execute(
                "SELECT COUNT(*) FROM tickets "
                "WHERE status NOT IN ('resolved','closed','cancelled')"
            ).fetchone()[0],
        }

    def close(self) -> None:
        self.conn.close()
