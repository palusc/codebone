from src import codesearch
from src import context_format as cf
from src.storage import Storage


def rows(n):
    out = []
    for i in range(n):
        out.append({"path": f"pkg{i % 7}/m{i}.py", "summary": f"Handles thing {i} with a rather long description " * 3,
                    "tables": [f"T{i % 20}"], "routes": [f"GET /r{i % 30}"] if i % 3 == 0 else [], "events": [],
                    "domains": [f"Domain{i % 5}"], "source": "model"})
    return out


def index_of(files):
    return Storage._build_index(files)


def test_overview_size_is_bounded_and_deterministic():
    small, big = rows(50), rows(3000)
    a, b = cf.overview("p", big, index_of(big)), cf.overview("p", big, index_of(big))
    assert a == b
    assert len(a) < 12000  # about 3k tokens even for 3000 files
    assert len(cf.overview("p", small, index_of(small))) < len(a)
    assert "top 60 of 3000" in a


def test_search_ranks_filename_hits_first_and_caps_output():
    files = rows(400)
    files.append({"path": "billing/invoice_service.py", "summary": "Creates invoices", "tables": ["Invoice"],
                  "routes": [], "events": [], "domains": ["Billing"], "source": "model"})
    out = cf.search("p", files, index_of(files), query="invoice")
    assert out.index("billing/invoice_service.py") < out.index("### pkg") if "### pkg" in out else True
    many = cf.search("p", files, index_of(files), query="thing")
    assert many.count("### ") <= cf.MAX_MATCHES
    assert "(+" in many


def test_trivial_files_are_counted_not_listed():
    files = rows(3) + [{"path": "pkg/__init__.py", "summary": "", "tables": [], "routes": [], "events": [],
                        "domains": [], "source": "model"}]
    text = cf.overview("p", files, index_of(files))
    assert "__init__" not in text and "1 files without notable content omitted" in text


def test_word_search_symbols_assets_grouping_and_domain_boost(tmp_path):
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "Sidebar.tsx").write_text(
        "import { AskmentIcon } from './Icon'\nexport const Sidebar = () => <AskmentIcon color={dark}/>\n")
    (tmp_path / "ui" / "Icon.tsx").write_text("// logo mark\nexport function AskmentIcon() { return null }\n")
    files = [
        {"path": "ui/Sidebar.tsx", "summary": "Navigation", "tables": [], "routes": [], "events": [], "domains": ["User Interface"], "source": "model"},
        {"path": "ui/Icon.tsx", "summary": "Icon", "tables": [], "routes": [], "events": [], "domains": ["User Interface"], "source": "model"},
        *({"path": f"apps/{a}/public/logo.png", "summary": "image file (19.4 KB)", "tables": [], "routes": [], "events": [],
           "domains": ["Assets"], "source": "asset"} for a in ("a", "b", "c")),
    ]
    idx = index_of(files)
    texts = codesearch.read_texts(str(tmp_path), files)
    out = cf.search("p", files, idx, domain="Landing", query="AskmentIcon", texts=texts)
    assert "defined at ui/Icon.tsx:2" in out and "ui/Sidebar.tsx:2" in out  # other domain still ranks, symbol refs listed
    assert 'Domain "Landing": 0 hits in it, 2 elsewhere' in out and "(score" in out and "L2:" in out
    assert "logo.png" not in cf.search("p", files, idx, query="logo", texts=texts)
    assert "asset files also match" in cf.search("p", files, idx, query="logo", texts=texts)
    shown = cf.search("p", files, idx, query="logo", texts=texts, assets=True)
    assert shown.count("### apps") == 1 and "Same file in 2 more places" in shown


def test_offer_is_short_and_points_to_the_full_answer(tmp_path):
    (tmp_path / "billing").mkdir()
    (tmp_path / "billing" / "webhook.py").write_text("def handle_webhook(event):\n    return event\n")
    files = [{"path": "billing/webhook.py", "summary": "Stripe webhook", "tables": [], "routes": [], "events": [],
              "domains": ["Payment"], "source": "model"},
             *({"path": f"apps/w{i}/webhook_{i}.py", "summary": "webhook handler " * 12, "tables": [], "routes": [],
                "events": [], "domains": [], "source": "model"} for i in range(9)),
             {"path": "tests/test_webhook.py", "summary": "webhook tests", "tables": [], "routes": [], "events": [],
              "domains": [], "source": "model"}]
    idx = index_of(files)
    texts = codesearch.read_texts(str(tmp_path), files)
    out = cf.offer("p", files, idx, query="webhook", texts=texts)
    assert "Top: billing/webhook.py:1 def handle_webhook" in out and "Tests: tests/test_webhook.py" in out
    assert "whisper=true" in out and len(out) < len(cf.search("p", files, idx, query="webhook", texts=texts)) + 200
    assert "No match" in cf.offer("p", files, idx, query="zzzzqq", texts=texts)
    small = cf.offer("p", files[:1] + files[-1:], index_of(files[:1] + files[-1:]), query="webhook", texts=texts)
    assert "whisper" not in small and "### billing/webhook.py" in small  # small answers skip the offer step
