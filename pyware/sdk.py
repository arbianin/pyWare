import time

from . import offsets as O

datamodel = workspace = players = localplayer = camera = visualengine = world = 0
lasterror = ""
lastlines = []  # [(stage, ok, detail)]

_child_maps: dict[int, tuple[dict, float]] = {}
_bone_cache: dict[int, tuple[dict, float]] = {}


def _line(lines, stage, ok, detail):
    lines.append((stage, bool(ok), str(detail)))


def resolve_all(mem):
    """Returns True only if DataModel/Workspace/Players classes validate."""
    global datamodel, workspace, players, localplayer, camera, visualengine, world
    global lasterror, lastlines
    lines = []
    datamodel = workspace = players = localplayer = camera = visualengine = world = 0
    if not mem.attached:
        lasterror = "not attached"
        lastlines = lines
        return False

    base = mem.base
    _line(lines, "base", base != 0, hex(base))

    fake = mem.u64(base + O.get("FakeDataModel.Pointer"))
    _line(lines, "fakeDM", mem.is_valid(fake), f"{hex(fake)} (static {hex(O.get('FakeDataModel.Pointer'))})")
    if mem.is_valid(fake):
        datamodel = mem.u64(fake + O.get("FakeDataModel.RealDataModel"))

    if not mem.is_valid(datamodel):
        try:
            ve = mem.u64(base + O.get("VisualEngine.Pointer"))
            if mem.is_valid(ve):
                visualengine = ve
                fake2 = mem.u64(ve + O.get("VisualEngine.FakeDataModel"))
                if mem.is_valid(fake2):
                    datamodel = mem.u64(fake2 + O.get("FakeDataModel.RealDataModel"))
        except Exception:
            pass
    _line(lines, "dataModel", mem.is_valid(datamodel), hex(datamodel))

    dm_class = get_class_name(mem, datamodel)
    _line(lines, "dmClass", dm_class == "DataModel", f"'{dm_class}' (want 'DataModel')")
    if dm_class != "DataModel":
        lasterror = f"DataModel class mismatch ('{dm_class}') — stale offsets"
        lastlines = lines
        return False

    workspace = mem.u64(datamodel + O.get("DataModel.Workspace"))
    ws_class = get_class_name(mem, workspace)
    _line(lines, "workspace", ws_class == "Workspace", f"'{ws_class}' {hex(workspace)}")
    if ws_class != "Workspace":
        lasterror = "Workspace class mismatch — stale offsets"
        lastlines = lines
        return False

    camera = mem.u64(workspace + O.get("Workspace.CurrentCamera"))
    world = mem.u64(workspace + O.get("Workspace.World"))
    _line(lines, "camera", mem.is_valid(camera), hex(camera))

    if not mem.is_valid(visualengine):
        visualengine = mem.u64(base + O.get("VisualEngine.Pointer"))
    vm_ok = False
    try:
        m = mem.mat16(visualengine + O.get("VisualEngine.ViewMatrix"))
        vm_ok = any(abs(v) > 1e-9 for v in m) and abs(m[15]) + abs(m[0]) + abs(m[5]) > 0.01
    except Exception:
        pass
    _line(lines, "viewMatrix", vm_ok, f"ve {hex(visualengine)}")

    pls = find_first_child(mem, datamodel, "Players")
    if not mem.is_valid(pls):
        pls = find_first_child_of_class(mem, datamodel, "Players")
    players = pls
    pl_class = get_class_name(mem, players)
    pl_count = len(get_children(mem, players)) if mem.is_valid(players) else 0
    _line(lines, "players", pl_class == "Players", f"'{pl_class}' {pl_count} children")
    if pl_class != "Players":
        lasterror = "Players not found — stale offsets"
        lastlines = lines
        return False

    lp = mem.u64(players + O.get("Player.LocalPlayer"))
    lp_class = get_class_name(mem, lp)
    _line(lines, "localPlayer", lp_class == "Player", f"'{lp_class}' {hex(lp)}")
    localplayer = lp if lp_class == "Player" else 0

    lastlines = lines
    return True


def get_name(mem, inst):
    if not mem.is_valid(inst):
        return ""
    try:
        container = mem.u64(inst + O.get("Instance.NameContainer"))
        if not mem.is_valid(container):
            return ""
        return mem.rbx_string(container + O.get("Instance.Name"))
    except Exception:
        return ""


