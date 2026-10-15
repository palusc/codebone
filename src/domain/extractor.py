"""Tactical and Strategic Domain-Driven Design (DDD) AST & pattern extractor.

Extracts:
1. Bounded Contexts (Strategic DDD - domain boundaries inferred from structure & semantics)
2. Aggregate Roots (Tactical DDD - consistency boundaries and root entities)
3. Value Objects (Tactical DDD - immutable concepts defined by their attributes)
4. Domain Events (Tactical DDD - explicit business events and handlers)
5. Repositories (Tactical DDD - domain storage interfaces & abstractions)
6. Domain Services & Use Cases (Tactical DDD - cross-entity domain logic)

Supports Python, TypeScript, JavaScript, Go, Rust, Java, C#, PHP, and Ruby.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Patterns for Strategic DDD: Bounded Context extraction from paths
CONTEXT_DIR_PATTERNS = [
    re.compile(r"(?:^|/)(?:contexts?|bounded_contexts?)/([A-Za-z0-9_-]+)(?:/|$)", re.IGNORECASE),
    re.compile(r"(?:^|/)(?:domain|domains)/([A-Za-z0-9_-]+)(?:/|$)", re.IGNORECASE),
    re.compile(r"(?:^|/)(?:modules?|apps?)/([A-Za-z0-9_-]+)/domain(?:/|$)", re.IGNORECASE),
    re.compile(r"(?:^|/)(?:packages?|pkg|services?)/([A-Za-z0-9_-]+)/domain(?:/|$)", re.IGNORECASE),
]

# Tactical DDD Class Inheritance / Marker patterns
AGGREGATE_ROOT_PATTERNS = [
    # Python
    re.compile(r"class\s+([A-Za-z0-9_]+)\s*\([^)]*(?:AggregateRoot|Aggregate|IAggregateRoot)[^)]*\)"),
    re.compile(r"@(?:aggregate_root|aggregate)\b[^\n]*\n\s*class\s+([A-Za-z0-9_]+)"),
    # TypeScript / JavaScript
    re.compile(r"(?:export\s+)?class\s+([A-Za-z0-9_]+)\s+extends\s+(?:AggregateRoot|Aggregate)\b"),
    re.compile(r"(?:export\s+)?class\s+([A-Za-z0-9_]+)\s+implements\s+[^{]*(?:IAggregateRoot|AggregateRoot)\b"),
    # Java / Kotlin
    re.compile(r"(?:public\s+|open\s+)?class\s+([A-Za-z0-9_]+)\s+(?:extends\s+(?:AbstractAggregateRoot|AggregateRoot)|implements\s+[^{]*IAggregateRoot)\b"),
    re.compile(r"@AggregateRoot\s+(?:public\s+)?class\s+([A-Za-z0-9_]+)"),
    # C#
    re.compile(r"(?:public\s+)?class\s+([A-Za-z0-9_]+)\s*:\s*[^{]*(?:AggregateRoot|IAggregateRoot)\b"),
    # Go / Rust by directory or naming
    re.compile(r"type\s+([A-Za-z0-9_]+)\s+struct\b"),  # checked in conjunction with file path
]

VALUE_OBJECT_PATTERNS = [
    # Python
    re.compile(r"class\s+([A-Za-z0-9_]+)\s*\([^)]*(?:ValueObject|BaseValueObject|IValueObject)[^)]*\)"),
    re.compile(r"@dataclass\s*\(\s*frozen\s*=\s*True\s*\)[^\n]*\n\s*class\s+([A-Za-z0-9_]+)"),
    # TypeScript / JavaScript
    re.compile(r"(?:export\s+)?class\s+([A-Za-z0-9_]+)\s+extends\s+(?:ValueObject|BaseValueObject)\b"),
    # C#
    re.compile(r"(?:public\s+)?(?:class|record)\s+([A-Za-z0-9_]+)\s*:\s*[^{]*ValueObject\b"),
    re.compile(r"public\s+readonly\s+record\s+struct\s+([A-Za-z0-9_]+)"),
    # Java
    re.compile(r"(?:public\s+)?record\s+([A-Za-z0-9_]+)\s*\("),
    # Common DDD naming conventions across languages (e.g., CurrencyVO, MoneyValueObject, AddressVO)
    re.compile(r"(?:class|record|struct|type)\s+([A-Za-z0-9_]*(?:VO|ValueObject))\b"),
]

DOMAIN_EVENT_PATTERNS = [
    # Explicit event inheritance
    re.compile(r"class\s+([A-Za-z0-9_]+)\s*\([^)]*(?:DomainEvent|IDomainEvent|BaseEvent|Event)[^)]*\)"),
    re.compile(r"(?:export\s+)?class\s+([A-Za-z0-9_]+)\s+extends\s+(?:DomainEvent|BaseEvent)\b"),
    re.compile(r"(?:export\s+)?class\s+([A-Za-z0-9_]+)\s+implements\s+[^{]*(?:IDomainEvent|DomainEvent)\b"),
    re.compile(r"(?:public\s+)?(?:record|class)\s+([A-Za-z0-9_]+)\s*:\s*[^{]*IDomainEvent\b"),
    # Naming convention for past-tense business domain events
    re.compile(r"(?:class|record|struct|type)\s+([A-Z][A-Za-z0-9_]*(?:Created|Updated|Deleted|Placed|Shipped|Cancelled|Failed|Completed|Registered|Approved|Rejected|Expired|Paid)Event?)\b"),
]

REPOSITORY_PATTERNS = [
    # Explicit repository interfaces or implementations
    re.compile(r"(?:class|interface|type)\s+([A-Za-z0-9_]*(?:Repository|Repo))\b"),
    re.compile(r"(?:class|interface)\s+([A-Za-z0-9_]+)\s*(?:extends|implements|:)\s*[^{]*(?:Repository|IRepository|CrudRepository|JpaRepository)\b"),
]

DOMAIN_SERVICE_PATTERNS = [
    # Domain services and Use Cases / Command / Query Handlers
    re.compile(r"(?:class|interface|type)\s+([A-Za-z0-9_]*(?:DomainService|UseCase|CommandHandler|QueryHandler))\b"),
    re.compile(r"class\s+([A-Za-z0-9_]+)\s*\([^)]*(?:DomainService|UseCase|BaseUseCase)[^)]*\)"),
]


def infer_bounded_context(file_path: str) -> Optional[str]:
    """Infers the bounded context name from standard DDD project folder structures."""
    norm = file_path.replace("\\", "/")
    for pattern in CONTEXT_DIR_PATTERNS:
        match = pattern.search(norm)
        if match:
            candidate = match.group(1).replace("-", "_").strip()
            # Ignore technical folder names
            if candidate.lower() not in {"model", "models", "entity", "entities", "events", "repositories", "services", "aggregates", "vo"}:
                return candidate.lower()

    # Check top-level business modules under src/ or apps/
    parts = norm.split("/")
    if len(parts) >= 3 and parts[0] in {"src", "app", "apps", "lib", "packages"} and parts[1].lower() not in {
        "common", "core", "shared", "utils", "config", "ui", "components", "api", "infra", "infrastructure"
    }:
        return parts[1].replace("-", "_").lower()

    return None


def extract_tactical_ddd(file_path: str, code: str) -> Dict[str, List[str]]:
    """Extracts tactical DDD components from source code using AST patterns and semantic conventions."""
    aggregates: Set[str] = set()
    value_objects: Set[str] = set()
    domain_events: Set[str] = set()
    repositories: Set[str] = set()
    domain_services: Set[str] = set()

    norm_path = file_path.lower()
    in_aggregate_dir = any(seg in norm_path for seg in ("/aggregate/", "/aggregates/", "_aggregate.", ".aggregate."))
    in_vo_dir = any(seg in norm_path for seg in ("/value_objects/", "/vo/", "/values/", "_vo.", ".vo."))
    in_event_dir = any(seg in norm_path for seg in ("/events/", "/domain_events/", "_event.", ".event."))
    in_repo_dir = any(seg in norm_path for seg in ("/repositories/", "/repos/", "_repository.", ".repository."))
    in_service_dir = any(seg in norm_path for seg in ("/domain_services/", "/use_cases/", "/usecases/", "/commands/", "/queries/", "/domain/", "/services/"))

    # 1. Aggregates
    for pat in AGGREGATE_ROOT_PATTERNS:
        for m in pat.finditer(code):
            name = m.group(1)
            if in_aggregate_dir or "aggregate" in name.lower() or pat != AGGREGATE_ROOT_PATTERNS[-1]:
                if len(name) > 2 and name not in {"AggregateRoot", "Aggregate", "IAggregateRoot"}:
                    aggregates.add(name)

    # 2. Value Objects
    for pat in VALUE_OBJECT_PATTERNS:
        for m in pat.finditer(code):
            name = m.group(1)
            if len(name) > 2 and name not in {"ValueObject", "BaseValueObject", "IValueObject"}:
                value_objects.add(name)
    if in_vo_dir and not value_objects:
        # Extract top-level classes in VO directories
        for m in re.finditer(r"(?:class|record|struct)\s+([A-Za-z0-9_]+)", code):
            name = m.group(1)
            if len(name) > 2:
                value_objects.add(name)

    # 3. Domain Events
    for pat in DOMAIN_EVENT_PATTERNS:
        for m in pat.finditer(code):
            name = m.group(1)
            if len(name) > 2 and name not in {"DomainEvent", "IDomainEvent", "BaseEvent", "Event"}:
                domain_events.add(name)

    # 4. Repositories
    for pat in REPOSITORY_PATTERNS:
        for m in pat.finditer(code):
            name = m.group(1)
            if len(name) > 3 and name not in {"Repository", "IRepository", "CrudRepository", "JpaRepository"}:
                repositories.add(name)

    # 5. Domain Services & Use Cases
    for pat in DOMAIN_SERVICE_PATTERNS:
        for m in pat.finditer(code):
            name = m.group(1)
            if len(name) > 3 and name not in {"DomainService", "UseCase", "BaseUseCase", "CommandHandler", "QueryHandler"}:
                domain_services.add(name)
    # Check classes ending in Service within domain directories
    if in_service_dir:
        for m in re.finditer(r"(?:class|interface|type)\s+([A-Za-z0-9_]*Service)\b", code):
            name = m.group(1)
            if len(name) > 3 and name not in {"Service", "IService"}:
                domain_services.add(name)


    return {
        "aggregates": sorted(aggregates),
        "value_objects": sorted(value_objects),
        "domain_events": sorted(domain_events),
        "events": sorted(domain_events),
        "repositories": sorted(repositories),
        "domain_services": sorted(domain_services),
    }
