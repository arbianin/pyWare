"""Teleport via HRP primitive position writes (velocity zeroed)."""
import subprocess

from . import config, engine, sdk

O = __import__("pyware.offsets", fromlist=["get"]).get
last = ""
_saved = (0.0, 0.0, 0.0)
_has_saved = False


def _guard():
    global last
    if not engine.mem.attached:
        last = "not attached"
        return False
    if not engine.resolved:
        last = "blocked: pointers not validated"
        return False
    if config.SafeMode:
        last = "blocked: SAFE MODE on (SYS to disable)"
        return False
    return True


def to_coords(dest):
    global last
    if not _guard():
        return False
    try:
        mem = engine.mem
        lp = sdk.localplayer
        if not mem.is_valid(lp):
            last = "no local player"
            return False
        ch = sdk.get_character(mem, lp)
        cmap = sdk.get_child_map(mem, ch) if mem.is_valid(ch) else {}
        hrp = cmap.get("HumanoidRootPart", 0)
        prim = mem.u64(hrp + O("BasePart.Primitive")) if mem.is_valid(hrp) else 0
        if not mem.is_valid(prim):
            last = "no primitive"
            return False
        mem.write_vec3(prim + O("Primitive.Position"), dest)
        mem.write_vec3(prim + O("Primitive.AssemblyLinearVelocity"), (0, 0, 0))
        last = f"teleported to ({dest[0]:.0f},{dest[1]:.0f},{dest[2]:.0f})"
        return True
    except Exception as ex:
        last = str(ex)[:100]
        return False


def to_player(addr):
    global last
    if not _guard():
        return False
    try:
        mem = engine.mem
        ch = sdk.get_character(mem, addr)
        if not mem.is_valid(ch):
            last = "target has no character"
            return False
        cmap = sdk.get_child_map(mem, ch)
        hrp = cmap.get("HumanoidRootPart", 0)
        pos = sdk.get_part_position(mem, hrp) if mem.is_valid(hrp) else None
        if not pos:
            last = "target pos unreadable"
            return False
        return to_coords((pos[0], pos[1] + 3.0, pos[2]))
    except Exception as ex:
        last = str(ex)[:100]
        return False


def bring_player(addr):
    global last
    if not _guard():
        return False
    try:
        mem = engine.mem
        ch = sdk.get_character(mem, addr)
        if not mem.is_valid(ch):
            last = "target has no character"
            return False
        cmap = sdk.get_child_map(mem, ch)
        hrp = cmap.get("HumanoidRootPart", 0)
        prim = mem.u64(hrp + O("BasePart.Primitive")) if mem.is_valid(hrp) else 0
        if not mem.is_valid(prim):
            last = "target primitive null"
            return False
        lr = engine.local_root
        mem.write_vec3(prim + O("Primitive.Position"), (lr[0], lr[1] + 3.0, lr[2]))
        mem.write_vec3(prim + O("Primitive.AssemblyLinearVelocity"), (0, 0, 0))
        last = "brought player to you"
        return True
    except Exception as ex:
        last = str(ex)[:100]
        return False


def bring_all():
    global last
    if not _guard():
        return
    try:
        n = sum(1 for addr, _ in engine.roster() if bring_player(addr))
        last = f"brought {n} players" if n else "bring all: no targets"
    except Exception as ex:
        last = str(ex)[:100]


def save_slot():
    global _saved, _has_saved, last
    _saved = engine.local_root
    _has_saved = True
    last = f"slot saved ({_saved[0]:.0f},{_saved[1]:.0f},{_saved[2]:.0f})"


def load_slot():
    global last
    if not _has_saved:
        last = "slot empty — save first"
        return False
    return to_coords(_saved)


def copy_rejoin():
    global last
    try:
        place = engine.mem.u32(sdk.datamodel + O("DataModel.PlaceId")) if engine.mem.is_valid(sdk.datamodel) else 0
        job = engine.job_id
        if not place or not job:
            last = "need place + job id first"
            return
        script = f'game:GetService("TeleportService"):TeleportToPlaceInstance({place}, "{job}")'
        subprocess.run(["clip"], input=script.encode(), check=False)
        last = "rejoin script copied"
    except Exception as ex:
        last = str(ex)[:100]
