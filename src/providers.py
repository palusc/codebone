"""Brain providers for codebone: Built-in (Metal Qwen), Local URL, Cloud BYOK, and Fast Fallback."""
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False
    requests = None

from .config import Config
from .prompts import build_prompt, ground_analysis

logger = logging.getLogger("codebone.providers")

try:
    from llama_cpp import Llama
    _LLAMA_CPP_AVAILABLE = True
except ImportError:
    _LLAMA_CPP_AVAILABLE = False

REQUEST_TIMEOUT = 15


# (domain from prompts.DOMAIN_VOCAB, path/content terms). A path hit is strong evidence; a hit in the code must recur.
DOMAIN_PATTERNS = [
    ("Payment & Billing", (r"billing", r"payment", r"stripe", r"invoice", r"checkout", r"subscription", r"pricing")),
    ("Authentication & Identity", (r"auth", r"login", r"signup", r"jwt", r"password", r"credential", r"oauth")),
    ("Notifications & Messaging", (r"notif", r"email", r"sms", r"mailer", r"webhook")),
    ("Data Persistence & Storage", (r"schema", r"database", r"sqlite", r"postgres", r"migration", r"repository", r"orm")),
    ("API & Routing", (r"router", r"endpoint", r"controller", r"middleware", r"gateway")),
    ("Search & Analytics", (r"search", r"analytic", r"telemetry", r"metric")),
    ("Configuration & Core", (r"config", r"setting", r"bootstrap", r"logging")),
]
# Structure-only signals (checked against the path, never the code)
PATH_DOMAINS = [
    ("Testing", re.compile(r"(^|/)(tests?|spec|__tests__)(/|$)|(^|/)(test_[^/]*|[^/]*_test\.\w+|[^/]*\.(test|spec)\.\w+)$")),
    ("Documentation", re.compile(r"\.(md|markdown|txt)$|(^|/)docs?/")),
    ("Build & Deployment", re.compile(r"(^|/)(Dockerfile|Makefile|Jenkinsfile|Containerfile|Procfile)$|(^|/)(scripts?|deploy|ci)/|\.(sh|bash|zsh)$")),
    ("User Interface", re.compile(r"\.(html?|css|scss|sass|less|vue|svelte|astro|tsx|jsx)$|(^|/)(ui|views?|components?|templates?)/")),
    ("Background Jobs", re.compile(r"(^|/)(jobs?|workers?|cron|tasks?|queues?)(/|_|\.)")),
    ("Utilities", re.compile(r"(^|/)(utils?|helpers?|lib|common)(/|_|\.)")),
]


class Provider:
    # Which analyser produced the last sniff() result: "model" or "regex" (the fallback). Stored per file so rows
    # written without a model can be re-analysed once one is available.
    last_source = "model"

    @property
    def ready(self) -> bool:
        """Whether sniff() can use its real model right now, without loading or contacting anything."""
        return self.available

    def sniff(self, file_path: str, code: str) -> str:
        raise NotImplementedError

    def generate(self, prompt: str, max_tokens: int = 250) -> str:
        raise NotImplementedError

    def reconcile_architecture(
        self,
        previous_domains: list[str],
        previous_entities: dict,
        delta: dict,
    ) -> tuple[list[str], str]:
        from .prompts import build_reconciliation_prompt, parse_reconciliation
        prompt = build_reconciliation_prompt(previous_domains, previous_entities, delta)
        raw = self.generate(prompt, max_tokens=220)
        if not raw:
            return FastFallbackProvider().reconcile_architecture(previous_domains, previous_entities, delta)
        domains, summary = parse_reconciliation(raw)
        if not domains:
            fb_domains, _ = FastFallbackProvider().reconcile_architecture(previous_domains, previous_entities, delta)
            domains = fb_domains
        return domains, summary

    def _fallback_sniff(self, file_path: str, code: str) -> str:
        fb = getattr(self, "_fallback", None) or FastFallbackProvider()
        out = fb.sniff(file_path, code)
        self.last_source = "regex"
        return out

    def _model_result(self, out: str, file_path: str, code: str) -> str:
        if not out:
            return self._fallback_sniff(file_path, code)
        self.last_source = "model"
        return self._ground(out, file_path, code)

    def _ground(self, out: str, file_path: str, code: str) -> str:
        a = FastFallbackProvider().analyze(file_path, code)
        return ground_analysis(out, code, default_flow=a["summary"],
                               entities=(a["tables"], a["routes"], a["events"]), default_domains=a["path_domains"],
                               supported_domains=a["supported"])

    @property
    def available(self) -> bool:
        raise NotImplementedError


