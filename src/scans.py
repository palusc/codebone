"""Persistent codebase scan snapshots and AI structural reconciliation."""
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .config import Config
from .prompts import parse_analysis
from .providers import Provider
from .storage import Storage

logger = logging.getLogger("codebone.scans")


class ScanManager:
    """Manages saved codebase scans, snapshots, and exports in ~/Library/Application Support/codebone/scans."""

    def __init__(self, config: Config):
        self.config = config
        self.scans_dir = config.scans_dir
        self.registry_file = self.scans_dir / "scans_registry.json"

    def _read_registry(self) -> dict:
        if not self.registry_file.exists():
            return {}
        try:
            return json.loads(self.registry_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_registry(self, data: dict):
        self.scans_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.registry_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.registry_file)

    def list_scans(self) -> List[dict]:
        """List all valid saved codebase scans, updated with current file metadata."""
        reg = self._read_registry()
        valid_scans = []
        changed = False

        for scan_id, meta in list(reg.items()):
            db_path = Path(meta.get("db_path", ""))
            if not db_path.exists():
                # Scan database was deleted
                reg.pop(scan_id, None)
                changed = True
                continue

            # Ensure file count is accurate
            try:
                storage = Storage(db_path)
                meta["file_count"] = storage.file_count()
                idx = storage.entity_index()
                meta["domains"] = list(idx.get("domains", {}).keys())
                meta["tables_count"] = len(idx.get("tables", {}))
                meta["routes_count"] = len(idx.get("routes", {}))
            except Exception:
                pass

            valid_scans.append(meta)

        if changed:
            self._write_registry(reg)

        valid_scans.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
        return valid_scans

    def save_snapshot(
        self,
        project_name: str,
        project_path: Optional[Path],
        storage: Storage,
        scan_id: Optional[str] = None,
    ) -> dict:
        """Create or update a snapshot .sqlite3 database in scans directory."""
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", project_name).lower().strip("_") or "project"
        scan_id = scan_id or f"{slug}_{int(time.time())}"
        dest_db = self.scans_dir / f"{scan_id}.sqlite3"

        storage.snapshot_to(dest_db)

        idx = storage.entity_index()
        domains = list(idx.get("domains", {}).keys())

        meta = {
            "id": scan_id,
            "project_name": project_name,
            "project_path": str(project_path) if project_path else None,
            "db_path": str(dest_db),
            "file_count": storage.file_count(),
            "domains": domains,
            "tables_count": len(idx.get("tables", {})),
            "routes_count": len(idx.get("routes", {})),
            "events_count": len(idx.get("events", {})),
            "updated_at": time.time(),
        }

        reg = self._read_registry()
        reg[scan_id] = meta
        self._write_registry(reg)
        logger.info("Saved scan snapshot '%s' (%d files)", scan_id, meta["file_count"])
        return meta

    def get_scan(self, scan_id_or_path: str) -> Optional[dict]:
        """Find scan by ID, filename, or absolute path."""
        reg = self._read_registry()
        if scan_id_or_path in reg:
            return reg[scan_id_or_path]

        p = Path(scan_id_or_path)
        for meta in reg.values():
            if Path(meta.get("db_path", "")) == p or meta.get("id") == p.stem:
                return meta

        # If it is an external .sqlite3 file that exists on disk
        if p.exists() and p.suffix in (".sqlite3", ".db", ".sqlite"):
            try:
                storage = Storage(p)
                idx = storage.entity_index()
                return {
                    "id": p.stem,
                    "project_name": p.stem,
                    "project_path": None,
                    "db_path": str(p),
                    "file_count": storage.file_count(),
                    "domains": list(idx.get("domains", {}).keys()),
                    "tables_count": len(idx.get("tables", {})),
                    "routes_count": len(idx.get("routes", {})),
                    "events_count": len(idx.get("events", {})),
                    "updated_at": p.stat().st_mtime,
                }
            except Exception:
                return None
        return None

    def find_matching_scan(self, project_path: Path) -> Optional[dict]:
        """Find an existing scan that matches project folder name or previous path."""
        scans = self.list_scans()
        name_lower = project_path.name.lower()
        path_str = str(project_path)

        # Exact path match
        for s in scans:
            if s.get("project_path") == path_str:
                return s

        # Folder name match
        for s in scans:
            if s.get("project_name", "").lower() == name_lower:
                return s

        return None

    def export_scan(self, scan_id_or_path: str, dest_path: Path) -> Path:
        scan = self.get_scan(scan_id_or_path)
        if not scan:
            raise FileNotFoundError(f"Scan '{scan_id_or_path}' not found")
        src_path = Path(scan["db_path"])
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        Storage(src_path).snapshot_to(dest_path)
        return dest_path

    def import_scan(self, source_path: Path, project_name: Optional[str] = None) -> dict:
        if not source_path.exists():
            raise FileNotFoundError(f"Source file {source_path} does not exist")
        p_name = project_name or source_path.stem
        storage = Storage(source_path)
        return self.save_snapshot(project_name=p_name, project_path=None, storage=storage)


