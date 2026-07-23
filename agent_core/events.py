import json
import sys
from typing import Dict, Optional


def event(step: str, status: str, code: str, message: str, evidence: Optional[Dict[str, str]] = None) -> dict:
    return {
        "step": step,
        "status": status,
        "code": code,
        "message": message,
        "evidence": evidence or {},
    }


def emit(item: dict) -> None:
    sys.stdout.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    sys.stdout.flush()

