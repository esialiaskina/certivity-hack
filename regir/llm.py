"""Thin LLM wrapper: disk cache, retries, JSON parsing, thread pool. Reads ANTHROPIC_API_KEY from env or .env.
Model names via env: REGIR_BULK_MODEL (cheap, default claude-haiku-5-5), REGIR_STRONG_MODEL (default claude-sonnet-5-5)."""
from __future__ import annotations
import os, json, re, hashlib, time, pathlib
from concurrent.futures import ThreadPoolExecutor

BULK = os.getenv("REGIR_BULK_MODEL", "claude-haiku-5-5")
STRONG = os.getenv("REGIR_STRONG_MODEL", "claude-sonnet-5-5")
CACHE = pathlib.Path("data/llm_cache"); CACHE.mkdir(parents=True, exist_ok=True)


def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1); os.environ.setdefault(k, v.strip().strip('"').strip("'"))


_client = None
def client():
    global _client
    if _client is None:
        load_env(); import anthropic; _client = anthropic.Anthropic()
    return _client


def parse_json(text: str):
    """Extract the first JSON object/array from a model reply (tolerates ```json fences and chatter)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.M).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = t.find(opener), t.rfind(closer)
        if i != -1 and j > i:
            try: return json.loads(t[i:j + 1])
            except json.JSONDecodeError: pass
    raise ValueError("no JSON in reply: " + t[:120])


def call(system: str, user: str, model: str = BULK, max_tokens: int = 4000, temperature: float = 0.0, fake=None) -> str:
    """One cached call. `fake` (callable(system,user)->str) replaces the API in tests."""
    key = hashlib.sha256(json.dumps([model, system, user, max_tokens, temperature]).encode()).hexdigest()
    f = CACHE / f"{key}.txt"
    if f.exists(): return f.read_text()
    if fake is not None: out = fake(system, user)
    else:
        for attempt in range(5):
            try:
                r = client().messages.create(model=model, max_tokens=max_tokens, temperature=temperature,
                                             system=system, messages=[{"role": "user", "content": user}])
                out = "".join(b.text for b in r.content if getattr(b, "type", "") == "text"); break
            except Exception as e:  # rate limit / overload: back off
                if attempt == 4: raise
                time.sleep(2 ** attempt)
    f.write_text(out); return out


def call_json(system, user, **kw):
    return parse_json(call(system, user, **kw))


def pmap(fn, items, workers=8):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))
