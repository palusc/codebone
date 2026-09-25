"""Test suite for codebone's Smart Scan Adoption and AI Structural Reconciliation."""
import os
import shutil
import tempfile
from pathlib import Path

from src.config import Config
from src.providers import FastFallbackProvider
from src.scans import ScanManager, ScanReconciler
from src.storage import Storage


def test_scan_adoption_and_reconciliation():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        proj_v1 = tmp_path / "project_v1"
        proj_v2 = tmp_path / "project_v2"
        proj_v1.mkdir()
        proj_v2.mkdir()

        # Step 1: Create initial project files in v1
        auth_file = proj_v1 / "auth.py"
        auth_file.write_text(
            "class User(Model):\n    __tablename__ = 'users'\n"
            "@app.post('/api/login')\ndef login():\n    return 'jwt'\n"
        )
        billing_file = proj_v1 / "billing.py"
        billing_file.write_text(
            "class Invoice(Model):\n    __tablename__ = 'invoices'\n"
            "@app.post('/api/checkout')\ndef checkout():\n    emit('payment_processed')\n"
        )
        order_file = proj_v1 / "order_service.py"
        order_file.write_text(
            "@app.get('/api/orders')\ndef get_orders():\n    return []\n"
        )

        config = Config(config_file=tmp_path / "config.json")
        config.data["watched_extensions"] = [".py"]
        config.data["ignore_dirs"] = [".git"]
        config.data["project_path"] = str(proj_v1)

        storage_v1 = Storage(tmp_path / "v1.sqlite3")
        provider = FastFallbackProvider()

        # Populate storage_v1
        for p in [auth_file, billing_file, order_file]:
            rel = str(p.relative_to(proj_v1))
            code = p.read_text()
            raw = provider.sniff(rel, code)
            import hashlib
            h = hashlib.sha256(code.encode()).hexdigest()
            storage_v1.update_file(rel, raw, mtime=p.stat().st_mtime, content_hash=h)

        assert storage_v1.file_count() == 3

        # Save snapshot
        manager = ScanManager(config)
        snap = manager.save_snapshot("project_v1", proj_v1, storage_v1, scan_id="test_v1")
        assert snap["file_count"] == 3
        assert "Payment & Billing" in snap["domains"]

        # Step 2: Set up project_v2 (folder moved/renamed + changes)
        # - billing.py was moved to src/services/billing.py (exact same content)
        # - order_service.py was modified
        # - notification.py was added
        # - auth.py was deleted
        (proj_v2 / "src" / "services").mkdir(parents=True)
        (proj_v2 / "src" / "services" / "billing.py").write_text(billing_file.read_text())

        (proj_v2 / "order_service.py").write_text(
            "@app.get('/api/orders')\ndef get_orders():\n    # modified\n    return ['order-1']\n"
        )
        (proj_v2 / "notification.py").write_text(
            "@app.post('/api/webhook/email')\ndef send_receipt():\n    emit('email_sent')\n"
        )

        storage_v2 = Storage(tmp_path / "v2.sqlite3")

        # Step 3: Run ScanReconciler
        report = ScanReconciler.reconcile(
            target_project=proj_v2,
            source_db_path=Path(snap["db_path"]),
            target_storage=storage_v2,
            provider=provider,
            config=config,
        )

        # Assertions
        assert report["total_target_files"] == 3
        assert report["renamed_count"] == 1
        assert report["renamed_pairs"] == [("billing.py", "src/services/billing.py")]
        assert report["modified_count"] == 1
        assert report["added_count"] == 1
        assert report["deleted_count"] == 1

        # Check target storage
        assert storage_v2.file_count() == 3
        renamed_rec = storage_v2.get_file("src/services/billing.py")
        assert renamed_rec is not None
        assert "invoices" in renamed_rec["tables"]
        assert "Payment & Billing" in renamed_rec["domains"]

        # Check graph edges in target storage
        # Files here share no real entity/domain, so no edge is expected (the old heuristic linked everything).
        assert storage_v2.graph_edges() == []

        print("Reconciliation test passed successfully! Report:", report)


