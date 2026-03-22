import re

SENSITIVE_REPLACEMENTS = [
    (re.compile(r'(?i)\b(?:private[_-]?key|secret|mnemonic)\s*[:=]\s*["\']?[^"\',\s]+["\']?'), '[REDACTED_SECRET_FIELD]'),
    (re.compile(r'\b0x[a-fA-F0-9]{64}\b'), '[REDACTED_PRIVATE_KEY]'),
    (re.compile(r'(?<![A-Za-z0-9])(?:[a-fA-F0-9]{64})(?![A-Za-z0-9])'), '[REDACTED_HEX_SECRET]'),
    (re.compile(r'\b0x[a-fA-F0-9]{40}\b'), '[REDACTED_WALLET]'),
    (re.compile(r'\bsk-or-[A-Za-z0-9_-]{16,}\b'), '[REDACTED_OPENROUTER_KEY]'),
    (re.compile(r'(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*'), 'Bearer [REDACTED_TOKEN]'),
    (re.compile(r'\b\d{8,}:[A-Za-z0-9_-]{20,}\b'), '[REDACTED_BOT_TOKEN]'),
    (re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'), '[REDACTED_ACCESS_KEY]'),
    (re.compile(r'\b[a-zA-Z0-9_]{6,}\.\.\.[a-zA-Z0-9_]{3,}\b'), '[REDACTED_PARTIAL_SECRET]'),
    (re.compile(r'"(private_key|api_key|wallet|token|secret)"\s*:\s*"[^"]*"', re.IGNORECASE), r'"\1":"[REDACTED]"'),
]


def sanitize_log_message(message: str) -> str:
    if not isinstance(message, str):
        message = str(message)

    sanitized = message
    for pattern, replacement in SENSITIVE_REPLACEMENTS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized