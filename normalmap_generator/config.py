import json
import os
import tempfile
from pathlib import Path

try:
    from platformdirs import user_config_dir
except Exception:
    user_config_dir = None

APP_NAME = "Normalmap_Generator_v3"

DEFAULTS = {
    "version": 1,
    "language": "ja",
    "last_input_path": "",
    "last_output_dir": "",
    "show_input_preview": False,
    "default_output_resolution": 2048,
    # Default processing parameters
    "default_radius": 15,
    "default_strength": 1.0,
    "overwrite_by_default": False,
    "window_geometry": "",
}


def _default_config_path():
    if user_config_dir:
        cfg_dir = Path(user_config_dir(APP_NAME, appauthor=False))
    else:
        # Fallback: use %APPDATA% on Windows, else use home/.config
        if os.name == "nt":
            base = os.getenv("APPDATA") or str(Path.home())
            cfg_dir = Path(base) / APP_NAME
        else:
            cfg_dir = Path.home() / ".config" / APP_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "config.json"


class Config:
    def __init__(self, path: Path = None):
        self.path = Path(path) if path else _default_config_path()
        self.data = DEFAULTS.copy()
        self.load()

    def load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                # Merge defaults: ensure all keys present
                merged = DEFAULTS.copy()
                merged.update(d)
                self.data = merged
        except Exception:
            # Backup broken file and reset to defaults
            try:
                bak = str(self.path) + ".bak"
                if self.path.exists():
                    os.replace(self.path, bak)
            except Exception:
                pass
            self.data = DEFAULTS.copy()

    def save(self):
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(self.path.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(self.path))
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, val):
        self.data[key] = val
        try:
            self.save()
        except Exception:
            # swallow save errors to avoid crashing the UI
            pass


__all__ = ["Config"]
