import json
import os
from typing import Dict, Any

class HealingReport:
    def __init__(self):
        self.events = []
        self.summary = {
            "total": 0,
            "primary": 0,
            "healed": 0,
            "failed": 0
        }
        
    def record_event(
        self,
        key: str,
        action: str,
        status: str,
        used_candidate: dict = None,
        message: str = "",
        details: dict | None = None,
    ):
        event = {
            "key": key,
            "action": action,
            "status": status,
            "used_candidate": used_candidate,
            "message": message,
        }
        if details:
            event["details"] = details
        self.events.append(event)
        self.summary["total"] += 1
        if status in self.summary:
            self.summary[status] += 1
            
    def save(self, filepath: str):
        data = {
            "events": self.events,
            "summary": self.summary
        }
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
