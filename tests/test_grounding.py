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


def test_hybrid_fusion_merges_scanner_facts_and_verified_model_discoveries():
    from src.prompts import ground_analysis
    code = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/users')\n"
        "def list_users(): return []\n"
        "class UserRecord(Model): pass\n"
        "emitter.emit('user_registered')\n"
    )
    # Deterministic scanner found UserRecord and GET /users
    static_entities = (["UserRecord"], ["GET /users"], [])
    # Model hallucinated FakeTable, but legitimately noticed user_registered and an extra verified route
    raw_model = (
        "TABLES: UserRecord, FakeTable\n"
        "ROUTES: GET /users\n"
        "EVENTS: user_registered, fake_event\n"
        "DOMAINS: Authentication & Identity\n"
        "FLOW: Handles user listing and emits registration events."
    )
    out = ground_analysis(raw_model, code, default_flow="Defines UserRecord.", entities=static_entities,
                          default_domains=["Configuration & Core"])
    # FakeTable and fake_event dropped (not in code), UserRecord and user_registered kept!
    assert "TABLES: UserRecord" in out and "FakeTable" not in out
    assert "ROUTES: GET /users" in out
    assert "EVENTS: user_registered" in out and "fake_event" not in out
    assert "DOMAINS: Authentication & Identity" in out
    assert "FLOW: Handles user listing and emits registration events." in out


def test_multilanguage_deterministic_scanner_covers_modern_frameworks():
    from src.providers import FastFallbackProvider
    scanner = FastFallbackProvider()

    # TypeScript / Drizzle ORM & BullMQ & Hono
    ts_code = (
        "import { pgTable, text } from 'drizzle-orm/pg-core';\n"
        "export const customers = pgTable('customers', { id: text('id') });\n"
        "app.post('/api/checkout', (c) => c.text('ok'));\n"
        "emailQueue.add('welcome_email', { to: 'a@b.com' });\n"
    )
    a_ts = scanner.analyze("src/checkout.ts", ts_code)
    assert "customers" in a_ts["tables"]
    assert "POST /api/checkout" in a_ts["routes"]
    assert "welcome_email" in a_ts["events"]

    # Go GORM & Gin & Kafka
    go_code = (
        "type Order struct {\n"
        "    gorm.Model\n"
        "}\n"
        "r.GET(\"/orders\", handleOrders)\n"
        "msg := kafka.Message{topic: \"orders.created\"}\n"
    )
    a_go = scanner.analyze("handlers/order.go", go_code)
    assert "Order" in a_go["tables"]
    assert "GET /orders" in a_go["routes"]
    assert "orders.created" in a_go["events"]

    # Rust Actix-web
    rust_code = (
        "#[get(\"/healthz\")]\n"
        "async fn health() -> impl Responder { \"ok\" }\n"
        "table! { products (id) { id -> Integer, } }\n"
    )
    a_rs = scanner.analyze("src/main.rs", rust_code)
    assert "products" in a_rs["tables"]
    assert "ROUTE /healthz" in a_rs["routes"]

    # C# ASP.NET & Entity Framework
    cs_code = (
        "public class AppDbContext : DbContext {\n"
        "    public DbSet<Invoice> Invoices { get; set; }\n"
        "}\n"
        "[HttpGet(\"/invoices/summary\")]\n"
        "public IActionResult Get() { return Ok(); }\n"
    )
    a_cs = scanner.analyze("Controllers/InvoiceController.cs", cs_code)
    assert "Invoice" in a_cs["tables"]
    assert "GET /invoices/summary" in a_cs["routes"]

    # PHP Laravel
    php_code = (
        "class Subscription extends Model {}\n"
        "Route::post('/subscribe', [SubController::class, 'store']);\n"
    )
    a_php = scanner.analyze("routes/web.php", php_code)
    assert "Subscription" in a_php["tables"]
    assert "POST /subscribe" in a_php["routes"]

