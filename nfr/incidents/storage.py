"""Persist incidents to disk + daily index."""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from nfr.constants import STORAGE_ROOT
from nfr.incidents.models import Incident, IncidentStatus

INCIDENTS_DIR = STORAGE_ROOT / "incidents"
INDEX_FILE = STORAGE_ROOT / "incidents" / "index.json"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def save_incident(inc: Incident) -> Path:
    """Save incident to {date}/{inc-id}.json."""
    date_str = inc.start_ts.strftime("%Y-%m-%d")
    out_dir = INCIDENTS_DIR / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (inc.id + ".json")
    _atomic_write(out_path, json.dumps(inc.to_dict(), indent=2, sort_keys=True, default=str))
    _update_index()
    return out_path


def _update_index() -> None:
    """Rebuild quick index of incidents per day."""
    if not INCIDENTS_DIR.exists():
        return
    idx: Dict[str, dict] = {}
    for date_dir in sorted(INCIDENTS_DIR.iterdir()):
        if not date_dir.is_dir() or date_dir.name == "index.json.tmp":
            continue
        date_str = date_dir.name
        day_incidents = []
        for f in date_dir.glob("inc-*.json"):
            try:
                d = json.loads(f.read_text())
                day_incidents.append({
                    "id": d["id"],
                    "severity": d["severity"],
                    "status": d["status"],
                    "start": d["start_ts"],
                    "end": d.get("end_ts"),
                    "layers": d.get("layers_affected", []),
                })
            except Exception:
                continue
        if day_incidents:
            critical = sum(1 for i in day_incidents if i["severity"] == "critical")
            warning = sum(1 for i in day_incidents if i["severity"] == "warning")
            notice = sum(1 for i in day_incidents if i["severity"] == "notice")
            idx[date_str] = {
                "total": len(day_incidents),
                "critical": critical,
                "warning": warning,
                "notice": notice,
                "open": sum(1 for i in day_incidents if i["status"] == "open"),
                "closed": sum(1 for i in day_incidents if i["status"] == "closed"),
            }
    _atomic_write(INDEX_FILE, json.dumps(idx, indent=2, sort_keys=True))


def get_index() -> dict:
    if not INDEX_FILE.exists():
        return {}
    try:
        return json.loads(INDEX_FILE.read_text())
    except Exception:
        return {}


def load_incidents_for_date(date_str: str) -> List[Incident]:
    """Load all incidents for a given date."""
    out_dir = INCIDENTS_DIR / date_str
    if not out_dir.exists():
        return []
    out = []
    for f in sorted(out_dir.glob("inc-*.json")):
        try:
            d = json.loads(f.read_text())
            out.append(Incident.from_dict(d))
        except Exception:
            continue
    return out


def load_active_incidents() -> List[Incident]:
    """Load currently-open incidents."""
    if not INCIDENTS_DIR.exists():
        return []
    out = []
    for date_dir in INCIDENTS_DIR.iterdir():
        if not date_dir.is_dir():
            continue
        for f in date_dir.glob("inc-*.json"):
            try:
                d = json.loads(f.read_text())
                if d.get("status") == IncidentStatus.OPEN.value:
                    out.append(Incident.from_dict(d))
            except Exception:
                continue
    return out


def load_incident(incident_id: str) -> Optional[Incident]:
    """Load a specific incident by id."""
    if not INCIDENTS_DIR.exists():
        return None
    for date_dir in INCIDENTS_DIR.iterdir():
        f = date_dir / (incident_id + ".json")
        if f.exists():
            try:
                return Incident.from_dict(json.loads(f.read_text()))
            except Exception:
                return None
    return None
