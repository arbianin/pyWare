import ctypes
import math

from . import config, engine, sdk

_user32 = ctypes.windll.user32
O = __import__("pyware.offsets", fromlist=["get"]).get

_invis_char = 0
_invis_parts: list = []
_invis_expires = 0.0
_invis_orig: dict = {}
_spin_a = 0.0


def _get_hum(mem):
    lp = sdk.localplayer
    if not mem.is_valid(lp):
        return 0, 0
    ch = sdk.get_character(mem, lp)
    if not mem.is_valid(ch):
        return 0, 0
    cmap = sdk.get_child_map(mem, ch)
    hum = cmap.get("Humanoid", 0)
    return (hum if mem.is_valid(hum) else 0), ch


def _apply_invis(mem, ch):
    import time
    global _invis_char, _invis_parts, _invis_expires
    if _invis_char != ch:
        _invis_orig.clear()
        _invis_parts = []
        _invis_char = ch
    now = time.monotonic()
    if now >= _invis_expires or not _invis_parts:
        _invis_parts = []
        for c in sdk.get_children(mem, ch):
            try:
                if sdk.get_class_name(mem, c) in ("Part", "MeshPart"):
                    _invis_parts.append(c)
            except Exception:
                pass
        _invis_expires = now + 5.0
    for p in _invis_parts:
        try:
            addr = p + O("BasePart.Transparency")
            if addr not in _invis_orig:
                _invis_orig[addr] = mem.f32(addr)
            mem.write_f32(addr, 1.0)
        except Exception:
            pass


def _clear_invis(mem):
    global _invis_char, _invis_parts
    for addr, orig in _invis_orig.items():
        try:
            mem.write_f32(addr, orig)
        except Exception:
            pass
    _invis_orig.clear()
    _invis_parts = []
    _invis_char = 0


def tick():
    global _spin_a
    mem = engine.mem
    if not mem.attached or not engine.resolved or config.SafeMode:
        return
    try:
        hum, ch = _get_hum(mem) if (config.SpeedEnabled or config.JumpEnabled or config.BhopEnabled or config.Invis or config.Fly or config.Spin) else (0, 0)
        if hum:
            if config.SpeedEnabled:
                mem.write_f32(hum + O("Humanoid.Walkspeed"), config.Speed)
                try:
                    mem.write_f32(hum + O("Humanoid.WalkspeedCheck"), config.Speed)
                except Exception:
                    pass
            if config.JumpEnabled:
                mem.write_f32(hum + O("Humanoid.JumpPower"), config.JumpPower)
                try:
                    mem.write_f32(hum + O("Humanoid.JumpHeight"), config.JumpPower / 7.2)
                except Exception:
                    pass
            if config.BhopEnabled:
                try:
                    mem.write(hum + O("Humanoid.Jump"), b"\x01")
                except Exception:
                    pass
        if config.Invis and mem.is_valid(ch):
            _apply_invis(mem, ch)
        elif _invis_orig:
            _clear_invis(mem)

        if config.Fly and mem.is_valid(ch):
            try:
                cmap = sdk.get_child_map(mem, ch)
                hrp = cmap.get("HumanoidRootPart", 0)
                prim = mem.u64(hrp + O("BasePart.Primitive")) if mem.is_valid(hrp) else 0
                if mem.is_valid(prim):
                    vx, _, vz = mem.vec3(prim + O("Primitive.AssemblyLinearVelocity"))
                    vy = 0.0
                    if _user32.GetAsyncKeyState(0x20) & 0x8000:
                        vy = config.FlySpeed
                    elif (_user32.GetAsyncKeyState(0x43) & 0x8000) or (_user32.GetAsyncKeyState(0xA2) & 0x8000):
                        vy = -config.FlySpeed
                    mem.write_vec3(prim + O("Primitive.AssemblyLinearVelocity"), (vx, vy, vz))
            except Exception:
                pass

        if config.Spin and mem.is_valid(ch):
            try:
                cmap = sdk.get_child_map(mem, ch)
                hrp = cmap.get("HumanoidRootPart", 0)
                prim = mem.u64(hrp + O("BasePart.Primitive")) if mem.is_valid(hrp) else 0
                if mem.is_valid(prim):
                    _spin_a += config.SpinSpeed * 0.016 * math.pi / 180.0
                    c, s = math.cos(_spin_a), math.sin(_spin_a)
                    rb = prim + O("Primitive.Rotation")
                    for off, val in ((0, c), (4, 0.0), (8, -s), (12, 0.0), (16, 1.0),
                                     (20, 0.0), (24, s), (28, 0.0), (32, c)):
                        mem.write_f32(rb + off, val)
            except Exception:
                pass

        if config.GravityEnabled and mem.is_valid(sdk.world):
            mem.write_f32(sdk.world + O("World.Gravity"), config.Gravity)
        if config.FovEnabled and mem.is_valid(sdk.camera):
            mem.write_f32(sdk.camera + O("Camera.FieldOfView"), config.CamFov)
    except Exception:
        pass
