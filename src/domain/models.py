"""Domain-Driven Design (DDD) domain models for codebone.

Defines the core entities, value objects, and aggregates for representing both
codebase architecture knowledge and internal system operations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class DDDRole(str, Enum):
    """Tactical DDD roles a code file or symbol can fulfill."""
    AGGREGATE_ROOT = "Aggregate Root"
    ENTITY = "Entity"
    VALUE_OBJECT = "Value Object"
    DOMAIN_EVENT = "Domain Event"
    REPOSITORY = "Repository"
    DOMAIN_SERVICE = "Domain Service"
    USE_CASE = "Use Case"
    COMMAND_HANDLER = "Command Handler"
    QUERY_HANDLER = "Query Handler"
    API_ROUTER = "API Router"
    INFRASTRUCTURE = "Infrastructure"
    GENERIC = "Generic"


@dataclass(frozen=True)
class BoundedContext:
    """Strategic DDD: Represents a distinct problem domain / bounded context."""
    name: str
    description: str = ""
    is_custom: bool = False

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


@dataclass(frozen=True)
class TacticalSymbol:
    """A tactical DDD symbol identified in code."""
    name: str
    role: DDDRole
    file_path: str
    details: str = ""


@dataclass
class FileRecord:
    """Core Domain Entity: Represents an analyzed file in the knowledge graph."""
    path: str
    tables: List[str] = field(default_factory=list)
    routes: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    summary: str = ""
    updated_at: float = 0.0
    mtime: float = 0.0
    content_hash: str = ""
    source: str = "model"

    # Tactical DDD metadata
    aggregates: List[str] = field(default_factory=list)
    value_objects: List[str] = field(default_factory=list)
    repositories: List[str] = field(default_factory=list)
    domain_services: List[str] = field(default_factory=list)
    bounded_context: str = ""

    def primary_role(self) -> DDDRole:
        """Derive the primary tactical DDD role of this file."""
        if self.aggregates:
            return DDDRole.AGGREGATE_ROOT
        if self.value_objects:
            return DDDRole.VALUE_OBJECT
        if self.domain_services:
            return DDDRole.DOMAIN_SERVICE
        if self.repositories:
            return DDDRole.REPOSITORY
        if self.events and not self.routes:
            return DDDRole.DOMAIN_EVENT
        if self.routes:
            return DDDRole.API_ROUTER
        if self.tables:
            return DDDRole.ENTITY
        return DDDRole.GENERIC

    def all_entities(self) -> List[str]:
        """All entities declared across tables and DDD aggregates."""
        seen: Set[str] = set()
        res: List[str] = []
        for item in self.aggregates + self.tables:
            if item not in seen:
                seen.add(item)
                res.append(item)
        return res

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "tables": list(self.tables),
            "routes": list(self.routes),
            "events": list(self.events),
            "domains": list(self.domains),
            "summary": self.summary,
            "updated_at": self.updated_at,
            "mtime": self.mtime,
            "content_hash": self.content_hash,
            "source": self.source,
            "aggregates": list(self.aggregates),
            "value_objects": list(self.value_objects),
            "repositories": list(self.repositories),
            "domain_services": list(self.domain_services),
            "bounded_context": self.bounded_context,
            "role": self.primary_role().value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FileRecord:
        return cls(
            path=data.get("path", ""),
            tables=list(data.get("tables", [])),
            routes=list(data.get("routes", [])),
            events=list(data.get("events", [])),
            domains=list(data.get("domains", [])),
            summary=data.get("summary", ""),
            updated_at=float(data.get("updated_at", 0.0)),
            mtime=float(data.get("mtime", 0.0)),
            content_hash=data.get("content_hash", ""),
            source=data.get("source", "model"),
            aggregates=list(data.get("aggregates", [])),
            value_objects=list(data.get("value_objects", [])),
            repositories=list(data.get("repositories", [])),
            domain_services=list(data.get("domain_services", [])),
            bounded_context=data.get("bounded_context", ""),
        )


@dataclass
class ArchitectureGraph:
    """Aggregate Root representing the entire indexed project architecture graph."""
    project_name: str
    files: Dict[str, FileRecord] = field(default_factory=dict)
    revision: int = 0

    def add_file(self, record: FileRecord) -> None:
        self.files[record.path] = record
        self.revision += 1

    add_record = add_file

    def remove_file(self, path: str) -> bool:
        if path in self.files:
            del self.files[path]
            self.revision += 1
            return True
        return False

    def get_bounded_contexts(self) -> Dict[str, List[str]]:
        """Group files by bounded context / domain."""
        contexts: Dict[str, List[str]] = {}
        for f in self.files.values():
            ctx = f.bounded_context or (f.domains[0] if f.domains else "Unassigned")
            contexts.setdefault(ctx, []).append(f.path)
        return contexts

    @property
    def bounded_contexts(self) -> Dict[str, List[str]]:
        return self.get_bounded_contexts()

    def get_aggregates(self) -> Dict[str, List[str]]:
        """Index files by aggregate roots."""
        idx: Dict[str, List[str]] = {}
        for f in self.files.values():
            for agg in f.aggregates:
                idx.setdefault(agg, []).append(f.path)
        return idx

    @property
    def aggregates(self) -> Dict[str, List[str]]:
        return self.get_aggregates()

    def summary_metrics(self) -> Dict[str, int]:
        all_aggregates = set()
        all_repos = set()
        for f in self.files.values():
            all_aggregates.update(f.aggregates)
            all_repos.update(f.repositories)
        return {
            "files_count": len(self.files),
            "bounded_contexts_count": len(self.get_bounded_contexts()),
            "aggregates_count": len(all_aggregates),
            "repositories_count": len(all_repos),
        }

