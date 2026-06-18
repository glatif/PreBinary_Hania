"""
Shared JSON parsing helper for LLM responses in the Narrated Slideshow feature.

Used by narration_generator.py and quiz_generator.py, which both ask the LLM
for a single JSON object back.
"""

import json
import re
from typing import Any, Dict, Optional


def _strip_fences(text: str) -> str:
    """Remove a leading/trailing markdown code fence (```json ... ```) if present."""
    stripped = text.strip()
    stripped = re.sub(r"^```[a-zA-Z]*\s*\n?", "", stripped)
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()


def repair_and_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract and parse the first JSON object out of raw LLM text, repairing
    truncated output where possible.

    Small local models (observed with llama3.2 via Ollama) sometimes emit
    their stop token one step early, ending the response right before the
    final closing brace - Ollama reports this as done_reason="stop", not a
    token-limit cutoff, so it isn't fixable by raising num_predict. A naive
    `text.find('{')` / `text.rfind('}')` extraction returns a string that
    will never parse in that case.

    This walks the text tracking bracket nesting (skipping over the contents
    of string literals) to find a balanced JSON object. If the text ends with
    brackets still open, it closes them in the correct order and retries -
    that fixes the common "stopped one token early" case while leaving
    genuinely malformed JSON to fail and be reported via raw_response.

    Returns the parsed dict, or None if no valid object could be recovered.
    """
    if not text:
        return None

    stripped = _strip_fences(text)
    start = stripped.find('{')
    if start < 0:
        return None
    candidate_text = stripped[start:]

    stack = []
    in_string = False
    escape = False
    end_index = None

    for i, ch in enumerate(candidate_text):
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in '{[':
            stack.append(ch)
        elif ch in '}]':
            if stack:
                stack.pop()
            if not stack:
                end_index = i
                break

    if end_index is not None:
        # Balanced object found - the common, well-formed case.
        try:
            return json.loads(candidate_text[:end_index + 1])
        except json.JSONDecodeError:
            return None

    # Reached end of text with brackets still open: the model stopped
    # generating before finishing the JSON. Close out whatever's left open
    # and retry once.
    repaired = candidate_text.rstrip()
    repaired = re.sub(r",\s*$", "", repaired)
    if in_string:
        repaired += '"'
    closers = {'{': '}', '[': ']'}
    repaired += ''.join(closers[ch] for ch in reversed(stack))

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None
