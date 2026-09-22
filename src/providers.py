"""Brain providers for PUG: Built-in (Metal Qwen), Local URL, Cloud BYOK, and Fast Fallback."""
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

logger = logging.getLogger("pug.providers")

try:
    from llama_cpp import Llama
    _LLAMA_CPP_AVAILABLE = True
except ImportError:
    _LLAMA_CPP_AVAILABLE = False

REQUEST_TIMEOUT = 15


class Provider:
    def sniff(self, file_path: str, code: str) -> str:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        raise NotImplementedError


class FastFallbackProvider(Provider):
    """Zero-dependency regex/heuristic scanner that extracts models, routes, and events
    in < 5ms. Used when no local LLM is loaded or while the model is downloading."""

    @property
    def available(self) -> bool:
        return True

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

    def sniff(self, file_path: str, code: str) -> str:
        if not self._ensure_loaded():
            return self._fallback.sniff(file_path, code)

        prompt = build_prompt(file_path, code)
        try:
            res = self._llm.create_chat_completion(
                messages=[
                    {"role": "user", "content": prompt},
                ],
                max_tokens=220,
                temperature=0.1,
            )
            return res["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("Inference error in BuiltinProvider: %s. Using fallback.", exc)
            return self._fallback.sniff(file_path, code)


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

    def sniff(self, file_path: str, code: str) -> str:
        prompt = build_prompt(file_path, code)
        try:
            if "api/generate" in self.url or ":11434" in self.url:
                # Ollama format
                url = self.url if "api/generate" in self.url else f"{self.url}/api/generate"
                r = requests.post(
                    url,
                    json={"model": "qwen2.5-coder:0.5b", "prompt": prompt, "stream": False},
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    return r.json().get("response", "").strip()
            else:
                # OpenAI-compatible /v1/chat/completions format
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
            logger.warning("LocalUrlProvider error: %s", exc)

        return self._fallback.sniff(file_path, code)


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

    def sniff(self, file_path: str, code: str) -> str:
        if not self.available:
            return self._fallback.sniff(file_path, code)

        prompt = build_prompt(file_path, code)
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
                        "model": self.model or "claude-3-5-haiku-20241022",
                        "max_tokens": 250,
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
                        "model": self.model or "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("CloudProvider error: %s", exc)

        return self._fallback.sniff(file_path, code)


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
