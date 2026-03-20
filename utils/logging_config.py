"""
Structured JSON logging configuration with sensitive data redaction.
"""

import json
import logging
import re
import sys
from datetime import datetime
from typing import Any, Dict

# Sensitive patterns to redact from logs
_SENSITIVE_PATTERNS = [
    # Ethereum private keys (64 hex chars)
    (re.compile(r'(0x)?[0-9a-fA-F]{64}'), '[REDACTED_KEY]'),
    # Bearer tokens
    (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE), 'Bearer [REDACTED]'),
    # API keys (sk-... pattern)
    (re.compile(r'(sk-[A-Za-z0-9]{20,})'), '[REDACTED_API_KEY]'),
    # Telegram bot tokens (numeric:alphanumeric)
    (re.compile(r'\d{8,}:[A-Za-z0-9_-]{30,}'), '[REDACTED_BOT_TOKEN]'),
    # Wallet addresses (0x + 40 hex chars)
    (re.compile(r'(0x[a-fA-F0-9]{40})'), '[REDACTED_WALLET]'),
    # Private key references
    (re.compile(r'private_key[=:]\s*[^\s,]+'), 'private_key=[REDACTED]'),
    # API key in URLs
    (re.compile(r'api[_-]?key[=:][^&\s]+'), 'api_key=[REDACTED]'),
    # Database connection strings
    (re.compile(r'postgres(ql)?://[^@]+@[^\s]+'), '[REDACTED_DB_URL]'),
    (re.compile(r'mysql://[^@]+@[^\s]+'), '[REDACTED_DB_URL]'),
    # AWS/GCP/Azure keys
    (re.compile(r'AKIA[0-9A-Z]{16}'), '[REDACTED_AWS_KEY]'),
    (re.compile(r'[0-9a-zA-Z/+]{40}'), '[REDACTED_SECRET]'),
]


def redact_sensitive_data(text: str) -> str:
    """Redact sensitive patterns from text."""
    if not isinstance(text, str):
        return text
    
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SecureJSONFormatter(logging.Formatter):
    """
    Formatta i record di log come JSON con redazione dati sensibili.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_object = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_data(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Aggiunge info eccezione se presente (redatta)
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            log_object["exception"] = redact_sensitive_data(exc_text)
        
        if record.stack_info:
            log_object["stack"] = redact_sensitive_data(record.stack_info)
        
        # Aggiunge campi extra dal record (redatti)
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info"
            ]:
                if isinstance(value, str):
                    log_object[key] = redact_sensitive_data(value)
                else:
                    log_object[key] = value
        
        return json.dumps(log_object, ensure_ascii=False, default=str)


def setup_logging(
    log_level: str = "INFO",
    json_format: bool = True,
    log_file: Optional[str] = None,
    console_output: bool = True
) -> None:
    """
    Configura il logging per l'applicazione con redazione dati sensibili.
    
    Args:
        log_level: Livello di logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Usa formattazione JSON (raccomandato per produzione)
        log_file: Percorso file log opzionale
        console_output: Se output su console
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Crea logger radice
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Rimuovi handler esistenti
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Crea formatter
    if json_format:
        formatter = SecureJSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    # Handler console
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # Handler file
    if log_file:
        import os
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Configura logger specifici
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("eth_account").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # Flask


def get_logger(name: str) -> logging.Logger:
    """
    Ottieni un logger con il nome dato.
    """
    return logging.getLogger(name)


# Funzione di utilità per log sicuri
def log_safe(logger: logging.Logger, level: str, message: str, **kwargs) -> None:
    """
    Log a message with automatic sensitive data redaction.
    
    Args:
        logger: Logger instance
        level: Log level ('debug', 'info', 'warning', 'error', 'critical')
        message: Message to log (will be redacted)
        **kwargs: Additional fields to include in log (will be redacted)
    """
    safe_kwargs = {k: redact_sensitive_data(str(v)) if isinstance(v, str) else v 
                   for k, v in kwargs.items()}
    
    log_method = getattr(logger, level.lower(), logger.info)
    
    if safe_kwargs:
        extra_msg = " ".join(f"{k}={v}" for k, v in safe_kwargs.items())
        log_method(f"{redact_sensitive_data(message)} [{extra_msg}]")
    else:
        log_method(redact_sensitive_data(message))