class FastFallbackProvider(Provider):
    """Zero-dependency regex/heuristic scanner that extracts models, routes, and events
    in < 5ms. Used when no local LLM is loaded or while the model is downloading."""

    @property
    def available(self) -> bool:
        return True

    @property
    def ready(self) -> bool:
        return False  # heuristics only: there is no model behind this provider

    def generate(self, prompt: str, max_tokens: int = 250) -> str:
        return ""

    def reconcile_architecture(
        self,
        previous_domains: list[str],
        previous_entities: dict,
        delta: dict,
    ) -> tuple[list[str], str]:
        domains = list(previous_domains)
        all_new_paths = [p for p in delta.get("added", [])] + [new for old, new in delta.get("renamed", [])]
        for p in all_new_paths:
            low = p.lower()
            for d_name, terms in DOMAIN_PATTERNS:
                if any(t in low for t in terms) and d_name not in domains:
                    domains.append(d_name)
        renamed_count = len(delta.get("renamed", []))
        added_count = len(delta.get("added", []))
        modified_count = len(delta.get("modified", []))
        summary = f"Reconciled codebase with {renamed_count} renamed, {modified_count} modified, and {added_count} new files."
        return domains, summary

    def analyze(self, file_path: str, code: str) -> dict:
        """Deterministic extraction straight from the code: tables, routes, events, domains, a one-line summary."""
        tables, routes, events = set(), set(), set()

        # Database tables / models (Django, SQLAlchemy, Prisma, TypeORM, Mongoose, Sequelize, Rails, plain SQL)
        for m in re.finditer(r"class\s+([A-Za-z0-9_]+)\s*\([^)]*(?:Model|Base|Document|Entity)[^)]*\)", code):
            tables.add(m.group(1))
        for m in re.finditer(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]", code):
            tables.add(m.group(1))
        for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?['\"`]?([A-Za-z0-9_]+)['\"`]?", code, re.IGNORECASE):
            tables.add(m.group(1))
        for m in re.finditer(r"^\s*model\s+([A-Za-z0-9_]+)\s*\{", code, re.MULTILINE):  # Prisma
            tables.add(m.group(1))
        for m in re.finditer(r"(?:mongoose\.model|sequelize\.define|\bTable)\(\s*['\"]([A-Za-z0-9_]+)['\"]", code):
            tables.add(m.group(1))
        for m in re.finditer(r"create_table\s*[(:]?\s*['\":]?([A-Za-z0-9_]+)", code):
            tables.add(m.group(1))
        for m in re.finditer(r"@Entity\([^)]*\)\s*(?:export\s+)?class\s+([A-Za-z0-9_]+)", code):
            tables.add(m.group(1))

        # API routes (a real route starts with "/", which keeps dict.get('key') out)
        verbs = r"(get|post|put|delete|patch)"
        for m in re.finditer(rf"@[A-Za-z_][\w.]*\.{verbs}\s*\(\s*['\"](/[^'\"]*)['\"]", code, re.IGNORECASE):
            routes.add(f"{m.group(1).upper()} {m.group(2)}")
        for m in re.finditer(rf"\b(?:app|router|api|server)\.{verbs}\s*\(\s*['\"](/[^'\"]*)['\"]", code, re.IGNORECASE):
            routes.add(f"{m.group(1).upper()} {m.group(2)}")
        for m in re.finditer(r"@[A-Za-z_][\w.]*\.route\s*\(\s*['\"](/[^'\"]*)['\"]", code):
            routes.add(f"ROUTE {m.group(1)}")
        for m in re.finditer(r"@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*)?['\"](/[^'\"]*)['\"]", code):
            routes.add(f"{m.group(1).upper()} {m.group(2)}")
        for m in re.finditer(r"\.(?:HandleFunc|Handle)\(\s*\"(/[^\"]*)\"", code):
            routes.add(f"ROUTE {m.group(1)}")

        # Events
        for m in re.finditer(r"\b(?:emit|dispatch|trigger|publish)\s*\(\s*['\"]([^'\"]+)['\"]", code):
            events.add(m.group(1))
        for m in re.finditer(r"\.on\(\s*['\"]([^'\"]+)['\"]", code):
            events.add(m.group(1))

        path_domains = [name for name, pattern in PATH_DOMAINS if pattern.search(file_path)]
        low_path, low_code = file_path.lower(), code.lower()
        domains = list(path_domains)
        supported = list(path_domains)  # domains a model may claim: the file shows at least one sign of them
        for name, terms in DOMAIN_PATTERNS:
            if any(term in low_path for term in terms) or any(len(re.findall(rf"\b{term}", low_code)) >= 3 for term in terms):
                if name not in domains:
                    domains.append(name)
            if name not in supported and any(term in low_path or re.search(rf"\b{term}", low_code) for term in terms):
                supported.append(name)

        defs = re.findall(r"(?:def|class|function|const)\s+([A-Za-z0-9_]+)", code)
        consts = re.findall(r"^([A-Z][A-Z0-9_]{2,})\s*=", code, re.MULTILINE)
        if defs:
            summary = f"Defines {', '.join(defs[:6])}" + (f"; constants {', '.join(consts[:6])}" if consts else "") + "."
        else:
            summary = ""  # nothing worth saying (empty __init__.py, data file): keep it out of the context
        return {"tables": sorted(tables), "routes": sorted(routes), "events": sorted(events),
                "domains": domains[:3], "path_domains": path_domains[:2], "supported": supported,
                "summary": summary}

    def sniff(self, file_path: str, code: str) -> str:
        self.last_source = "regex"
        a = self.analyze(file_path, code)
        return (
            f"TABLES: {', '.join(a['tables']) or 'none'}\n"
            f"ROUTES: {', '.join(a['routes']) or 'none'}\n"
            f"EVENTS: {', '.join(a['events']) or 'none'}\n"
            f"DOMAINS: {', '.join(a['domains']) or 'none'}\n"
            f"FLOW: {a['summary']}"
        )


