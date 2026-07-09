"""
Logging module for Google Photos Takeout Fixer.
Generates human-readable .log and machine-parseable .jsonl files.
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import threading
import sys

class ProcessingLogger:
    
    def __init__(self, log_dir: Path, run_id: str = None, anonymous: bool = False):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.anonymous = anonymous
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.run_id = run_id or timestamp
        self.log_file = self.log_dir / f"{self.run_id}_Processing.log"
        self.jsonl_file = self.log_dir / f"{self.run_id}_Processing.jsonl"
        
        self._lock = threading.Lock()
        
        # Use run_id as logger name to prevent handler accumulation across runs
        logger_name = f"TakeoutFixer_{self.run_id}"
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.DEBUG)
        
        # File handler for human-readable log
        fh = logging.FileHandler(self.log_file, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('[%(asctime)s] %(levelname)-8s %(message)s', 
                                      datefmt='%Y-%m-%d %H:%M:%S')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        
        # Console handler only if stderr exists (not in --windowed mode)
        if sys.stderr is not None:
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

    def log(self, level: str, message: str, file_info: Optional[dict] = None):
        """Thread-safe logging method."""
        with self._lock:
            original_file_info = file_info
            file_info = self._redact_file_info(file_info)
            message = self._redact_message(message, original_file_info)

            # Human-readable
            if level == "SUCCESS":
                self.logger.info(message)
            elif level == "REVIEW":
                self.logger.warning(message)
            elif level == "AUDIT":
                self.logger.info(message)
            else:
                self.logger.log(getattr(logging, level, logging.INFO), message)
            
            # Machine-parseable JSONL
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "message": message
            }
            if file_info:
                log_entry["file"] = file_info
                
            with open(self.jsonl_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')

    def _redact_file_info(self, file_info: Optional[dict]) -> Optional[dict]:
        if not self.anonymous or not file_info:
            return file_info

        redacted = dict(file_info)
        for key in ("filename", "path", "json_path"):
            if key in redacted and redacted[key]:
                redacted[key] = "<redacted>"
        return redacted

    def _redact_message(self, message: str, file_info: Optional[dict]) -> str:
        if not self.anonymous or not file_info:
            return message

        original_name = file_info.get("filename")
        if original_name and original_name != "<redacted>":
            return message.replace(original_name, "<redacted>")
        return message

    def audit_reconciliation(self, scanned: int, completed: int, unmatched: int, errors: int, low_confidence: int = 0):
        """Logs the final reconciliation check."""
        total_processed = completed + unmatched + errors + low_confidence
        counts_status = "PASS" if scanned == total_processed else "FAIL"
        error_rate = (errors / scanned * 100) if scanned else 0

        if error_rate >= 50:
            health = "CRITICAL"
        elif error_rate >= 5:
            health = "DEGRADED"
        else:
            health = "HEALTHY"

        msg = (
            f"Reconciliation: {scanned} scanned == {completed} completed + "
            f"{unmatched} unmatched + {errors} errors + {low_confidence} low_confidence. "
            f"[Counts: {counts_status}] [Health: {health}, {error_rate:.1f}% error rate]"
        )
        self.log("AUDIT" if health == "HEALTHY" else "ERROR", msg)
    
    def cleanup(self):
        """Remove all handlers to prevent accumulation."""
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
