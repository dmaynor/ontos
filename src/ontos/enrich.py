"""Optional LLM enrichment of draft definitions.

When an OpenAI-compatible endpoint is configured through environment
variables, ``ontos generate`` asks the model to write one-sentence
definitions for the draft terms. Enrichment is a *proposal* step only:
enriched terms are still drafts, still labeled (origin = 'llm'), and still
worthless for serving until a human certifies them.

Configuration (first set wins):
  ONTOS_LLM_BASE_URL / ONTOS_LLM_API_KEY / ONTOS_LLM_MODEL
  OPENAI_BASE_URL    / OPENAI_API_KEY    / OPENAI_MODEL

With nothing configured, generate falls back to deterministic
metadata-derived definitions (origin = 'template'). Generate must always
complete with no credentials - that fallback is the default path, and any
enrichment failure falls back per-term rather than failing the run.
"""

from __future__ import annotations

import json
import os
import urllib.request

from ontos.store import Term

TIMEOUT_SECONDS = 20


def llm_config(env: dict | None = None) -> dict | None:
    env = os.environ if env is None else env
    base = env.get("ONTOS_LLM_BASE_URL") or env.get("OPENAI_BASE_URL")
    key = env.get("ONTOS_LLM_API_KEY") or env.get("OPENAI_API_KEY")
    model = env.get("ONTOS_LLM_MODEL") or env.get("OPENAI_MODEL")
    if base and key and model:
        return {"base_url": base.rstrip("/"), "api_key": key, "model": model}
    return None


def _chat_completion(config: dict, prompt: str) -> str:
    body = json.dumps(
        {
            "model": config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write terse, factual, one-sentence ontology term "
                        "definitions. Reply with the definition only - no "
                        "preamble, no quotes."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{config['base_url']}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"].strip()


def enrich_definitions(terms: list[Term], config: dict, source_desc: str) -> int:
    """Enrich draft definitions in place. Returns how many terms changed.

    Never raises: a failed call leaves that term's template definition
    untouched.
    """
    changed = 0
    for term in terms:
        if term.state != "draft":
            continue
        prompt = (
            f"Source database: {source_desc}. Ontology term '{term.name}' "
            f"(kind: {term.kind}) maps to table '{term.source_table}'"
            + (f", column '{term.source_column}'" if term.source_column else "")
            + (f", related to term '{term.related_term}'" if term.related_term else "")
            + f". Current draft definition: {term.definition} "
            "Write a clearer one-sentence definition of what this term means "
            "in this dataset."
        )
        try:
            text = _chat_completion(config, prompt)
        except Exception:
            continue
        if text:
            term.definition = text
            term.origin = "llm"
            changed += 1
    return changed