class BuiltinProvider(Provider):
    """llama-cpp-python running Qwen2.5-Coder GGUF, Metal-accelerated via n_gpu_layers=-1."""

    def __init__(self, model_path: str, n_ctx: int = 2048, n_gpu_layers: int = -1):
        self.model_path = Path(model_path)
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self._llm: Optional["Llama"] = None
        self._fallback = FastFallbackProvider()
        self._load_lock = threading.Lock()
        self._gen_lock = threading.Lock()  # llama.cpp contexts are not thread safe
        self._load_failed_at = 0.0
        import atexit
        atexit.register(self.close)

    def close(self):
        """Release Metal GPU context cleanly before process exit (waits for a running generation)."""
        with self._gen_lock:
            self._close_locked()

    def _close_locked(self):
        if self._llm is not None:
            try:
                if hasattr(self._llm, "close"):
                    self._llm.close()
            except Exception:
                pass
            self._llm = None
            import gc
            gc.collect()

    @property
    def available(self) -> bool:
        return self._ensure_loaded()

    @property
    def ready(self) -> bool:
        """Cheap readiness check: model file present and llama.cpp importable. Never loads the model."""
        return self._llm is not None or (_LLAMA_CPP_AVAILABLE and self.model_path.exists())

    def _ensure_loaded(self) -> bool:
        if self._llm is not None:
            return True
        if not _LLAMA_CPP_AVAILABLE or not self.model_path.exists():
            return False
        if self._load_failed_at and time.monotonic() - self._load_failed_at < 60:
            return False  # do not retry a failing load for every file
        with self._load_lock:
            return self._load_locked()

    def _load_locked(self) -> bool:
        if self._llm is not None:
            return True
        try:
            self._llm = Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_gpu_layers=self.n_gpu_layers,
                verbose=False,
            )
            logger.info("Loaded built-in GGUF brain: %s", self.model_path)
            return True
        except Exception as exc:
            logger.error("Failed to load built-in brain: %s", exc)
            self._load_failed_at = time.monotonic()
            return False

    def generate(self, prompt: str, max_tokens: int = 250) -> str:
        if not self._ensure_loaded():
            return ""
        try:
            with self._gen_lock:
                res = self._llm.create_chat_completion(
                    messages=[
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.1,
                )
            return res["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("Generation error in BuiltinProvider: %s", exc)
            return ""

    def _fit_prompt(self, file_path: str, code: str, max_tokens: int) -> str:
        """Shrink the code until instructions + code + answer fit the context window; an oversized prompt makes
        llama.cpp raise, which used to drop the file to the regex fallback without anyone noticing."""
        budget = self.n_ctx - max_tokens - 64
        lines = [ln[:300] for ln in code.splitlines()]  # a minified one-liner alone could exceed the window
        keep = min(len(lines), 250)
        while True:
            prompt = build_prompt(file_path, "\n".join(lines[:keep]))
            if keep <= 8 or len(self._llm.tokenize(prompt.encode("utf-8"), add_bos=False)) <= budget:
                return prompt
            keep = max(8, int(keep * 0.7))

    def sniff(self, file_path: str, code: str) -> str:
        if not self._ensure_loaded():
            return self._fallback_sniff(file_path, code)
        out = self.generate(self._fit_prompt(file_path, code, 90), max_tokens=90)
        return self._model_result(out, file_path, code)


class LocalUrlProvider(Provider):
    """Pointed at an external Ollama or OpenAI-compatible server (LM Studio, vLLM)."""

    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self._fallback = FastFallbackProvider()

    @property
    def available(self) -> bool:
        try:
            # Check Ollama /api/version or base url
            r = requests.get(self.url.replace("/api/generate", "/api/version"), timeout=2)
            return r.status_code < 500
        except Exception:
            return False

    def generate(self, prompt: str, max_tokens: int = 250) -> str:
        try:
            if "api/generate" in self.url or ":11434" in self.url:
                url = self.url if "api/generate" in self.url else f"{self.url}/api/generate"
                r = requests.post(
                    url,
                    json={"model": "qwen2.5-coder:0.5b", "prompt": prompt, "stream": False},
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    return r.json().get("response", "").strip()
            else:
                url = self.url if self.url.endswith("/chat/completions") else f"{self.url}/v1/chat/completions"
                r = requests.post(
                    url,
                    json={
                        "model": "default",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("LocalUrlProvider generation error: %s", exc)
        return ""

    def sniff(self, file_path: str, code: str) -> str:
        prompt = build_prompt(file_path, code)
        out = self.generate(prompt, max_tokens=90)
        return self._model_result(out, file_path, code)


class CloudProvider(Provider):
    """Cloud BYOK provider (OpenAI or Anthropic)."""

    def __init__(self, vendor: str, api_key: str, model: str):
        self.vendor = vendor.lower()
        self.api_key = api_key
        self.model = model
        self._fallback = FastFallbackProvider()

    @property
    def available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 8)

    def generate(self, prompt: str, max_tokens: int = 250) -> str:
        if not self.available:
            return ""
        try:
            if self.vendor == "anthropic":
                r = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model or "claude-sonnet-5",
                        "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    return r.json()["content"][0]["text"].strip()
            else:
                # OpenAI
                r = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model or "gpt-6",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("CloudProvider generation error: %s", exc)
        return ""

    def sniff(self, file_path: str, code: str) -> str:
        if not self.available:
            return self._fallback_sniff(file_path, code)

        prompt = build_prompt(file_path, code)
        out = self.generate(prompt, max_tokens=90)
        return self._model_result(out, file_path, code)


def build_provider(config: Config) -> Provider:
    kind = config.get("brain_provider", "builtin")
    if kind == "local_url":
        url = config.get("brain_local_url", "http://localhost:11434/api/generate")
        return LocalUrlProvider(url)
    elif kind == "cloud":
        return CloudProvider(
            vendor=config.get("brain_cloud_vendor", "openai"),
            api_key=config.get("brain_cloud_api_key", ""),
            model=config.get("brain_cloud_model", "gpt-6"),
        )
    else:
        model_path = config.get("model_path")
        return BuiltinProvider(model_path=model_path)