class ScanReconciler:
    """Reconciles a target project folder against an existing codebase scan.
    - Zero-cost reuse: files with identical SHA-256 hashes are reused immediately.
    - Path move/rename detection: files whose relative path changed but hash is identical are re-linked.
    - Selective AI sniff: only modified or newly added files are processed by the provider.
    - Architectural reconciliation: passes structural delta to AI to reconcile overarching business domains.
    """

    @staticmethod
    def reconcile(
        target_project: Path,
        source_db_path: Path,
        target_storage: Storage,
        provider: Provider,
        config: Config,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        if not target_project.exists():
            raise FileNotFoundError(f"Target project path does not exist: {target_project}")
        if not source_db_path.exists():
            raise FileNotFoundError(f"Source scan database does not exist: {source_db_path}")

        source_storage = Storage(source_db_path)
        old_files = source_storage.all_files()
        old_by_path: Dict[str, dict] = {f["path"]: f for f in old_files}
        old_by_hash: Dict[str, List[dict]] = {}
        old_domains: set = set()

        for f in old_files:
            h = f.get("content_hash", "")
            if h:
                old_by_hash.setdefault(h, []).append(f)
            for d in f.get("domains", []):
                old_domains.add(d)

        # 1. Discover all current target files on disk
        extensions = set(config.get("watched_extensions", []))
        ignore_dirs = set(config.get("ignore_dirs", []))

        disk_files: List[Path] = []
        for path in target_project.rglob("*"):
            if path.is_file() and path.suffix in extensions and not any(
                part in ignore_dirs for part in path.parts
            ):
                disk_files.append(path)

        total_disk = len(disk_files)
        logger.info(
            "Starting scan reconciliation: %d disk files vs %d source scan files",
            total_disk,
            len(old_files),
        )

        # 2. Compute hash and mtime for disk files
        disk_file_info: List[dict] = []
        for p in disk_files:
            try:
                rel = str(p.relative_to(target_project))
            except ValueError:
                rel = str(p)
            try:
                b = p.read_bytes()
                h = hashlib.sha256(b).hexdigest()
                mtime = p.stat().st_mtime
                disk_file_info.append({"path": p, "rel_path": rel, "hash": h, "mtime": mtime})
            except OSError:
                continue

        # 3. Categorize into: reused, renamed, modified, added
        reused: List[dict] = []
        renamed: List[Tuple[str, str, dict]] = []  # (old_rel, new_rel, record)
        modified: List[dict] = []
        added: List[dict] = []

        unclaimed_old_hashes = dict(old_by_hash)
        matched_disk_rel = set()

        # Step 3a: Exact path + hash matches
        for item in disk_file_info:
            rel = item["rel_path"]
            h = item["hash"]
            if rel in old_by_path:
                old_rec = old_by_path[rel]
                if old_rec.get("content_hash") == h:
                    # Exact match!
                    reused.append({
                        "path": rel,
                        "tables": old_rec.get("tables", []),
                        "routes": old_rec.get("routes", []),
                        "events": old_rec.get("events", []),
                        "domains": old_rec.get("domains", []),
                        "summary": old_rec.get("summary", ""),
                        "mtime": item["mtime"],
                        "content_hash": h,
                    })
                    matched_disk_rel.add(rel)
                    # Remove from unclaimed
                    if h in unclaimed_old_hashes:
                        unclaimed_old_hashes[h] = [x for x in unclaimed_old_hashes[h] if x["path"] != rel]

        # Step 3b: Move/Rename detection for remaining files
        for item in disk_file_info:
            rel = item["rel_path"]
            h = item["hash"]
            if rel in matched_disk_rel:
                continue

            # Check if this content_hash existed in an old file whose old path no longer exists on disk
            if h in unclaimed_old_hashes and unclaimed_old_hashes[h]:
                candidate = unclaimed_old_hashes[h].pop(0)
                old_rel = candidate["path"]
                logger.info("Detected moved/renamed file: %s -> %s (hash: %s)", old_rel, rel, h[:8])
                renamed.append((
                    old_rel,
                    rel,
                    {
                        "path": rel,
                        "tables": candidate.get("tables", []),
                        "routes": candidate.get("routes", []),
                        "events": candidate.get("events", []),
                        "domains": candidate.get("domains", []),
                        "summary": candidate.get("summary", ""),
                        "mtime": item["mtime"],
                        "content_hash": h,
                    },
                ))
                matched_disk_rel.add(rel)

        # Step 3c: Remaining files are modified or added
        for item in disk_file_info:
            rel = item["rel_path"]
            if rel in matched_disk_rel:
                continue
            if rel in old_by_path:
                modified.append(item)
            else:
                added.append(item)

        # Deleted files from old scan
        all_new_rel = {item["rel_path"] for item in disk_file_info}
        renamed_old_paths = {old_p for old_p, _, _ in renamed}
        deleted_paths = [
            p for p in old_by_path.keys()
            if p not in all_new_rel and p not in renamed_old_paths
        ]

        logger.info(
            "Reconciliation diff: %d reused, %d renamed, %d modified, %d added, %d deleted",
            len(reused),
            len(renamed),
            len(modified),
            len(added),
            len(deleted_paths),
        )

        # 4. Clear/Prepare target storage and insert reused & renamed records
        target_storage.reset()

        for rec in reused:
            target_storage.insert_record(rec)

        for _, _, rec in renamed:
            target_storage.insert_record(rec)

        # 5. Sniff modified and added files via Provider
        total_to_sniff = len(modified) + len(added)
        sniffed_count = 0

        for item in modified + added:
            sniffed_count += 1
            if on_progress:
                on_progress(sniffed_count, total_to_sniff, item["rel_path"])
            try:
                code_bytes = item["path"].read_bytes()
                code_str = code_bytes.decode("utf-8", errors="ignore")
                raw_output = provider.sniff(item["rel_path"], code_str[:6000])
                target_storage.update_file(
                    rel_path=item["rel_path"],
                    raw_output=raw_output,
                    mtime=item["mtime"],
                    content_hash=item["hash"],
                )
            except Exception as exc:
                logger.warning("Error sniffing %s during reconciliation: %s", item["rel_path"], exc)

        # 6. AI Architectural Reconciliation pass
        delta = {
            "renamed": [(old_p, new_p) for old_p, new_p, _ in renamed],
            "modified": [item["rel_path"] for item in modified],
            "added": [item["rel_path"] for item in added],
            "deleted": deleted_paths,
        }

        reconciled_domains, arch_summary = provider.reconcile_architecture(
            previous_domains=sorted(old_domains),
            previous_entities=source_storage.entity_index(),
            delta=delta,
        )

        logger.info(
            "AI Architectural Reconciliation: domains=%s, summary=%s",
            reconciled_domains,
            arch_summary,
        )

        return {
            "total_target_files": total_disk,
            "reused_count": len(reused),
            "renamed_count": len(renamed),
            "modified_count": len(modified),
            "added_count": len(added),
            "deleted_count": len(deleted_paths),
            "renamed_pairs": [(old_p, new_p) for old_p, new_p, _ in renamed],
            "active_domains": reconciled_domains,
            "architecture_summary": arch_summary,
        }
