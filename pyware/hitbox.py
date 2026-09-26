"""Enemy head hitbox expander with restore on disable."""
from . import config, engine

O = __import__("pyware.offsets", fromlist=["get"]).get

_orig: dict = {}


def tick():
    mem = engine.mem
    if not mem.attached or not engine.resolved or config.SafeMode:
        return
    try:
        if not config.HitboxEnabled:
            if _orig:
                for addr, v in _orig.items():
                    try:
                        mem.write_vec3(addr, v)
                    except Exception:
                        pass
                _orig.clear()
            return
        s = max(1.0, min(10.0, config.HitboxSize))
        for e in engine.snapshot():
            if not mem.is_valid(e.head_addr):
                continue
            try:
                prim = mem.u64(e.head_addr + O("BasePart.Primitive"))
                if not mem.is_valid(prim):
                    continue
                addr = prim + O("Primitive.Size")
                if addr not in _orig:
                    _orig[addr] = mem.vec3(addr)
                mem.write_vec3(addr, (s, s, s))
            except Exception:
                pass
    except Exception:
        pass
