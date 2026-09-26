"""All toggles + JSON save/load. Version-gated so stale configs never stick."""
import json
import os

APPDATA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "pyWare")
FILE = os.path.join(APPDATA, "config.json")
VERSION = 3

# ESP
EspEnabled = True
Boxes = True
CornerBox = False
ThreeDBox = False
Names = True
ShowTool = False
Health = True
HealthText = False
Distance = True
Snaplines = False
SnapOrigin = 0
Skeleton = False
HeadDot = False
Crosshair = True
XhairSize = 1.0
FadeDist = False
TeamColors = False
TeamCheck = True
EnableMaxDistance = False
MaxDistance = 1000.0

# Aim
AimEnabled = False
AimTarget = 0
AimMode = 0
AimFovPx = 150.0
AimSmooth = 4.0
AimMaxStep = 30.0
Prediction = False
AimLeadScale = 1.0
TargetLine = True
TriggerEnabled = False
TriggerRadius = 8.0
HitboxEnabled = False
HitboxSize = 4.0

# Mods
SpeedEnabled = False
Speed = 16.0
JumpEnabled = False
JumpPower = 50.0
BhopEnabled = False
Invis = False
Fly = False
FlySpeed = 50.0
Spin = False
SpinSpeed = 720.0
GravityEnabled = False
Gravity = 196.2
FovEnabled = False
CamFov = 70.0

# World
Fullbright = False
NoFog = False
ClockEnabled = False
ClockTime = 14.0
InfZoom = False

# Misc
SafeMode = False
BoxColor = 0
Accent = 0

_FIELDS = [k for k in list(globals()) if not k.startswith("_") and k not in ("json", "os", "APPDATA", "FILE", "VERSION")]


def _snapshot():
    import sys
    mod = sys.modules[__name__]
    return {k: getattr(mod, k) for k in _FIELDS}


def save():
    import sys
    mod = sys.modules[__name__]
    os.makedirs(APPDATA, exist_ok=True)
    data = _snapshot()
    data["ConfigVersion"] = VERSION
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return FILE


def load():
    import sys
    mod = sys.modules[__name__]
    with open(FILE, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("ConfigVersion", 0) != VERSION:
        return FILE  # stale: keep clean defaults
    for k, v in data.items():
        if k in _FIELDS and hasattr(mod, k):
            try:
                setattr(mod, k, v)
            except Exception:
                pass
    return FILE
