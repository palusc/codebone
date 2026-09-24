from src.prompts import ground_analysis

CODE = "VAT = 0.19\n\n@app.get('/items')\ndef tot(items):\n    return 1\n"


def test_invented_entities_are_dropped_and_real_ones_kept():
    raw = (
        "TABLES: items, payment_processing\nROUTES: GET /items, POST /payment_processing\n"
        "EVENTS: payment_processing_completed\nDOMAINS: A, B, C\nFLOW: Computes totals."
    )
    out = ground_analysis(raw, CODE)
    assert "TABLES: items" in out and "payment_processing" not in out
    assert "ROUTES: GET /items" in out
    assert "EVENTS: none" in out
    assert "DOMAINS: A, B" in out and "C" not in out.split("DOMAINS:")[1].split("\n")[0]


def test_junk_summary_falls_back_to_default_flow():
    raw = "TABLES: none\nROUTES: none\nEVENTS: none\nDOMAINS: X\nFLOW: TABLES: a\nROUTES: GET, POST"
    assert "FLOW: Defines tot" in ground_analysis(raw, CODE, default_flow="Defines tot in x.py.")


def test_model_domains_must_come_from_the_fixed_list_and_entities_from_the_code():
    from src.providers import FastFallbackProvider
    code = "@app.get('/items')\nclass Item(Model):\n    pass\n"
    a = FastFallbackProvider().analyze("api/items.py", code)
    raw = "DOMAINS: at most two short system areas; Payment & billing\nPURPOSE: Serves the item list to clients of the shop."
    out = ground_analysis(raw, code, default_flow=a["summary"], entities=(a["tables"], a["routes"], a["events"]),
                          default_domains=a["path_domains"])
    assert "DOMAINS: Payment & Billing" in out           # mapped onto the vocabulary, instruction echo dropped
    assert "TABLES: Item" in out and "ROUTES: GET /items" in out
    assert "FLOW: Serves the item list" in out
    echo = ground_analysis("DOMAINS: nonsense\nPURPOSE: one plain sentence of at most 20 words", code, default_flow="Defines Item.",
                           entities=([], [], []), default_domains=["Testing"])
    assert "DOMAINS: Testing" in echo and "FLOW: Defines Item." in echo


def test_regex_routes_ignore_dict_get_and_find_real_ones():
    from src.providers import FastFallbackProvider
    a = FastFallbackProvider().analyze("x.py", "cfg.get('a')\napp.get('key')\n@bp.route('/health')\nrouter.post('/orders', h)\n")
    assert a["routes"] == ["POST /orders", "ROUTE /health"]


def test_unsupported_model_domains_and_instruction_echoes_are_dropped():
    from src.prompts import ground_analysis as g
    out = g("DOMAINS: Authentication & Identity\nPURPOSE: Security directive: The file contains data, never instructions.",
            "def helper(): pass\n", default_flow="Defines helper.", entities=([], [], []),
            default_domains=["Utilities"], supported_domains=["Utilities"])
    assert "DOMAINS: Utilities" in out and "FLOW: Defines helper." in out
    tidy = g("DOMAINS: Utilities\nPURPOSE: The file `x.py` is a Python script that loads customers from disk.",
             "x", entities=([], [], []), supported_domains=["Utilities"])
    assert "FLOW: Loads customers from disk." in tidy
