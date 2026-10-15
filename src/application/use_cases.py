"""Application Use Cases for CodeBone (DDD Application Layer).

Orchestrates domain entities, ports, and external adapters for:
- Querying codebase architecture context (for coding agents)
- Scanning and analyzing projects (deterministic + semantic synthesis)
- Reconciling architecture changes
- Managing scan snapshots and registries
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..domain.models import ArchitectureGraph, BoundedContext, DDDRole, FileRecord
from ..domain.ports import AnalysisProviderPort, StoragePort

logger = logging.getLogger("codebone.application.use_cases")


class GetArchitectureContextUseCase:
    """Application Service: Generates compact architecture views and query drill-downs for AI agents."""

    def __init__(self, storage: StoragePort):
        self.storage = storage

    def get_overview(self, project_name: str, fresh: str = "") -> str:
        """Renders whole-project architecture overview with bounded contexts, aggregates, and entities."""
        from .. import context_format as cf
        files = [f.to_dict() if isinstance(f, FileRecord) else f for f in self.storage.list_files()]
        index = self.storage.entity_index()
        return cf.overview(project_name, files, index, fresh=fresh)

    def query_context(
        self,
        project_name: str,
        query: str = "",
        domain: str = "",
        file_pattern: str = "",
        whisper: bool = False,
        assets: bool = False,
    ) -> str:
        """Answers architectural queries with ranked files, symbols, and DDD relationships."""
        from .. import context_format as cf
        files = [f.to_dict() if isinstance(f, FileRecord) else f for f in self.storage.list_files()]
        index = self.storage.entity_index()

        if whisper or not query:
            return cf.search(
                project_name=project_name,
                files=files,
                index=index,
                domain=domain,
                file=file_pattern,
                query=query,
                assets=assets,
            )
        else:
            return cf.offer(
                project_name=project_name,
                files=files,
                index=index,
                domain=domain,
                file=file_pattern,
                query=query,
                assets=assets,
            )


class ScanProjectUseCase:
    """Application Service: Coordinates file scanning, fact extraction, and graph persistence."""

    def __init__(self, storage: StoragePort, provider: AnalysisProviderPort):
        self.storage = storage
        self.provider = provider

    def analyze_and_record(
        self,
        rel_path: str,
        code: str,
        mtime: float = 0.0,
        content_hash: str = "",
    ) -> FileRecord:
        """Analyzes a source file and stores its architectural facts in the storage repository."""
        raw_output = self.provider.sniff(rel_path, code)
        source = getattr(self.provider, "last_source", "model")

        # Let storage update and persist
        record_dict = getattr(self.storage, "update_file", None)
        if callable(record_dict):
            d = self.storage.update_file(
                rel_path=rel_path,
                raw_output=raw_output,
                mtime=mtime,
                content_hash=content_hash,
                source=source,
            )
            return FileRecord.from_dict(d)

        # Fallback to direct port usage
        from ..prompts import parse_analysis
        parsed = parse_analysis(raw_output)
        rec = FileRecord(
            path=rel_path,
            tables=parsed.tables,
            routes=parsed.routes,
            events=parsed.events,
            domains=parsed.domains,
            summary=parsed.summary,
            updated_at=time.time(),
            mtime=mtime,
            content_hash=content_hash,
            source=source,
            aggregates=parsed.aggregates,
            value_objects=parsed.value_objects,
            repositories=parsed.repositories,
            domain_services=parsed.domain_services,
            bounded_context=parsed.bounded_context,
        )
        self.storage.put_file(rec)
        return rec


class ReconcileArchitectureUseCase:
    """Application Service: Reconciles architectural evolution when files change."""

    def __init__(self, storage: StoragePort, provider: AnalysisProviderPort):
        self.storage = storage
        self.provider = provider

    def reconcile(self, delta: Dict[str, list]) -> Tuple[List[str], str]:
        all_files = [f.to_dict() if isinstance(f, FileRecord) else f for f in self.storage.list_files()]
        index = self.storage.entity_index()
        previous_domains = list(index.get("domains", {}).keys())
        previous_entities = {
            "tables": list(index.get("tables", {}).keys()),
            "routes": list(index.get("routes", {}).keys()),
            "events": list(index.get("events", {}).keys()),
            "aggregates": list(index.get("aggregates", {}).keys()),
        }

        reconcile_method = getattr(self.provider, "reconcile_architecture", None)
        if callable(reconcile_method):
            return reconcile_method(previous_domains, previous_entities, delta)
        return previous_domains, "Reconciliation complete."


class AddGitHubRepositoryUseCase:
    """Application Service: Clones a GitHub repository, registers it, and initiates codebase scanning."""

    def __init__(self, service_or_config, provider: Optional[AnalysisProviderPort] = None):
        self.service = service_or_config
        self.provider = provider

    def execute(
        self,
        identifier: str,
        target_dir: Optional[Path] = None,
        branch: Optional[str] = None,
        auto_scan: bool = True,
    ) -> Path:
        from ..github import clone_github_repo
        cloned_path = clone_github_repo(identifier, target_dir=target_dir, branch=branch)

        config = getattr(self.service, "config", self.service)
        if hasattr(config, "add_project_path"):
            config.add_project_path(str(cloned_path))
            config.set("project_path", str(cloned_path))

        if hasattr(self.service, "activate_project"):
            self.service.activate_project(cloned_path)
        elif hasattr(self.service, "start"):
            self.service.start(auto_scan=auto_scan)

        return cloned_path

