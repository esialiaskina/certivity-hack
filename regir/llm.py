"""Thin LLM wrapper: disk cache, retries, JSON parsing, thread pool. Reads ANTHROPIC_API_KEY from env or .env.
Model names via env: REGIR_BULK_MODEL (cheap, default claude-haiku-5-5), REGIR_STRONG_MODEL (default claude-sonnet-5-5)."""
from __future__ import annotations
import os, json, re, hashlib, time, pathlib
from concurrent.futures import ThreadPoolExecutor

BULK = os.getenv("REGIR_BULK_MODEL", "claude-haiku-5-5")
STRONG = os.getenv("REGIR_STRONG_MODEL", "claude-sonnet-5-5")
CACHE = pathlib.Path("data/llm_cache"); CACHE.mkdir(parents=True, exist_ok=True)


def load_env(path=".env"):
    """.env wins over the ambient shell. An ambient ANTHROPIC_AUTH_TOKEN would make the SDK send a Bearer token
    and ignore the API key, so it is dropped when .env provides ANTHROPIC_API_KEY."""
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); os.environ[k.strip()] = v.strip().strip('"').strip("'")
        if os.environ.get("ANTHROPIC_API_KEY"):
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)


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


def call(system: str, user: str, model: str = BULK, max_tokens: int = 4000, temperature: float = 0.0,
         fake=None, refresh: bool = False) -> str:
    """One cached call. `fake` (callable(system,user)->str) replaces the API in tests."""
    key = hashlib.sha256(json.dumps([model, system, user, max_tokens, temperature]).encode()).hexdigest()
    f = CACHE / f"{key}.txt"
    if f.exists() and not refresh: return f.read_text()
    if fake is not None: out = fake(system, user)
    else:
        for attempt in range(5):
            try:
                r = client().messages.create(model=model, max_tokens=max_tokens,
                                             system=system, messages=[{"role": "user", "content": user}])
                out = "".join(b.text for b in r.content if getattr(b, "type", "") == "text"); break
            except Exception as e:  # rate limit / overload: back off
                if attempt == 4: raise
                time.sleep(2 ** attempt)
    f.write_text(out); return out


def call_json(system, user, **kw):
    try:
        return parse_json(call(system, user, **kw))
    except ValueError:
        # A truncated/malformed cached response must not poison every future run.
        # Retry the same structured request once without reusing its cache entry.
        return parse_json(call(system, user, refresh=True, **kw))


def pmap(fn, items, workers=8):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))


def diagnose():
    load_env()
    print("env names set (values hidden):", sorted(k for k in os.environ if "ANTHROPIC" in k.upper()))
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    print("api key: length", len(k), "| starts with", (k[:3] + "...") if k else "(none)", "| has whitespace:", any(c.isspace() for c in k))
    print("base url:", os.environ.get("ANTHROPIC_BASE_URL", "(default api.anthropic.com)"))


if __name__ == "__main__":
    diagnose()
    # smoke test: one real call per model, prints the reply or the exact error
    for m in (BULK, STRONG):
        try:
            r = client().messages.create(model=m, max_tokens=30, messages=[{"role": "user", "content": "Reply with the single word: ok"}])
            print(m, "->", "".join(b.text for b in r.content if getattr(b, "type", "") == "text"))
        except Exception as e:
            print(m, "-> ERROR", type(e).__name__, str(e)[:400])
