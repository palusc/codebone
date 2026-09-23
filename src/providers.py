"""Brain providers for codebone: Built-in (Metal Qwen), Local URL, Cloud BYOK, and Fast Fallback."""
import json
import logging
import re
from pathlib import Path
from typing import Optional

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False
    requests = None

from .config import Config
from .prompts import build_prompt

logger = logging.getLogger("codebone.providers")

try:
    from llama_cpp import Llama
    _LLAMA_CPP_AVAILABLE = True
except ImportError:
    _LLAMA_CPP_AVAILABLE = False

REQUEST_TIMEOUT = 15


class Provider:
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

    @property
    def available(self) -> bool:
        raise NotImplementedError


class FastFallbackProvider(Provider):
    """Zero-dependency regex/heuristic scanner that extracts models, routes, and events
    in < 5ms. Used when no local LLM is loaded or while the model is downloading."""

    @property
    def available(self) -> bool:
        return True

    def generate(self, prompt: str, max_tokens: int = 250) -> str:
        return ""

    def reconcile_architecture(
        self,
        previous_domains: list[str],
        previous_entities: dict,
        delta: dict,
    ) -> tuple[list[str], str]:
        domains = list(previous_domains)
        domain_patterns = [
            ("Payment & Billing", (r"bill", r"pay", r"stripe", r"invoice", r"checkout", r"subscription", r"pricing")),
            ("Authentication & Identity", (r"auth", r"login", r"signup", r"jwt", r"token", r"session", r"password", r"credential", r"oauth")),
            ("Notifications & Messaging", (r"notif", r"email", r"sms", r"alert", r"webhook", r"mailer", r"push")),
            ("Data Persistence & Storage", (r"model", r"schema", r"database", r"sqlite", r"postgres", r"migration", r"repository", r"dao")),
            ("API & Routing", (r"router", r"endpoint", r"controller", r"handler", r"middleware", r"gateway", r"api")),
            ("Search & Analytics", (r"search", r"query", r"filter", r"analytic", r"telemetry", r"metric", r"tracking")),
            ("Configuration & Core", (r"config", r"setting", r"env", r"bootstrap", r"logging", r"constant")),
        ]
        all_new_paths = [p for p in delta.get("added", [])] + [new for old, new in delta.get("renamed", [])]
        for p in all_new_paths:
            low = p.lower()
            for d_name, terms in domain_patterns:
                if any(t in low for t in terms) and d_name not in domains:
                    domains.append(d_name)
        renamed_count = len(delta.get("renamed", []))
        added_count = len(delta.get("added", []))
        modified_count = len(delta.get("modified", []))
        summary = f"Reconciled codebase with {renamed_count} renamed, {modified_count} modified, and {added_count} new files."
        return domains, summary

    def sniff(self, file_path: str, code: str) -> str:
        tables = set()
        routes = set()
        events = set()

        # Database tables / ORM patterns
        # Python / Django / SQLAlchemy / Prisma / TypeORM / SQL
        for m in re.finditer(r"(?:class\s+([A-Za-z0-9_]+)\s*\([^)]*(?:Model|Base|Document|Entity)[^)]*\))", code):
            tables.add(m.group(1))
        for m in re.finditer(r"(?:__tablename__\s*=\s*['\"]([^'\"]+)['\"])", code):
            tables.add(m.group(1))
        for m in re.finditer(r"(?:CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?['\"`]?([A-Za-z0-9_]+)['\"`]?)", code, re.IGNORECASE):
            tables.add(m.group(1))
        for m in re.finditer(r"(?:model\s+([A-Za-z0-9_]+)\s*\{)", code):  # Prisma
            tables.add(m.group(1))

        # API Routes
        # FastAPI / Flask: @app.get("/path"), router.post("/path")
        for m in re.finditer(r"@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]", code, re.IGNORECASE):
            routes.add(f"{m.group(1).upper()} {m.group(2)}")
        # Express / Node: app.get('/path', ...), router.post(...)
        for m in re.finditer(r"(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]", code, re.IGNORECASE):
            routes.add(f"{m.group(1).upper()} {m.group(2)}")

        # Events
        for m in re.finditer(r"(?:emit|dispatch|on|trigger)\s*\(\s*['\"]([^'\"]+)['\"]", code):
            events.add(m.group(1))

        # Architectural and business domains
        domains = set()
        low_path = file_path.lower()
        low_code = code.lower()

        domain_patterns = [
            ("Payment & Billing", (r"bill", r"pay", r"stripe", r"invoice", r"checkout", r"subscription", r"pricing")),
            ("Authentication & Identity", (r"auth", r"login", r"signup", r"jwt", r"token", r"session", r"password", r"credential", r"oauth")),
            ("Notifications & Messaging", (r"notif", r"email", r"sms", r"alert", r"webhook", r"mailer", r"push")),
            ("Data Persistence & Storage", (r"model", r"schema", r"database", r"sqlite", r"postgres", r"migration", r"repository", r"dao")),
            ("API & Routing", (r"router", r"endpoint", r"controller", r"handler", r"middleware", r"gateway", r"api")),
            ("Search & Analytics", (r"search", r"query", r"filter", r"analytic", r"telemetry", r"metric", r"tracking")),
            ("Configuration & Core", (r"config", r"setting", r"env", r"bootstrap", r"logging", r"constant")),
        ]

        for domain_name, terms in domain_patterns:
            if any(term in low_path for term in terms) or any(re.search(rf"\b{term}", low_code) for term in terms):
                domains.add(domain_name)

        defs = re.findall(r"(?:def|class|function|const)\s+([A-Za-z0-9_]+)", code)
        if defs:
            summary = f"Defines {', '.join(defs[:4])} in {Path(file_path).name}."
        else:
            summary = f"Module {Path(file_path).name}."

        t_str = ", ".join(sorted(tables)) if tables else "none"
        r_str = ", ".join(sorted(routes)) if routes else "none"
        e_str = ", ".join(sorted(events)) if events else "none"
        d_str = ", ".join(sorted(domains)) if domains else "none"

        return (
            f"TABLES: {t_str}\n"
            f"ROUTES: {r_str}\n"
            f"EVENTS: {e_str}\n"
            f"DOMAINS: {d_str}\n"
            f"FLOW: {summary}"
        )


class BuiltinProvider(Provider):
    """llama-cpp-python running Qwen2.5-Coder GGUF, Metal-accelerated via n_gpu_layers=-1."""

    def __init__(self, model_path: str, n_ctx: int = 2048, n_gpu_layers: int = -1):
        self.model_path = Path(model_path)
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self._llm: Optional["Llama"] = None
        self._fallback = FastFallbackProvider()
        import atexit
        atexit.register(self.close)

    def close(self):
        """Release Metal GPU context cleanly before process exit."""
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

    def _ensure_loaded(self) -> bool:
        if self._llm is not None:
            return True
        if not _LLAMA_CPP_AVAILABLE or not self.model_path.exists():
            return False
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
            return False

    def generate(self, prompt: str, max_tokens: int = 250) -> str:
        if not self._ensure_loaded():
            return ""
        try:
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

    def sniff(self, file_path: str, code: str) -> str:
        if not self._ensure_loaded():
            return self._fallback.sniff(file_path, code)

        prompt = build_prompt(file_path, code)
        out = self.generate(prompt, max_tokens=220)
        return out if out else self._fallback.sniff(file_path, code)


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
        out = self.generate(prompt, max_tokens=220)
        return out if out else self._fallback.sniff(file_path, code)


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
                        "model": self.model or "claude-haiku-4-5-20251001",
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
                        "model": self.model or "gpt-6-luna",
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
            return self._fallback.sniff(file_path, code)

        prompt = build_prompt(file_path, code)
        out = self.generate(prompt, max_tokens=250)
        return out if out else self._fallback.sniff(file_path, code)


def build_provider(config: Config) -> Provider:
    kind = config.get("brain_provider", "builtin")
    if kind == "local_url":
        url = config.get("brain_local_url", "http://localhost:11434/api/generate")
        return LocalUrlProvider(url)
    elif kind == "cloud":
        return CloudProvider(
            vendor=config.get("brain_cloud_vendor", "openai"),
            api_key=config.get("brain_cloud_api_key", ""),
            model=config.get("brain_cloud_model", "gpt-4o-mini"),
        )
    else:
        model_path = config.get("model_path")
        return BuiltinProvider(model_path=model_path)
