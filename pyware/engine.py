"""80Hz entity cache, validation-gated offset-table attempts, diagnostics."""
import math
import threading
import time
from datetime import datetime

from . import config, offsets as O, sdk
from .memory import Memory

BONES_R15 = [
    ("Head", "UpperTorso"), ("UpperTorso", "LowerTorso"),
    ("UpperTorso", "LeftUpperArm"), ("LeftUpperArm", "LeftLowerArm"), ("LeftLowerArm", "LeftHand"),
    ("UpperTorso", "RightUpperArm"), ("RightUpperArm", "RightLowerArm"), ("RightLowerArm", "RightHand"),
    ("LowerTorso", "LeftUpperLeg"), ("LeftUpperLeg", "LeftLowerLeg"), ("LeftLowerLeg", "LeftFoot"),
    ("LowerTorso", "RightUpperLeg"), ("RightUpperLeg", "RightLowerLeg"), ("RightLowerLeg", "RightFoot"),
]
BONES_R6 = [
    ("Head", "Torso"), ("Torso", "Left Arm"), ("Torso", "Right Arm"),
    ("Torso", "Left Leg"), ("Torso", "Right Leg"),
]


class EspEntry:
    __slots__ = ("addr", "head_addr", "name", "team", "hp", "maxhp", "dist",
                 "root3", "head3", "vel", "root2", "head2", "root_vis", "head_vis",
                 "onscreen", "pairs", "joints", "tool")


mem = Memory()
status = "not attached"
running = False
resolved = False

_lock = threading.Lock()
_snapshot: list = []
_roster: list = []
_diag: list = []
_diag_lock = threading.Lock()

viewmatrix = [0.0] * 16
screen_w, screen_h = 1920, 1080
window_w, window_h = 0, 0
camera_pos = (0.0, 0.0, 0.0)
local_team = 0
local_root = (0.0, 0.0, 0.0)
local_ws_now = -1.0
local_ws_want = -1.0
lighting_addr = 0
place_info = ""
job_id = ""

_last_resolve = 0.0
_light_retry = 0.0
_job_t = 0.0
_players_cache: list = []
_players_expires = 0.0
_tool_cache: dict = {}


def log(s):
    global status
    status = s
    try:
        print(f"[{datetime.now():%H:%M:%S}] {s}", flush=True)
    except Exception:
        pass


def diag():
    with _diag_lock:
        return list(_diag)


def snapshot():
    with _lock:
        return list(_snapshot)


def roster():
    with _lock:
        return list(_roster)


def attach(proc="RobloxPlayerBeta"):
    ok = mem.attach(proc)
    if not ok:
        names = ""
        try:
            import psutil
            seen = sorted({(p.info["name"] or "") for p in psutil.process_iter(["name"])})
            names = ",".join(n for n in seen if "roblox" in n.lower())
        except Exception:
            pass
        log("RobloxPlayerBeta not found" + (f"; running: {names}" if names else " (start the game first)"))
        return False
    try:
        import psutil
        O.detect_local_version(psutil.Process(mem.pid))
    except Exception:
        pass
    log(f"attached PID {mem.pid} base {hex(mem.base)} local {O.local_version}")

    def _bg():
        O.fetch_live()
        log(O.last_message)
        resolve(True)

    threading.Thread(target=_bg, daemon=True).start()
    resolve(True)
    return True


def refetch_and_resolve():
    def _bg():
        O.fetch_live()
        log(O.last_message)
        global resolved
        resolved = False
        resolve(True)

    threading.Thread(target=_bg, daemon=True).start()


def resolve(force=False):
    """Try compiled then live tables; keep the first that VALIDATES."""
    global _last_resolve, resolved
    now = time.monotonic()
    if not force and now - _last_resolve < 5.0 and resolved and mem.is_valid(sdk.datamodel):
        return True
    _last_resolve = now
    cands = [(f"compiled {O.COMPILED_VERSION}", dict(__import__("pyware.offsets_snapshot", fromlist=["COMPILED"]).COMPILED))]
    if O.live_ok and len(O.live_table) > 30:
        cands.append((f"live {O.live_version}", O.live_table))
    for name, table in cands:
        O.apply(table)
        if sdk.resolve_all(mem):
            resolved = True
            O.effective_source = name
            with _diag_lock:
                _diag[:] = sdk.lastlines
            log(f"RESOLVED with {name} | dm {hex(sdk.datamodel)}")
            return True
        log(f"attempt [{name}] failed: {sdk.lasterror}")
    resolved = False
    O.reset_to_compiled()
    O.effective_source = "none (all attempts failed)"
    with _diag_lock:
        _diag[:] = sdk.lastlines
    log("RESOLVE FAILED — see SYS diag. Likely version mismatch: update offsets.")
    return False


