"""Phase 17 -- Security Graph. A single relational table in the existing
PostgreSQL database, not a graph database: at CyberLab's current scale
(hundreds, not millions, of nodes) a recursive CTE over an indexed edge
table is simple, transactionally consistent with the rest of the app, and
introduces no new infrastructure.

Nodes are not a separate table. ASSET/FINDING nodes reference real rows
(`from_id`/`to_id` holds the UUID as a string); CVE/SERVICE/TECHNOLOGY are
"virtual" nodes identified by a natural key (e.g. "CVE-2021-44228",
"80/tcp", "Apache") -- creating a local CVE/Service/Technology table just
to satisfy the graph model would be exactly the kind of invented data this
phase is instructed to avoid.

Every edge is written by app/graph/builder.py from data that already
exists elsewhere (Finding.cve_ids, Asset.technologies, nmap evidence,
Phase 16's FindingRelation) -- never accepted as API input, and never a
silent guess: `reason` must always answer "why does this edge exist?".
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        # Idempotence: rebuilding the same edge from the same source never
        # creates a duplicate -- app/graph/builder.py upserts on this key.
        UniqueConstraint("from_type", "from_id", "to_type", "to_id", "relation", name="uq_graph_edge"),
        Index("ix_graph_edges_from", "from_type", "from_id"),
        Index("ix_graph_edges_to", "to_type", "to_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # "ASSET" | "FINDING" | "CVE" | "SERVICE" | "TECHNOLOGY" -- plain
    # strings, not a DB enum: virtual node types (CVE/SERVICE/TECHNOLOGY)
    # have no backing table to anchor an enum to, and a 5th real node type
    # would otherwise require a migration just to widen the enum.
    from_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # UUID string for ASSET/FINDING; a natural key for virtual nodes
    # (e.g. "CVE-2021-44228", "80/tcp", "Apache").
    from_id: Mapped[str] = mapped_column(String(512), nullable=False)
    to_type: Mapped[str] = mapped_column(String(32), nullable=False)
    to_id: Mapped[str] = mapped_column(String(512), nullable=False)

    # "HAS_FINDING" | "EXPOSES" | "USES_TECHNOLOGY" | "REFERENCES_CVE" |
    # "RELATED_TO" -- see app/graph/builder.py for the fixed set of rules
    # that produce each one. Never a free-form relation from a request.
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    # Tool/mechanism that produced this edge (e.g. "nmap", "whatweb",
    # "phase16_correlation") -- distinct from `reason`, which is the
    # human-readable justification.
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    edge_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )
