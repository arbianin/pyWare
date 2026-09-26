import ctypes
import math
import time

from PyQt5.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import QWidget

from . import aimbot, config, engine, hitbox, mods, teleport, world
from . import offsets as O

_user32 = ctypes.windll.user32

CATS = ["ESP", "AIM", "MODS", "WORLD", "MISC", "TP", "SYS"]
FRAME_W, ROW_H, BAR_W, TITLE_H = 250.0, 22.0, 104.0, 26.0

ACCENT = QColor(139, 92, 246)
ACCENT_HI = QColor(167, 139, 250)
BG = QColor(11, 11, 16)
TITLE_BG = QColor(21, 21, 29)
BORDER = QColor(42, 42, 53)
TEXT = QColor(237, 237, 242)
DIM = QColor(142, 142, 153)
GOOD = QColor(34, 197, 94)
BAD = QColor(239, 68, 68)


def apply_accent():
    global ACCENT, ACCENT_HI
    m = {
        1: ((34, 211, 238), (165, 243, 252)),
        2: ((249, 115, 22), (253, 186, 116)),
        3: ((236, 72, 153), (249, 168, 212)),
    }
    a, h = m.get(config.Accent, ((139, 92, 246), (167, 139, 250)))
    ACCENT, ACCENT_HI = QColor(*a), QColor(*h)


def enemy_box_color():
    return {
        1: QColor(0, 255, 0),
        2: QColor(80, 160, 255),
        3: QColor(200, 120, 255),
        4: QColor(255, 255, 255),
        5: QColor(255, 165, 0),
    }.get(config.BoxColor, QColor(255, 0, 0))


def with_a(c, a):
    return QColor(c.red(), c.green(), c.blue(), int(255 * max(0.0, min(1.0, a))))


# ---------------- menu rows ----------------
class Row:
    def __init__(self, text="", selectable=True):
        self.text = text
        self.selectable = selectable

    def key(self):
        return self.text

    def left(self):
        pass

    def right(self):
        pass

    def enter(self):
        pass


class HeaderRow(Row):
    def __init__(self, text):
        super().__init__(text, False)


class ToggleRow(Row):
    def __init__(self, label, get, set_):
        super().__init__(label)
        self.label, self.get, self.set_ = label, get, set_

    def key(self):
        return "t:" + self.label

    def enter(self):
        self.set_(not self.get())

    def render(self):
        return self.label


class CycleRow(Row):
    def __init__(self, label, opts, get, set_):
        super().__init__(label)
        self.label, self.opts, self.get, self.set_ = label, opts, get, set_

    def key(self):
        return "c:" + self.label

    def enter(self):
        self.set_((self.get() + 1) % len(self.opts))

    def render(self):
        return f"{self.label}: {self.opts[max(0, min(self.get(), len(self.opts) - 1))]}"


class SliderRow(Row):
    def __init__(self, label, get, set_, mn, mx, step):
        super().__init__(label)
        self.label, self.get, self.set_ = label, get, set_
        self.mn, self.mx, self.step = mn, mx, step

    def key(self):
        return "s:" + self.label

    def left(self):
        self.set_(max(self.mn, min(self.mx, self.get() - self.step)))

    def right(self):
        self.set_(max(self.mn, min(self.mx, self.get() + self.step)))

    def set_frac(self, f):
        f = max(0.0, min(1.0, f))
        self.set_(self.mn + f * (self.mx - self.mn))

    def frac(self):
        return max(0.0, min(1.0, (self.get() - self.mn) / max(1e-3, self.mx - self.mn)))

    def render(self):
        return f"{self.label}: {self.get():.1f}".rstrip("0").rstrip(".")


class ButtonRow(Row):
    def __init__(self, label, act):
        super().__init__(label)
        self.label, self.act = label, act

    def key(self):
        return "b:" + self.label

    def enter(self):
        self.act()

    def render(self):
        return f"[ {self.label} ]"


class PlayerRow(Row):
    def __init__(self, addr, text):
        super().__init__(text)
        self.addr = addr

    def key(self):
        return f"p:{self.addr}"


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        r = __import__("PyQt5.QtWidgets", fromlist=["QApplication"]).QApplication.primaryScreen().geometry()
        self.setGeometry(r)

        self.menu_open = True
        self.menu_t = time.monotonic()
        self.frame_pos: dict = {}
        self.collapsed = set()
        self.rows: dict = {}
        self.hit: list = []
        self.title_rects: list = []
        self.x_rects: list = []
        self.frame_rects: dict = {}
        self.hover_key = ""
        self.hover_k = 0.0
        self.fill_k: dict = {}
        self.tog_k: dict = {}
        self.drag_key = ""
        self.drag_frame = ""
        self.drag_off = (0, 0)
        self.l_down = False
        self.mouse = (0, 0)
        self.cfg_msg = ""
        self.rows_t = 0.0
        self.rows_dirty = True
        self.frames = 0
        self.fps = 0
        self.fps_t = time.monotonic()
        self.prev_ins = False

        self.font_menu = QFont("Segoe UI", 10, QFont.Bold)
        self.font_small = QFont("Segoe UI", 9, QFont.Bold)
        self.font_hud = QFont("Segoe UI", 11, QFont.Bold)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.frame)
        self.timer.start(16)

    # ---------------- window plumbing ----------------
    def set_click_through(self, through):
        self.setWindowFlag(Qt.WindowTransparentForInput, through)
        self.show()

    def set_menu_open(self, open_):
        self.menu_open = open_
        self.menu_t = time.monotonic()
        self.drag_key = ""
        self.drag_frame = ""
        self.rows_dirty = True
        self.set_click_through(not open_)
        print(f"[menu] {'OPEN' if open_ else 'CLOSED'} clickable={open_}", flush=True)

    def track_game(self):
        try:
            hwnd = _user32.FindWindowW(None, "Roblox")
            if not hwnd:
                return

            class RECT(ctypes.Structure):
                _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                            ("r", ctypes.c_long), ("b", ctypes.c_long)]

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            rc, pt = RECT(), POINT(0, 0)
            if _user32.GetClientRect(hwnd, ctypes.byref(rc)) == 0:
                return
            w, h = rc.r - rc.l, rc.b - rc.t
            if w < 100 or h < 100:
                return
            _user32.ClientToScreen(hwnd, ctypes.byref(pt))
            if (self.x(), self.y(), self.width(), self.height()) != (pt.x, pt.y, w, h):
                self.setGeometry(pt.x, pt.y, w, h)
            engine.window_w, engine.window_h = w, h
        except Exception:
            pass

    # ---------------- frame ----------------
    def frame(self):
        self.track_game()
        try:
            aimbot.tick()
            mods.tick()
            world.tick()
            hitbox.tick()
        except Exception:
            pass
        apply_accent()

        ins = (_user32.GetAsyncKeyState(0x2D) & 0x8000) != 0
        if ins and not self.prev_ins:
            self.set_menu_open(not self.menu_open)
        self.prev_ins = ins

        try:
            gp = self.mapFromGlobal(__import__("PyQt5.QtGui", fromlist=["QCursor"]).QCursor.pos())
            self.mouse = (gp.x(), gp.y())
        except Exception:
            pass
        self.hover_key = ""
        for row, rect in self.hit:
            if rect.contains(*self.mouse):
                self.hover_key = row.key()
                break
        self.hover_k = max(0.0, min(1.0, self.hover_k + (0.35 if self.hover_key else -0.35)))

        self.frames += 1
        now = time.monotonic()
        if now - self.fps_t >= 1.0:
            self.fps, self.frames, self.fps_t = self.frames, 0, now

        if self.menu_open and (self.rows_dirty or now - self.rows_t > 0.5 or not self.rows):
            self.build_frames()
            self.rows_t = now
            self.rows_dirty = False
        self.update()

    # ---------------- input ----------------
    @staticmethod
    def _bar(rect):
        return QRect(int(rect.x() + rect.width() - BAR_W - 8), int(rect.y() + 4), int(BAR_W), 14)

    def mousePressEvent(self, ev):
        if self.menu_open:
            self.handle_down((ev.x(), ev.y()), ev.button())

    def mouseMoveEvent(self, ev):
        if self.menu_open:
            self.handle_move((ev.x(), ev.y()))

    def mouseReleaseEvent(self, ev):
        if self.menu_open:
            self.handle_up()

    def wheelEvent(self, ev):
        if self.menu_open:
            self.handle_wheel((ev.x(), ev.y()), ev.angleDelta().y())

    def handle_down(self, p, btn):
        from PyQt5.QtCore import Qt as _Q
        if btn == _Q.LeftButton:
            self.l_down = True
        for xr in self.x_rects:
            if xr.contains(*p):
                self.set_menu_open(False)
                return True
        for cat, rect in self.title_rects:
            if rect.contains(*p):
                if btn == _Q.RightButton:
                    if cat in self.collapsed:
                        self.collapsed.remove(cat)
                    else:
                        self.collapsed.add(cat)
                    self.rows_dirty = True
                    print(f"[menu] {cat} {'collapsed' if cat in self.collapsed else 'expanded'}", flush=True)
                else:
                    self.drag_frame = cat
                    pos = self.frame_pos[cat]
                    self.drag_off = (p[0] - pos[0], p[1] - pos[1])
                return True
        for row, rect in self.hit:
            if not rect.contains(*p):
                continue
            if isinstance(row, ToggleRow):
                row.enter()
                print(f"[menu] {row.label} -> {row.render()}", flush=True)
            elif isinstance(row, CycleRow):
                row.enter()
                print(f"[menu] {row.render()}", flush=True)
            elif isinstance(row, SliderRow):
                bar = self._bar(rect)
                generous = QRect(bar.x(), bar.y() - 7, bar.width(), bar.height() + 14)
                if generous.contains(*p):
                    self.drag_key = row.key()
                    row.set_frac((p[0] - bar.x()) / max(1.0, bar.width()))
                    print(f"[menu] grab: {row.label}", flush=True)
                elif p[0] < rect.x() + rect.width() / 2:
                    row.left()
                else:
                    row.right()
            elif isinstance(row, ButtonRow):
                print(f"[menu] {row.label}", flush=True)
                row.enter()
            elif isinstance(row, PlayerRow):
                from PyQt5.QtCore import Qt as _Q2
                if btn == _Q2.RightButton:
                    teleport.bring_player(row.addr)
                else:
                    teleport.to_player(row.addr)
                print(f"[menu] player: {row.text}", flush=True)
            return True
        return False

    def handle_move(self, p):
        self.mouse = p
        if self.drag_frame and self.l_down:
            self.frame_pos[self.drag_frame] = (
                max(-200, min(p[0] - self.drag_off[0], self.width() - 60)),
                max(0, min(p[1] - self.drag_off[1], self.height() - 40)))
            return True
        if self.drag_key and self.l_down:
            for row, rect in self.hit:
                if row.key() == self.drag_key and isinstance(row, SliderRow):
                    bar = self._bar(rect)
                    row.set_frac((p[0] - bar.x()) / max(1.0, bar.width()))
                    return True
            self.drag_key = ""
        return False

    def handle_up(self):
        self.l_down = False
        was_frame = bool(self.drag_frame)
        self.drag_frame = ""
        if self.drag_key:
            print(f"[menu] slider: {self.drag_key}", flush=True)
            self.drag_key = ""
        if was_frame:
            return True
        for r in self.frame_rects.values():
            if r.contains(*self.mouse):
                return True
        return False

    def handle_wheel(self, p, delta):
        for r in self.frame_rects.values():
            if not r.contains(*p):
                continue
            for rows in self.rows.values():
                for row in rows:
                    if isinstance(row, SliderRow) and row.key() == self.hover_key:
                        if delta > 0:
                            row.right()
                        else:
                            row.left()
                        return True
            return True
        return False

    # ---------------- menu model ----------------
    def mini_status(self, r):
        r.append(HeaderRow(f"  {'LIVE' if engine.resolved else 'DOWN'} n={len(engine.snapshot())}"))

    def build_frames(self):
        allr = {c: [] for c in CATS}
        esp = allr["ESP"]
        self.mini_status(esp)
        esp += [
            ToggleRow("ESP enabled", lambda: config.EspEnabled, lambda v: setattr(config, "EspEnabled", v)),
            ToggleRow("Boxes", lambda: config.Boxes, lambda v: setattr(config, "Boxes", v)),
            ToggleRow("Corner box", lambda: config.CornerBox, lambda v: setattr(config, "CornerBox", v)),
            ToggleRow("3D box", lambda: config.ThreeDBox, lambda v: setattr(config, "ThreeDBox", v)),
            ToggleRow("Names", lambda: config.Names, lambda v: setattr(config, "Names", v)),
            ToggleRow("Equipped tool", lambda: config.ShowTool, lambda v: setattr(config, "ShowTool", v)),
            ToggleRow("Health", lambda: config.Health, lambda v: setattr(config, "Health", v)),
            ToggleRow("Health number", lambda: config.HealthText, lambda v: setattr(config, "HealthText", v)),
            ToggleRow("Distance", lambda: config.Distance, lambda v: setattr(config, "Distance", v)),
            ToggleRow("Snaplines", lambda: config.Snaplines, lambda v: setattr(config, "Snaplines", v)),
            CycleRow("Snap origin", ["bottom", "top", "cross"], lambda: config.SnapOrigin, lambda v: setattr(config, "SnapOrigin", v)),
            ToggleRow("Skeleton", lambda: config.Skeleton, lambda v: setattr(config, "Skeleton", v)),
            ToggleRow("Head dot", lambda: config.HeadDot, lambda v: setattr(config, "HeadDot", v)),
            ToggleRow("Team check", lambda: config.TeamCheck, lambda v: setattr(config, "TeamCheck", v)),
            ToggleRow("Team colors", lambda: config.TeamColors, lambda v: setattr(config, "TeamColors", v)),
            ToggleRow("Fade by distance", lambda: config.FadeDist, lambda v: setattr(config, "FadeDist", v)),
            ToggleRow("Max-dist filter", lambda: config.EnableMaxDistance, lambda v: setattr(config, "EnableMaxDistance", v)),
            SliderRow("Max dist", lambda: config.MaxDistance, lambda v: (setattr(config, "MaxDistance", v), setattr(config, "EnableMaxDistance", True)), 50, 10000, 50),
        ]
        aim = allr["AIM"]
        self.mini_status(aim)
        aim += [
            ToggleRow("Aimbot", lambda: config.AimEnabled, lambda v: setattr(config, "AimEnabled", v)),
            ToggleRow("Target: Head", lambda: config.AimTarget == 0, lambda v: setattr(config, "AimTarget", 0 if v else 1)),
            CycleRow("Aim pick", ["crosshair", "lowest hp"], lambda: config.AimMode, lambda v: setattr(config, "AimMode", v)),
            SliderRow("Aim FOV", lambda: config.AimFovPx, lambda v: (setattr(config, "AimFovPx", v), setattr(config, "AimEnabled", True)), 30, 800, 10),
            SliderRow("Smooth", lambda: config.AimSmooth, lambda v: (setattr(config, "AimSmooth", v), setattr(config, "AimEnabled", True)), 1, 20, 1),
            SliderRow("Max step", lambda: config.AimMaxStep, lambda v: (setattr(config, "AimMaxStep", v), setattr(config, "AimEnabled", True)), 5, 120, 5),
            ToggleRow("Velocity predict", lambda: config.Prediction, lambda v: setattr(config, "Prediction", v)),
            SliderRow("Lead scale", lambda: config.AimLeadScale, lambda v: (setattr(config, "AimLeadScale", v), setattr(config, "Prediction", True)), 0, 5, 0.5),
            ToggleRow("Crosshair", lambda: config.Crosshair, lambda v: setattr(config, "Crosshair", v)),
            SliderRow("XHair size", lambda: config.XhairSize, lambda v: setattr(config, "XhairSize", v), 0.5, 2.5, 0.1),
            ToggleRow("Target line", lambda: config.TargetLine, lambda v: setattr(config, "TargetLine", v)),
            ToggleRow("Triggerbot", lambda: config.TriggerEnabled, lambda v: setattr(config, "TriggerEnabled", v)),
            SliderRow("Trigger px", lambda: config.TriggerRadius, lambda v: (setattr(config, "TriggerRadius", v), setattr(config, "TriggerEnabled", True)), 4, 30, 1),
            ToggleRow("Head hitbox", lambda: config.HitboxEnabled, lambda v: setattr(config, "HitboxEnabled", v)),
            SliderRow("Hitbox size", lambda: config.HitboxSize, lambda v: (setattr(config, "HitboxSize", v), setattr(config, "HitboxEnabled", True)), 1, 10, 0.5),
        ]
        mods = allr["MODS"]
        self.mini_status(mods)
        mods += [
            HeaderRow("  writes OFF — disable SAFE MODE in SYS" if config.SafeMode else "  writes LIVE"),
            HeaderRow("  " + (f"walkspeed now: {engine.local_ws_now:.0f}" + (f" (want {engine.local_ws_want:.0f})" if engine.local_ws_want >= 0 else "") if engine.local_ws_now >= 0 else "walkspeed: (no humanoid)")),
            ToggleRow("Speed", lambda: config.SpeedEnabled, lambda v: setattr(config, "SpeedEnabled", v)),
            SliderRow("Walkspeed", lambda: config.Speed, lambda v: (setattr(config, "Speed", v), setattr(config, "SpeedEnabled", True)), 16, 500, 4),
            ToggleRow("Jump", lambda: config.JumpEnabled, lambda v: setattr(config, "JumpEnabled", v)),
            SliderRow("JumpPower", lambda: config.JumpPower, lambda v: (setattr(config, "JumpPower", v), setattr(config, "JumpEnabled", True)), 50, 500, 5),
            ToggleRow("Bunny hop", lambda: config.BhopEnabled, lambda v: setattr(config, "BhopEnabled", v)),
            ToggleRow("Fly [SPACE/C]", lambda: config.Fly, lambda v: setattr(config, "Fly", v)),
            SliderRow("Fly speed", lambda: config.FlySpeed, lambda v: (setattr(config, "FlySpeed", v), setattr(config, "Fly", True)), 10, 200, 5),
            ToggleRow("Invisibility (body)", lambda: config.Invis, lambda v: setattr(config, "Invis", v)),
            ToggleRow("Spinbot", lambda: config.Spin, lambda v: setattr(config, "Spin", v)),
            SliderRow("Spin speed", lambda: config.SpinSpeed, lambda v: (setattr(config, "SpinSpeed", v), setattr(config, "Spin", True)), 90, 3600, 90),
            ToggleRow("Gravity", lambda: config.GravityEnabled, lambda v: setattr(config, "GravityEnabled", v)),
            SliderRow("Gravity v", lambda: config.Gravity, lambda v: (setattr(config, "Gravity", v), setattr(config, "GravityEnabled", True)), 0, 500, 10),
            ToggleRow("Cam FOV", lambda: config.FovEnabled, lambda v: setattr(config, "FovEnabled", v)),
            SliderRow("FOV v", lambda: config.CamFov, lambda v: (setattr(config, "CamFov", v), setattr(config, "FovEnabled", True)), 30, 120, 1),
        ]
        wrld = allr["WORLD"]
        self.mini_status(wrld)
        wrld += [
            ToggleRow("Fullbright", lambda: config.Fullbright, lambda v: setattr(config, "Fullbright", v)),
            ToggleRow("No fog", lambda: config.NoFog, lambda v: setattr(config, "NoFog", v)),
            ToggleRow("Clock lock", lambda: config.ClockEnabled, lambda v: setattr(config, "ClockEnabled", v)),
            SliderRow("Hour", lambda: config.ClockTime, lambda v: (setattr(config, "ClockTime", v), setattr(config, "ClockEnabled", True)), 0, 24, 0.5),
            ToggleRow("Infinite zoom", lambda: config.InfZoom, lambda v: setattr(config, "InfZoom", v)),
            ButtonRow("Preset: Day", lambda: (setattr(config, "ClockTime", 14), setattr(config, "ClockEnabled", True), setattr(config, "Fullbright", False), setattr(config, "NoFog", False))),
            ButtonRow("Preset: Sunset", lambda: (setattr(config, "ClockTime", 18), setattr(config, "ClockEnabled", True), setattr(config, "Fullbright", False), setattr(config, "NoFog", False))),
            ButtonRow("Preset: Night", lambda: (setattr(config, "ClockTime", 0), setattr(config, "ClockEnabled", True), setattr(config, "Fullbright", True), setattr(config, "NoFog", True))),
        ]
        misc = allr["MISC"]
        self.mini_status(misc)
        misc += [
            CycleRow("Box color", ["red", "lime", "blue", "purple", "white", "orange"], lambda: config.BoxColor, lambda v: setattr(config, "BoxColor", v)),
            CycleRow("Accent", ["violet", "cyan", "orange", "pink"], lambda: config.Accent, lambda v: setattr(config, "Accent", v)),
            ButtonRow("Copy rejoin script", lambda: teleport.copy_rejoin()),
        ]
        tp = allr["TP"]
        self.mini_status(tp)
        tp += [
            ButtonRow("Save position", lambda: teleport.save_slot()),
            ButtonRow("TP to saved", lambda: teleport.load_slot()),
            ButtonRow("TP up +15", lambda: teleport.to_coords((engine.local_root[0], engine.local_root[1] + 15.0, engine.local_root[2]))),
            ButtonRow("Bring ALL here", lambda: teleport.bring_all()),
            HeaderRow("  " + (teleport.last or "")[:30]),
        ]
        snap = {e.addr: e for e in engine.snapshot()}
        shown = 0
        for addr, name in engine.roster():
            if shown >= 10:
                break
            e = snap.get(addr)
            extra = f"  {e.hp:.0f}hp" if e else ""
            tp.append(PlayerRow(addr, (name[:18] + extra)[:30]))
            shown += 1
        if len(engine.roster()) > shown:
            tp.append(HeaderRow(f"  +{len(engine.roster()) - shown} more"))
        if not engine.roster():
            tp.append(HeaderRow("  (no players)"))
        tp.append(HeaderRow("  L-click: tp to / R-click: bring"))

        sys = allr["SYS"]
        sys.append(HeaderRow("  PYWARE external"))
        sys.append(ToggleRow("SAFE MODE (writes off)", lambda: config.SafeMode, lambda v: setattr(config, "SafeMode", v)))
        sys.append(ButtonRow("Preset: Legit", lambda: self.apply_legit()))
        sys.append(ButtonRow("Preset: Rage", lambda: self.apply_rage()))
        for stage, ok, detail in engine.diag()[:8]:
            sys.append(HeaderRow(f"  [{'ok' if ok else '!!'}] {stage}"[:34]))
        sys.append(HeaderRow(f"  {O.effective_source}"[:34]))
        if engine.job_id:
            sys.append(HeaderRow("  job " + engine.job_id[:26]))
        sys.append(ButtonRow("Refetch + resolve", lambda: engine.refetch_and_resolve()))
        sys.append(ButtonRow("Save config", lambda: self._save_cfg()))
        sys.append(ButtonRow("Load config", lambda: self._load_cfg()))
        if self.cfg_msg:
            sys.append(HeaderRow("  " + self.cfg_msg[:30]))
        sys.append(ButtonRow("UNLOAD cheat", lambda: self.unload()))

        self.rows = allr
        counts = {c: len(v) for c, v in allr.items()}
        if counts != getattr(self, "_last_counts", None):
            self._last_counts = counts
            print(f"[menu] rows: {counts}", flush=True)
        cols = max(1, (self.width() - 24) // 270)
        for i, c in enumerate(CATS):
            if c not in self.frame_pos:
                self.frame_pos[c] = (12 + (i % cols) * 260.0, 64 + (i // cols) * 300.0)

    def _save_cfg(self):
        try:
            config.save()
            self.cfg_msg = "saved"
        except Exception as ex:
            self.cfg_msg = str(ex)[:30]

    def _load_cfg(self):
        try:
            config.load()
            self.cfg_msg = "loaded"
        except Exception as ex:
            self.cfg_msg = str(ex)[:30]

    def apply_legit(self):
        for k in ("SpeedEnabled", "JumpEnabled", "BhopEnabled", "Invis", "Fly", "GravityEnabled", "FovEnabled",
                  "Fullbright", "NoFog", "ClockEnabled", "InfZoom", "Spin"):
            setattr(config, k, False)
        config.EspEnabled, config.Boxes, config.Names, config.Distance = True, True, True, True
        config.Health, config.CornerBox, config.ThreeDBox, config.Skeleton = True, False, False, False
        config.Snaplines, config.HeadDot, config.ShowTool = False, False, False
        config.AimEnabled, config.TriggerEnabled = False, False
        print("[menu] preset: LEGIT", flush=True)

    def apply_rage(self):
        config.EspEnabled, config.Boxes, config.Names, config.Health = True, True, True, True
        config.Distance, config.Skeleton, config.HeadDot, config.TargetLine = True, True, True, True
        config.AimEnabled, config.AimTarget, config.AimMode = True, 0, 0
        config.AimFovPx, config.AimSmooth, config.AimMaxStep = 200, 2, 60
        config.Prediction, config.TriggerEnabled = True, True
        print("[menu] preset: RAGE", flush=True)

    def unload(self):
        print("[sys] unloading: restoring + exiting...", flush=True)

        def _bg():
            try:
                for k in ("SpeedEnabled", "JumpEnabled", "BhopEnabled", "Invis", "Fly", "GravityEnabled",
                          "FovEnabled", "Fullbright", "NoFog", "ClockEnabled", "InfZoom", "Spin",
                          "AimEnabled", "TriggerEnabled"):
                    setattr(config, k, False)
                mods.tick()
                world.tick()
            except Exception:
                pass
            finally:
                engine.stop()
                try:
                    from PyQt5.QtWidgets import QApplication
                    QApplication.quit()
                except Exception:
                    pass

        import threading
        threading.Thread(target=_bg, daemon=True).start()

    # ---------------- paint ----------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.fillRect(self.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        try:
            self.draw_esp(p)
        except Exception as ex:
            print(f"[paint] esp: {ex}", flush=True)
        try:
            self.draw_hud(p)
        except Exception as ex:
            print(f"[paint] hud: {ex}", flush=True)
        if self.menu_open:
            try:
                self.draw_frames(p)
            except Exception as ex:
                print(f"[paint] menu: {ex}", flush=True)
        p.end()

    @staticmethod
    def _fade(e):
        if not config.FadeDist:
            return 1.0
        return max(0.15, min(1.0, 1.0 - e.dist / max(1.0, config.MaxDistance)))

    def _text(self, p, s, x, y, color):
        p.setPen(QColor(0, 0, 0))
        p.setFont(self.font_small)
        p.drawText(int(x + 1), int(y + 11), s)
        p.setPen(color)
        p.drawText(int(x), int(y + 10), s)

    def draw_esp(self, p):
        if not config.EspEnabled and not config.AimEnabled and not config.Crosshair:
            return
        ents = engine.snapshot()
        cx, cy = engine.screen_w / 2, engine.screen_h / 2

        if config.Crosshair:
            pen = QPen(QColor(255, 255, 255, 220), 2)
            p.setPen(pen)
            gap, ln = 7 * config.XhairSize, 13 * config.XhairSize
            p.drawLine(int(cx - gap - ln), int(cy), int(cx - gap), int(cy))
            p.drawLine(int(cx + gap), int(cy), int(cx + gap + ln), int(cy))
            p.drawLine(int(cx), int(cy - gap - ln), int(cx), int(cy - gap))
            p.drawLine(int(cx), int(cy + gap), int(cx), int(cy + gap + ln))
        if config.AimEnabled:
            pulse = 100 + int(45 * math.sin(time.monotonic() / 0.28))
            p.setPen(QPen(QColor(0, 255, 0, max(0, min(255, pulse))), 2))
            p.setBrush(Qt.NoBrush)
            f = config.AimFovPx
            p.drawEllipse(int(cx - f), int(cy - f), int(f * 2), int(f * 2))
            p.setBrush(QBrush(QColor(0, 255, 0)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(int(cx - 2), int(cy - 2), 4, 4)
        if config.TargetLine and aimbot.current_target is not None:
            ax, ay = aimbot.last_aim_point
            p.setPen(QPen(QColor(0, 255, 0), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawLine(int(cx), int(cy), int(ax), int(ay))
            pr = 6 + 2 * math.sin(time.monotonic() / 0.25)
            p.drawEllipse(int(ax - pr), int(ay - pr), int(pr * 2), int(pr * 2))
        if not config.EspEnabled:
            return

        labels = []
        for e in ents:
            if not e.onscreen:
                continue
            rx, ry = e.root2
            hx, hy = e.head2
            if not all(map(math.isfinite, (rx, ry, hx, hy))):
                continue
            fade = self._fade(e)
            ally = engine.local_team != 0 and e.team == engine.local_team
            if aimbot.current_target is e:
                base = QColor(0, 255, 0)
            elif config.TeamColors and ally:
                base = QColor(0, 255, 255)
            else:
                base = enemy_box_color()
            col = with_a(base, fade)

            if config.Snaplines and e.root_vis:
                sx, sy = engine.screen_w / 2, engine.screen_h
                if config.SnapOrigin == 1:
                    sy = 0
                elif config.SnapOrigin == 2:
                    sx, sy = cx, cy
                p.setPen(QPen(QColor(255, 255, 255, int(140 * fade)), 1.5))
                p.drawLine(int(sx), int(sy), int(rx), int(ry))

            h = abs(ry - hy)
            if not e.root_vis or not e.head_vis or h < 4 or h > 2000:
                continue
            w = h / 2
            x = hx - w / 2
            y = hy
            if config.Boxes or config.ThreeDBox:
                p.setPen(QPen(col, 2))
                p.setBrush(Qt.NoBrush)
                if config.ThreeDBox:
                    self._draw_box3d(p, e, col, labels)
                else:
                    if config.CornerBox:
                        cl = min(w, h) * 0.25
                        for x1, y1, x2, y2 in (
                            (x, y + cl, x, y), (x, y, x + cl, y),
                            (x + w - cl, y, x + w, y), (x + w, y, x + w, y + cl),
                            (x + w, y + h - cl, x + w, y + h), (x + w, y + h, x + w - cl, y + h),
                            (x + cl, y + h, x, y + h), (x, y + h, x, y + h - cl)):
                            p.drawLine(int(x1), int(y1), int(x2), int(y2))
                    else:
                        p.drawRect(int(x), int(y), int(w), int(h))
                    if config.Health:
                        frac = max(0.0, min(1.0, e.hp / max(1.0, e.maxhp)))
                        p.setBrush(QBrush(QColor(int(255 * (1 - frac)), int(255 * frac), 0, int(255 * fade))))
                        p.setPen(Qt.NoPen)
                        p.drawRect(int(x - 6), int(y + h * (1 - frac)), 4, int(h * frac))
                        p.setBrush(Qt.NoBrush)
                        p.setPen(QPen(QColor(128, 128, 128), 1))
                        p.drawRect(int(x - 6), int(y), 4, int(h))
                        if config.HealthText:
                            labels.append((f"{e.hp:.0f}", x + w + 3, y + h - 14, with_a(QColor(255, 255, 255), fade)))
                    if config.Names:
                        labels.append((e.name, hx - 30, y - 18, with_a(QColor(255, 255, 255), fade)))
                    if config.ShowTool and e.tool:
                        labels.append((f"[{e.tool}]", hx - 30, y - 30, with_a(QColor(255, 255, 255), fade)))
                    if config.Distance:
                        labels.append((f"{e.dist:.0f}m", rx - 20, ry + 2, with_a(QColor(255, 255, 255), fade)))
            if config.Skeleton:
                p.setPen(QPen(QColor(0, 255, 0, int(230 * fade)), 2))
                max_seg = h * 3.0
                for a, b in e.pairs:
                    if a not in e.joints or b not in e.joints:
                        continue
                    pa = engine.w2s(e.joints[a], engine.screen_w, engine.screen_h)
                    pb = engine.w2s(e.joints[b], engine.screen_w, engine.screen_h)
                    if not pa or not pb:
                        continue
                    if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) > max_seg:
                        continue
                    p.drawLine(int(pa[0]), int(pa[1]), int(pb[0]), int(pb[1]))
            if config.HeadDot and e.head_vis:
                c = QColor(0, 255, 0) if aimbot.current_target is e else QColor(255, 255, 255)
                p.setBrush(QBrush(with_a(c, fade)))
                p.setPen(Qt.NoPen)
                p.drawEllipse(int(hx - 4), int(hy - 4), 8, 8)

        # label de-collision: stack instead of overprint
        if labels:
            fm = p.fontMetrics()
            labels.sort(key=lambda t: t[2])
            placed = []
            for text, lx, ly, lc in labels:
                ww = fm.horizontalAdvance(text) + 4
                r = QRect(int(lx - 2), int(ly), int(ww), 14)
                guard = 0
                while guard < 10 and any(r.intersects(q) for q in placed):
                    r.translate(0, 13)
                    guard += 1
                placed.append(r)
                self._text(p, text, r.x() + 2, r.y(), lc)

    def _draw_box3d(self, p, e, col, labels):
        top, bot = e.head3[1] + 0.6, e.root3[1] - 3.2
        x, z, hw, hd = e.root3[0], e.root3[2], 1.5, 1.0
        corners = [(x - hw, top, z - hd), (x + hw, top, z - hd), (x + hw, top, z + hd), (x - hw, top, z + hd),
                   (x - hw, bot, z - hd), (x + hw, bot, z - hd), (x + hw, bot, z + hd), (x - hw, bot, z + hd)]
        pts = [engine.w2s(c, engine.screen_w, engine.screen_h) for c in corners]
        if not all(pts):
            return
        p.setPen(QPen(col, 2))
        for i, j in ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)):
            p.drawLine(int(pts[i][0]), int(pts[i][1]), int(pts[j][0]), int(pts[j][1]))
        if config.Names:
            labels.append((e.name, pts[0][0] - 20, pts[0][1] - 18, QColor(255, 255, 255)))

    def draw_hud(self, p):
        color = QColor(0, 255, 0) if engine.resolved else QColor(255, 0, 0)
        text = f"pyWARE {self.fps}fps"
        p.setFont(self.font_hud)
        r = QRect(0, 10, self.width(), 24)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.setPen(QColor(0, 0, 0))
            p.drawText(QRect(r.x() + dx, r.y() + dy, r.width(), r.height()), Qt.AlignHCenter, text)
        p.setPen(color)
        p.drawText(r, Qt.AlignHCenter, text)

    # ---------------- ClickGUI frames ----------------
    def draw_frames(self, p):
        now = time.monotonic()
        k_all = max(0.0, min(1.0, (now - self.menu_t) / 0.22))
        k = 1 - (1 - k_all) ** 3
        self.hit.clear()
        self.title_rects.clear()
        self.x_rects.clear()
        self.frame_rects.clear()
        for fi, cat in enumerate(CATS):
            rows = self.rows.get(cat, [])
            collapsed = cat in self.collapsed
            if not rows and not collapsed:
                rows = [HeaderRow("  (empty)")]
            vis = 0 if collapsed else len(rows)
            kk = max(0.0, min(1.0, (now - self.menu_t - fi * 0.045) / 0.24))
            kk = 1 - (1 - kk) ** 3
            px = self.frame_pos[cat][0] - 50 * (1 - kk)
            py = self.frame_pos[cat][1]
            if not (math.isfinite(px) and math.isfinite(py)):
                px, py = 12.0, 64.0
                self.frame_pos[cat] = (px, py)
            ph = TITLE_H + vis * ROW_H + 6
            bg_a = int(150 + 55 * kk)
            self.frame_rects[cat] = QRect(int(px), int(py), int(FRAME_W), int(ph))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(11, 11, 16, bg_a)))
            p.drawRect(int(px), int(py), int(FRAME_W), int(ph))
            p.setPen(QPen(BORDER, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(int(px), int(py), int(FRAME_W), int(ph))

            title = QRect(int(px), int(py), int(FRAME_W), int(TITLE_H))
            self.title_rects.append((cat, title))
            p.setBrush(QBrush(QColor(21, 21, 29, bg_a)))
            p.setPen(Qt.NoPen)
            p.drawRect(title)
            p.setPen(QPen(ACCENT, 2))
            p.drawLine(int(title.x() + 6), int(title.bottom() - 2), int(title.right() - 6), int(title.bottom() - 2))
            self.draw_icon(p, cat, px + 9, py + 6, 14, ACCENT_HI)
            p.setPen(TEXT)
            p.setFont(self.font_menu)
            p.drawText(int(px + 28), int(py + 18), ("+ " if collapsed else "- ") + cat)
            xr = QRect(int(px + FRAME_W - 26), int(py + 4), 20, 17)
            self.x_rects.append(xr)
            p.setBrush(QBrush(QColor(120, 60, 20, 20)))
            p.setPen(Qt.NoPen)
            p.drawRect(xr)
            p.setPen(DIM)
            p.setFont(self.font_small)
            p.drawText(xr, Qt.AlignCenter, "x")
            if collapsed:
                continue

            y0 = py + TITLE_H + 3
            for i in range(vis):
                row = rows[i]
                ry = y0 + i * ROW_H
                rect = QRect(int(px + 5), int(ry), int(FRAME_W - 10), int(ROW_H))
                if row.selectable:
                    self.hit.append((row, rect))
                hov = row.key() == self.hover_key and row.selectable
                if hov:
                    p.setBrush(QBrush(QColor(139, 92, 246, int(60 * self.hover_k) + 25)))
                    p.setPen(Qt.NoPen)
                    p.drawRect(rect)
                if isinstance(row, ToggleRow):
                    k2 = self.tog_k.get(row.key(), 1.0 if row.get() else 0.0)
                    k2 += ((1.0 if row.get() else 0.0) - k2) * 0.35
                    self.tog_k[row.key()] = k2
                    p.setPen(TEXT)
                    p.setFont(self.font_menu)
                    p.drawText(int(px + 12), int(ry + 15), row.render())
                    pill_x, pill_w = px + FRAME_W - 50, 36
                    pill_y, pill_h = ry + 3, 14
                    p.setBrush(QBrush(ACCENT if k2 > 0.5 else QColor(58, 58, 66, 170)))
                    p.setPen(Qt.NoPen)
                    p.drawRoundedRect(int(pill_x), int(pill_y), int(pill_w), int(pill_h), 7, 7)
                    kx = pill_x + 2 + k2 * (pill_w - 16)
                    p.setBrush(QBrush(QColor(255, 255, 255)))
                    p.drawEllipse(int(kx), int(pill_y + 1), 12, 12)
                elif isinstance(row, CycleRow):
                    p.setPen(TEXT)
                    p.setFont(self.font_menu)
                    p.drawText(int(px + 12), int(ry + 15), row.render() + ("  >>" if hov else ""))
                elif isinstance(row, SliderRow):
                    p.setPen(TEXT)
                    p.setFont(self.font_menu)
                    p.drawText(int(px + 12), int(ry + 15), row.render())
                    bar = self._bar(rect)
                    disp = self.fill_k.get(row.key(), row.frac())
                    disp += (row.frac() - disp) * 0.4
                    self.fill_k[row.key()] = disp
                    p.setBrush(QBrush(QColor(40, 40, 48, 200)))
                    p.setPen(Qt.NoPen)
                    p.drawRect(bar)
                    p.setBrush(QBrush(ACCENT))
                    p.drawRect(int(bar.x()), int(bar.y()), int(bar.width() * disp), int(bar.height()))
                    p.setPen(QPen(BORDER, 1))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(bar)
                    kx = bar.x() + bar.width() * disp
                    p.setBrush(QBrush(QColor(255, 255, 255)))
                    p.setPen(QPen(QColor(0, 0, 0), 1))
                    p.drawEllipse(int(kx - 7), int(bar.y() - 4), 14, 22)
                elif isinstance(row, ButtonRow):
                    br = QRect(int(rect.x()), int(rect.y() + 1), int(rect.width()), int(ROW_H - 4))
                    p.setBrush(QBrush(QColor(139, 92, 246, 120 if hov else 0) if hov else QColor(30, 30, 38, 70)))
                    p.setPen(QPen(BORDER, 1))
                    p.drawRect(br)
                    p.setPen(TEXT)
                    p.setFont(self.font_menu)
                    p.drawText(br, Qt.AlignCenter, row.render())
                else:
                    c = DIM
                    if row.text.startswith("  [!!]"):
                        c = BAD
                    elif row.text.startswith("  [ok]"):
                        c = GOOD
                    p.setPen(c)
                    p.setFont(self.font_small)
                    p.drawText(int(px + 12), int(ry + 16), row.text)

    @staticmethod
    def draw_icon(p, cat, x, y, s, c):
        p.setPen(QPen(c, max(1.5, s / 8)))
        p.setBrush(Qt.NoBrush)
        cx, cy, r = x + s / 2, y + s / 2, s / 2 - 1
        if cat == "ESP":
            p.drawEllipse(int(x + 1), int(cy - r * 0.62), int(s - 2), int(r * 1.24))
            p.setBrush(QBrush(c))
            p.setPen(Qt.NoPen)
            p.drawEllipse(int(cx - r * 0.22), int(cy - r * 0.22), int(r * 0.44), int(r * 0.44))
        elif cat == "AIM":
            p.drawEllipse(int(x + 1), int(y + 1), int(s - 2), int(s - 2))
            p.drawLine(int(cx - r - 2), int(cy), int(cx - r + 2), int(cy))
            p.drawLine(int(cx + r - 2), int(cy), int(cx + r + 2), int(cy))
            p.drawLine(int(cx), int(cy - r - 2), int(cx), int(cy - r + 2))
            p.drawLine(int(cx), int(cy + r - 2), int(cx), int(cy + r + 2))
        elif cat == "MODS":
            p.setBrush(QBrush(c))
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([
                QPointF(x + s * 0.55, y), QPointF(x + s * 0.2, y + s * 0.55),
                QPointF(x + s * 0.45, y + s * 0.55), QPointF(x + s * 0.4, y + s),
                QPointF(x + s * 0.8, y + s * 0.42), QPointF(x + s * 0.55, y + s * 0.42)]))
        elif cat == "WORLD":
            p.drawEllipse(int(x + 1), int(y + 1), int(s - 2), int(s - 2))
            p.drawEllipse(int(cx - r * 0.45), int(y + 1), int(r * 0.9), int(s - 2))
            p.drawLine(int(x + 1), int(cy), int(x + s - 1), int(cy))
        elif cat == "MISC":
            p.setBrush(QBrush(c))
            p.setPen(Qt.NoPen)
            for i in range(3):
                for j in range(3):
                    p.drawEllipse(int(x + 1 + i * (s - 2) / 2 - 1), int(y + 1 + j * (s - 2) / 2 - 1), 2, 2)
        elif cat == "TP":
            p.drawLine(int(x + 1), int(cy), int(x + s - 4), int(cy))
            p.drawLine(int(x + s - 8), int(cy - 4), int(x + s - 1), int(cy))
            p.drawLine(int(x + s - 8), int(cy + 4), int(x + s - 1), int(cy))
        else:
            for i in range(3):
                ly = y + 2 + i * (s - 4) / 2
                p.drawLine(int(x + 1), int(ly), int(x + s - 1), int(ly))
                kx = x + 2 + ((i * 5 + 2) % int(s - 5))
                p.setBrush(QBrush(c))
                p.setPen(Qt.NoPen)
                p.drawRect(int(kx), int(ly - 2), 4, 4)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(c, max(1.5, s / 8)))