def get_class_name(mem, inst):
    if not mem.is_valid(inst):
        return ""
    try:
        desc = mem.u64(inst + O.get("Instance.ClassDescriptor"))
        if not mem.is_valid(desc):
            return ""
        obj = mem.u64(desc + O.get("Instance.ClassName"))
        if not mem.is_valid(obj):
            return ""
        return mem.rbx_string(obj)
    except Exception:
        return ""


def get_children(mem, inst):
    out = []
    if not mem.is_valid(inst):
        return out
    try:
        vec = mem.u64(inst + O.get("Instance.ChildrenStart"))
        if not mem.is_valid(vec):
            return out
        begin = mem.u64(vec)
        end = mem.u64(vec + O.get("Instance.ChildrenEnd"))
        if not mem.is_valid(begin) or end <= begin or end - begin > 0x10 * 4096:
            return out
        ptr = begin
        while ptr < end:
            c = mem.u64(ptr)
            if mem.is_valid(c):
                out.append(c)
            ptr += 0x10
    except Exception:
        pass
    return out


def find_first_child(mem, parent, name):
    for c in get_children(mem, parent):
        if get_name(mem, c) == name:
            return c
    return 0


def find_first_child_of_class(mem, parent, classname):
    for c in get_children(mem, parent):
        if get_class_name(mem, c) == classname:
            return c
    return 0


def find_all_of_class(mem, parent, classname):
    return [c for c in get_children(mem, parent) if get_class_name(mem, c) == classname]


def get_child_map(mem, parent):
    now = time.monotonic()
    e = _child_maps.get(parent)
    if e and now < e[1]:
        return dict(e[0])
    m = {}
    for c in get_children(mem, parent):
        n = get_name(mem, c)
        if n and n not in m:
            m[n] = c
    if len(_child_maps) > 512:
        _child_maps.clear()
    _child_maps[parent] = (m, now + 2.0)
    return dict(m)


def get_bone_parts(mem, ch):
    """Class-verified Part/MeshPart addrs per character (TTL 5s)."""
    now = time.monotonic()
    e = _bone_cache.get(ch)
    if e and now < e[1]:
        return dict(e[0])
    parts = {}
    for c in get_children(mem, ch):
        try:
            cl = get_class_name(mem, c)
            if cl not in ("Part", "MeshPart"):
                continue
            n = get_name(mem, c)
            if n and n not in parts:
                parts[n] = c
        except Exception:
            pass
    if len(_bone_cache) > 128:
        _bone_cache.clear()
    _bone_cache[ch] = (parts, now + 5.0)
    return dict(parts)


def get_part_position(mem, part):
    if not mem.is_valid(part):
        return None
    try:
        prim = mem.u64(part + O.get("BasePart.Primitive"))
        if not mem.is_valid(prim):
            return None
        return mem.vec3(prim + O.get("Primitive.Position"))
    except Exception:
        return None


def get_part_velocity(mem, part):
    if not mem.is_valid(part):
        return None
    try:
        prim = mem.u64(part + O.get("BasePart.Primitive"))
        if not mem.is_valid(prim):
            return None
        return mem.vec3(prim + O.get("Primitive.AssemblyLinearVelocity"))
    except Exception:
        return None


def get_character(mem, player):
    if not mem.is_valid(player):
        return 0
    try:
        return mem.u64(player + O.get("Player.ModelInstance"))
    except Exception:
        return 0


def pick_hrp(char_map, hum, mem):
    for n in ("HumanoidRootPart", "UpperTorso", "Torso"):
        a = char_map.get(n, 0)
        if mem.is_valid(a):
            return a
    if mem.is_valid(hum):
        try:
            alt = mem.u64(hum + O.get("Humanoid.HumanoidRootPart"))
            if mem.is_valid(alt):
                return alt
        except Exception:
            pass
    return 0


def get_player_name(mem, player):
    if not mem.is_valid(player):
        return "?"
    try:
        d = mem.rbx_string(player + O.get("Player.DisplayName"))
        if d and d != "Unknown":
            return d
    except Exception:
        pass
    return get_name(mem, player) or "?"
