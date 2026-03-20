import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """
    Formatta i record di log come JSON per logging strutturato.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_object = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Aggiunge info eccezione se presente
        if record.exc_info:
            log_object["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_object["stack"] = record.stack_info
        
        # Aggiunge campi extra dal record
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info"
            ]:
                log_object[key] = value
        
        return json.dumps(log_object, ensure_ascii=False, default=str)


def setup_logging(
    log_level: str = "INFO",
    json_format: bool = True,
    log_file: Optional[str] = None,
    console_output: bool = True
) -> None:
    """
    Configura il logging per l'applicazione.
    
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
        formatter = JSONFormatter()
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


def get_logger(name: str) -> logging.Logger:
    """
    Ottieni un logger con il nome dato.
    """
    return logging.getLogger(name)