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
