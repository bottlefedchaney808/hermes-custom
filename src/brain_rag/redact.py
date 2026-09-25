"""Scrub secrets out of session text before it becomes a vault note.

Transcripts carry whatever was pasted into a chat. Once swept they are
committed, pushed and indexed, so redaction happens at write time — the one
place that is too late to skip. Deliberately conservative: a card number must
pass Luhn, so order numbers and SF totals survive.
"""
from __future__ import annotations

import re

MASK = "[redacted]"

_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_PATTERNS = [
    re.compile(r"\bsk-(?:ant-|or-|proj-)?[A-Za-z0-9_-]{16,}"),          # Anthropic/OpenAI/OpenRouter
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),                            # Google API key
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),                        # GitHub tokens
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),                      # Slack tokens
    re.compile(r"\bya29\.[0-9A-Za-z_-]{20,}"),                          # Google OAuth access token
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b[A-Fa-f0-9]{40,}\b"),                                # long hex secrets
]
_ASSIGN = re.compile(
    r"(?i)\b((?:api[_-]?key|secret|token|password|passwd|pwd|client[_-]?secret|cvv|cvc)"
    r"\s*[:=]\s*)(\"[^\"]+\"|'[^']+'|\S+)"
)


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def _card(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return MASK if 13 <= len(digits) <= 19 and _luhn(digits) else match.group(0)


# A line that TALKS about a key/token is where a pasted credential lives, in
# whatever shape (Kalshi key ids are bare UUIDs). On such lines, mask anything
# credential-shaped: UUIDs and long mixed letter+digit runs.
_CRED_CONTEXT = re.compile(r"(?i)\b(api[\s_-]?key|key\s*id|access[\s_-]?key|keys?|token|secret|password|credential)s?\b")
_CRED_SHAPED = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    r"|\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{24,}\b"
)


def _context_line(line: str) -> str:
    return _CRED_SHAPED.sub(MASK, line) if _CRED_CONTEXT.search(line) else line


def redact(text: str) -> str:
    if not text:
        return text
    out = _CARD.sub(_card, text)
    for pattern in _PATTERNS:
        out = pattern.sub(MASK, out)
    out = _ASSIGN.sub(lambda m: m.group(1) + MASK, out)
    return "\n".join(_context_line(line) for line in out.split("\n"))