def start():
    global running
    if running:
        return
    running = True
    threading.Thread(target=_loop, daemon=True, name="pyWareEngine").start()


def stop():
    global running
    running = False


def w2s(world, sw, sh):
    m = viewmatrix
    if len(m) < 16 or sw <= 0 or sh <= 0:
        return None
    x = m[0] * world[0] + m[1] * world[1] + m[2] * world[2] + m[3]
    y = m[4] * world[0] + m[5] * world[1] + m[6] * world[2] + m[7]
    w = m[12] * world[0] + m[13] * world[1] + m[14] * world[2] + m[15]
    for v in (x, y, w):
        if not math.isfinite(v):
            return None
    if w <= 0.1:
        return None
    nx, ny = x / w, y / w
    if not (math.isfinite(nx) and math.isfinite(ny)):
        return None
    return (sw / 2 * (1 + nx), sh / 2 * (1 - ny))


def _loop():
    import random
    while running:
        try:
            if not mem.attached:
                log("waiting for RobloxPlayerBeta.exe...")
                _snapshot.clear()
                time.sleep(1.0)
                continue
            resolve()
            if not resolved:
                time.sleep(1.0)
                continue
            tick()
        except Exception:
            pass
        time.sleep(0.012 + random.uniform(-0.003, 0.003))


def _get_tool(ch):
    now = time.monotonic()
    e = _tool_cache.get(ch)
    if e and now < e[1]:
        return e[0]
    name = ""
    try:
        t = sdk.find_first_child_of_class(mem, ch, "Tool")
        if mem.is_valid(t):
            name = sdk.get_name(mem, t)
    except Exception:
        pass
    if len(_tool_cache) > 256:
        _tool_cache.clear()
    _tool_cache[ch] = (name, now + 3.0)
    return name


def _build_skeleton(ch):
    parts = sdk.get_bone_parts(mem, ch)
    pairs = list(BONES_R15 if "UpperTorso" in parts else BONES_R6)
    need = set()
    for a, b in pairs:
        need.add(a)
        need.add(b)
    joints = {}
    for name in need:
        a = parts.get(name, 0)
        if not mem.is_valid(a):
            continue
        w = sdk.get_part_position(mem, a)
        if w and all(math.isfinite(v) for v in w):
            joints[name] = w
    pairs = [(a, b) for a, b in pairs if a in joints and b in joints]
    return pairs, joints