def test_api_endpoints():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        proj_dir = tmp_path / "my_api_project"
        proj_dir.mkdir()
        (proj_dir / "app.py").write_text("@app.get('/ping')\ndef ping(): return 'pong'\n")

        config = Config(config_file=tmp_path / "config.json")
        config.data["project_path"] = str(proj_dir)
        config.data["watched_extensions"] = [".py"]
        config.data["ignore_dirs"] = []
        config.data["brain_provider"] = "fallback"

        from src.server import create_app
        from src.service import PugService
        from fastapi.testclient import TestClient

        service = PugService(config)
        service.rescan_all()

        app = create_app(service)
        client = TestClient(app, base_url="http://127.0.0.1")

        # 1. Test GET /codebone/scans (and /pug/scans)
        res = client.get("/codebone/scans")
        assert res.status_code == 200
        data = res.json()
        assert "scans" in data
        assert data["count"] >= 1
        assert client.get("/pug/scans").status_code == 200

        # 2. Test GET /codebone/status (and /pug/status)
        status_res = client.get("/codebone/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["file_count"] == 1
        assert client.get("/pug/status").status_code == 200

        # 3. Test GET /codebone/context, /codebone/graph, and /codebone/graph/ui
        assert client.get("/codebone/context").status_code == 200
        graph_res = client.get("/codebone/graph")
        assert graph_res.status_code == 200
        assert "files" in graph_res.json()
        ui_res = client.get("/codebone/graph/ui")
        assert ui_res.status_code == 200
        assert "codebone — Semantic Code Graph" in ui_res.text
        assert "metrics-bar" in ui_res.text

        # 4. Test POST /codebone/scans/adopt with a new moved folder
        new_proj_dir = tmp_path / "my_api_project_moved"
        new_proj_dir.mkdir()
        (new_proj_dir / "app_v2.py").write_text((proj_dir / "app.py").read_text())

        latest_scan = data["scans"][0]["id"]
        adopt_res = client.post(
            "/codebone/scans/adopt",
            json={"scan_id": latest_scan, "project_path": str(new_proj_dir)},
        )
        assert adopt_res.status_code == 200
        adopt_data = adopt_res.json()
        assert adopt_data["status"] == "success"
        assert adopt_data["report"]["renamed_count"] == 1
        assert adopt_data["report"]["renamed_pairs"] == [["app.py", "app_v2.py"]]

        service.stop()
        del client, app, service
        import gc
        gc.collect()

        print("API endpoint tests passed successfully!")


def test_force_rescan_reanalyzes_unchanged_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        (proj_dir / "app.py").write_text("@app.get('/ping')\ndef ping(): return 'pong'\n")

        config = Config(config_file=tmp_path / "config.json")
        config.data["project_path"] = str(proj_dir)
        config.data["watched_extensions"] = [".py"]
        config.data["ignore_dirs"] = []
        config.data["brain_provider"] = "fallback"

        from src.service import PugService

        service = PugService(config)
        total, sniffed, skipped = service.rescan_all()
        assert (total, sniffed, skipped) == (1, 1, 0)

        # A normal rescan with unchanged content is skipped (content hash short-circuit)
        total, sniffed, skipped = service.rescan_all()
        assert (total, sniffed, skipped) == (1, 0, 1)

        # force=True must bypass both the mtime AND the content-hash short-circuit,
        # otherwise a forced pass would never actually re-run unchanged files through the brain
        total, sniffed, skipped = service.rescan_all(force=True)
        assert (total, sniffed, skipped) == (1, 1, 0)

        service.stop()
        print("Force rescan re-sniff test passed successfully!")


if __name__ == "__main__":
    test_scan_adoption_and_reconciliation()
    test_api_endpoints()
    test_force_rescan_reanalyzes_unchanged_files()
