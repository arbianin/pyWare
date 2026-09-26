from .offsets_snapshot import VERSION as COMPILED_VERSION, COMPILED

IMTHEO_URL = "https://offsets.imtheo.lol/offsets.json"

RUNTIME = dict(COMPILED)

local_version = "unknown"
live_version = "unknown"
live_dumped_at = ""
live_ok = False
live_table: dict[str, int] = {}
last_message = "not checked"
effective_source = "compiled"


def get(path, default=0):
    return RUNTIME.get(path, default)


def apply(table):
    for k, v in table.items():
        if k in RUNTIME:
            try:
                RUNTIME[k] = int(v)
            except Exception:
                pass


def reset_to_compiled():
    RUNTIME.clear()
    RUNTIME.update(COMPILED)


def detect_local_version(proc):
    """Roblox client version = parent folder of the exe (version-xxxxxxxx)."""
    global local_version
    try:
        import os
        path = proc.exe()
        folder = os.path.basename(os.path.dirname(path))
        local_version = folder if folder.startswith("version-") else "unknown"
    except Exception:
        local_version = "unknown (access denied? run as admin)"
    return local_version


def _parse_value(el):
    try:
        if isinstance(el, bool):
            return None
        if isinstance(el, int):
            return el
        if isinstance(el, float):
            return int(el)
        s = str(el).strip()
        if s.lower().startswith("0x"):
            return int(s[2:], 16)
        return int(s)
    except Exception:
        return None


def fetch_live():
    """Download imtheo offsets.json (exact RbxDumperV2 schema). Fails soft."""
    global live_version, live_dumped_at, live_ok, live_table, last_message
    try:
        import requests
        r = requests.get(IMTHEO_URL, timeout=12)
        j = r.json()
        live_version = j.get("Roblox Version", "unknown")
        live_dumped_at = j.get("Dumped At", "")
        table: dict[str, int] = {}
        offs = j.get("Offsets", {})
        for cls, props in offs.items():
            if not isinstance(props, dict):
                continue
            for name, val in props.items():
                v = _parse_value(val)
                if v is not None:
                    table[f"{cls}.{name}"] = v
        f = table.get("FakeDataModel.Pointer", 0)
        e = table.get("VisualEngine.Pointer", 0)
        if f and f > 0x100000 and e and e > 0x100000:
            live_table = table
            live_ok = True
            last_message = f"live {live_version} ({len(table)} offsets)"
        else:
            live_ok = False
            last_message = "live JSON missing critical keys"
    except Exception as ex:
        live_ok = False
        last_message = "live fetch failed: " + str(ex)[:120]
    return live_ok
