"""Domain Ports (Interfaces) for CodeBone following Ports and Adapters / Hexagonal Architecture."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import FileRecord


class StoragePort(ABC):
    """Abstract port for persisting and querying architecture graph records."""

    @abstractmethod
    def get_file(self, path: str) -> Optional[FileRecord]:
        """Fetch single file record."""
        pass

    @abstractmethod
    def put_file(self, record: FileRecord) -> None:
        """Store or update file record."""
        pass

    @abstractmethod
    def list_files(self) -> List[FileRecord]:
        """List all indexed file records."""
        pass

    @abstractmethod
    def delete_file(self, path: str) -> bool:
        """Delete file record."""
        pass

    @abstractmethod
    def entity_index(self) -> Dict[str, Dict[str, List[str]]]:
        """Build index of domains, tables, routes, events, aggregates, value_objects, repositories."""
        pass

    @abstractmethod
    def file_count(self) -> int:
        """Count total files."""
        pass


class AnalysisProviderPort(ABC):
    """Abstract port for analyzing source code (via AST, regex, or LLM)."""

    @abstractmethod
    def sniff(self, file_path: str, code: str) -> str:
        """Analyze a single file and produce summary and entities."""
        pass

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 250, system_prompt: str = "") -> str:
        """Generate text using provider model."""
        pass