def tick():
    global screen_w, screen_h, camera_pos, local_team, local_root
    global local_ws_now, local_ws_want, lighting_addr, place_info, job_id
    global _players_cache, _players_expires, _light_retry, _job_t

    try:
        if mem.is_valid(sdk.camera):
            vs = mem.vec2(sdk.camera + O.get("Camera.ViewportSize"))
            if 100 < vs[0] < 8000 and 100 < vs[1]:
                screen_w, screen_h = int(vs[0]), int(vs[1])
        if mem.is_valid(sdk.visualengine):
            viewmatrix[:] = mem.mat16(sdk.visualengine + O.get("VisualEngine.ViewMatrix"))
            if screen_w < 100:
                d = mem.vec2(sdk.visualengine + O.get("VisualEngine.Dimensions"))
                if d[0] > 100 and d[1] > 100:
                    screen_w, screen_h = int(d[0]), int(d[1])
        if screen_w < 100:
            if window_w > 100:
                screen_w, screen_h = window_w, window_h
            else:
                screen_w, screen_h = 1920, 1080
        if mem.is_valid(sdk.camera):
            camera_pos = mem.vec3(sdk.camera + O.get("Camera.Position"))
    except Exception:
        pass

    try:
        if mem.is_valid(sdk.datamodel) and not place_info:
            place_info = f"PlaceId {mem.u32(sdk.datamodel + O.get('DataModel.PlaceId'))} | {O.COMPILED_VERSION}"
        now_j = time.monotonic()
        if mem.is_valid(sdk.datamodel) and now_j - _job_t > 5.0:
            _job_t = now_j
            try:
                j = mem.rbx_string(sdk.datamodel + O.get("DataModel.JobId"))
                if not j:
                    jp = mem.u64(sdk.datamodel + O.get("DataModel.JobId"))
                    if mem.is_valid(jp):
                        j = mem.rbx_string(jp)
                if j and j != "Unknown":
                    job_id = j
            except Exception:
                pass
    except Exception:
        pass

    local_team = 0
    local_root = (0.0, 0.0, 0.0)
    local_ws_now, local_ws_want = -1.0, -1.0
    try:
        now0 = time.monotonic()
        if not mem.is_valid(lighting_addr) and now0 - _light_retry > 2.0:
            _light_retry = now0
            lighting_addr = sdk.find_first_child_of_class(mem, sdk.datamodel, "Lighting")
    except Exception:
        pass
    try:
        if mem.is_valid(sdk.localplayer):
            local_team = mem.u64(sdk.localplayer + O.get("Player.Team"))
            ch = sdk.get_character(mem, sdk.localplayer)
            if mem.is_valid(ch):
                cmap = sdk.get_child_map(mem, ch)
                hrp = sdk.pick_hrp(cmap, 0, mem)
                if mem.is_valid(hrp):
                    p = sdk.get_part_position(mem, hrp)
                    if p:
                        local_root = p
                hum = cmap.get("Humanoid", 0)
                if mem.is_valid(hum):
                    try:
                        local_ws_now = mem.f32(hum + O.get("Humanoid.Walkspeed"))
                    except Exception:
                        pass
                    local_ws_want = config.Speed if config.SpeedEnabled else -1.0
    except Exception:
        pass

    out, rost = [], []
    try:
        if not mem.is_valid(sdk.players):
            resolve()
            return
        now = time.monotonic()
        if now >= _players_expires or not _players_cache:
            _players_cache = sdk.find_all_of_class(mem, sdk.players, "Player")
            _players_expires = now + 2.0
        for plr in _players_cache:
            pname = sdk.get_player_name(mem, plr)
            if plr != sdk.localplayer:
                rost.append((plr, pname))
            if plr == sdk.localplayer:
                continue
            team = mem.u64(plr + O.get("Player.Team"))
            if config.TeamCheck and local_team != 0 and team == local_team:
                continue
            ch = sdk.get_character(mem, plr)
            if not mem.is_valid(ch):
                continue
            cmap = sdk.get_child_map(mem, ch)
            hum = cmap.get("Humanoid", 0)
            if not mem.is_valid(hum):
                continue
            hrp = sdk.pick_hrp(cmap, hum, mem)
            if not mem.is_valid(hrp):
                continue
            head = cmap.get("Head", 0)
            root_pos = sdk.get_part_position(mem, hrp)
            if not root_pos:
                continue
            head_pos = sdk.get_part_position(mem, head) if mem.is_valid(head) else None
            if not head_pos:
                head_pos = (root_pos[0], root_pos[1] + 3.0, root_pos[2])
            head_pos = (head_pos[0], head_pos[1] + 0.5, head_pos[2])
            try:
                hp = mem.f32(hum + O.get("Humanoid.Health"))
                mx = mem.f32(hum + O.get("Humanoid.MaxHealth"))
                if not math.isfinite(hp):
                    hp = 100.0
                if not math.isfinite(mx) or mx <= 0:
                    mx = 100.0
                if hp <= 0.5:
                    continue
            except Exception:
                hp, mx = 100.0, 100.0
            dist = math.dist(root_pos, camera_pos)
            if not math.isfinite(dist):
                continue
            if config.EnableMaxDistance and dist > config.MaxDistance:
                continue
            vel = sdk.get_part_velocity(mem, hrp) or (0.0, 0.0, 0.0)
            s_root = w2s(root_pos, screen_w, screen_h)
            s_head = w2s(head_pos, screen_w, screen_h)
            e = EspEntry()
            e.addr, e.head_addr, e.name = plr, head, pname
            e.team, e.hp, e.maxhp, e.dist = team, hp, mx, dist
            e.root3, e.head3, e.vel = root_pos, head_pos, vel
            e.root2, e.head2 = s_root or (0, 0), s_head or (0, 0)
            e.root_vis, e.head_vis = s_root is not None, s_head is not None
            e.onscreen = e.root_vis or e.head_vis
            e.tool = _get_tool(ch) if config.ShowTool else ""
            if config.Skeleton and e.onscreen:
                e.pairs, e.joints = _build_skeleton(ch)
            else:
                e.pairs, e.joints = [], {}
            out.append(e)
    except Exception:
        pass

    with _lock:
        _snapshot[:] = out
        _roster[:] = rost
