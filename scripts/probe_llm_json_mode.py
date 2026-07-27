import json
import pathlib
import sys
import time
import types

from openai import OpenAI


ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

app_mod = types.ModuleType("app")
app_mod.__path__ = [str(BACKEND_ROOT / "app")]
sys.modules.setdefault("app", app_mod)

from app.services.model import ModelService  # noqa: E402
from app.services.provider import ProviderService  # noqa: E402


def run_probe(provider_id: str = "freemodel", model: str = "gpt-5.5") -> list[dict]:
    provider = ProviderService.get_provider_by_id(provider_id)
    results = []
    if not provider:
        return [{"case": "setup", "ok": False, "error": "provider not found"}]

    client = OpenAI(
        api_key=ModelService._resolve_api_key(provider),
        base_url=provider["base_url"],
        timeout=35.0,
    )
    cases = [
        {
            "case": "plain_text",
            "kwargs": {},
            "messages": [{"role": "user", "content": "Answer in one short sentence: 1+1=?"}],
        },
        {
            "case": "json_mode_minimal",
            "kwargs": {"response_format": {"type": "json_object"}},
            "messages": [
                {"role": "system", "content": "Return only a JSON object."},
                {"role": "user", "content": 'Return {"ok": true, "answer": 2}.'},
            ],
        },
        {
            "case": "prompt_json_no_json_mode",
            "kwargs": {},
            "messages": [
                {"role": "system", "content": "Return only a JSON object. No prose. No markdown."},
                {"role": "user", "content": 'Return {"ok": true, "answer": 2}.'},
            ],
        },
    ]

    for item in cases:
        started = time.time()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=item["messages"],
                temperature=0.2,
                max_tokens=128,
                **item["kwargs"],
            )
            content = response.choices[0].message.content or ""
            try:
                json.loads(content)
                json_parse_ok = True
                json_parse_error = ""
            except Exception as exc:
                json_parse_ok = False
                json_parse_error = str(exc)
            results.append(
                {
                    "case": item["case"],
                    "ok": True,
                    "seconds": round(time.time() - started, 2),
                    "content": content[:500],
                    "json_parse_ok": json_parse_ok,
                    "json_parse_error": json_parse_error,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "case": item["case"],
                    "ok": False,
                    "seconds": round(time.time() - started, 2),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                    "status_code": getattr(exc, "status_code", None),
                }
            )

    return results


if __name__ == "__main__":
    print(json.dumps(run_probe(), ensure_ascii=False, indent=2))
