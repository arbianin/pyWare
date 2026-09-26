"""Sticky RMB aimbot with smoothing + triggerbot. No hotkeys besides the key itself."""
import ctypes
import math
import time

from . import config, engine

_user32 = ctypes.windll.user32

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
VK_RBUTTON = 0x02

current_target = None
last_aim_point = (0, 0)
_sticky = 0
_last_trigger = 0.0
_was_held = False
_has_sm = False
_aim_sm = (0.0, 0.0)
_rem_x = _rem_y = 0.0


def _held():
    return (_user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000) != 0


def _aim_point(e):
    anchor = e.root3 if config.AimTarget == 1 else e.head3
    if config.Prediction:
        try:
            k = 0.035 * config.AimLeadScale
            pred = (anchor[0] + e.vel[0] * k, anchor[1] + e.vel[1] * k, anchor[2] + e.vel[2] * k)
            sp = engine.w2s(pred, engine.screen_w, engine.screen_h)
            if sp:
                return sp
        except Exception:
            pass
    return e.root2 if config.AimTarget == 1 else e.head2


def _move(pt, cx, cy):
    global _rem_x, _rem_y
    global last_aim_point
    last_aim_point = pt
    dxt = (pt[0] - cx) / max(1.0, config.AimSmooth)
    dyt = (pt[1] - cy) / max(1.0, config.AimSmooth)
    mag = math.hypot(dxt, dyt)
    cap = max(1.0, config.AimMaxStep)
    if mag > cap:
        dxt, dyt = dxt / mag * cap, dyt / mag * cap
    dxt += _rem_x
    dyt += _rem_y
    mx, my = int(dxt), int(dyt)
    _rem_x, _rem_y = dxt - mx, dyt - my
    if mx == 0 and my == 0:
        return
    _user32.mouse_event(MOUSEEVENTF_MOVE, mx, my, 0, None)


def tick():
    global current_target, _sticky, _last_trigger, _was_held, _has_sm, _aim_sm, _rem_x, _rem_y
    current_target = None
    ents = engine.snapshot()
    if not ents:
        _sticky = 0
        _has_sm = False
        return
    if not config.AimEnabled:
        _sticky = 0
        _has_sm = False
        _was_held = False
        _rem_x = _rem_y = 0.0
        _trigger(ents)
        return

    cx, cy = engine.screen_w / 2, engine.screen_h / 2
    if not _held():
        _was_held = False
        _has_sm = False
        _rem_x = _rem_y = 0.0
        _trigger(ents)
        return
    if not _was_held:
        _was_held = True
        _sticky = 0
        _has_sm = False

    locked = None
    if _sticky:
        for e in ents:
            if e.addr == _sticky and e.onscreen:
                locked = e
                break
    if locked is None:
        best = config.AimFovPx
        for e in ents:
            if not e.onscreen:
                continue
            pt = _aim_point(e)
            if pt[0] < -500 or pt[1] < -500 or pt[0] > engine.screen_w + 500 or pt[1] > engine.screen_h + 500:
                continue
            d = math.hypot(pt[0] - cx, pt[1] - cy)
            if d > config.AimFovPx:
                continue
            if config.AimMode == 1:
                if locked is None or e.hp < locked.hp - 0.5 or (abs(e.hp - locked.hp) <= 0.5 and d < best):
                    locked, best = e, d
            elif d < best:
                locked, best = e, d
        _sticky = locked.addr if locked else 0
        _has_sm = False

    if locked is not None:
        current_target = locked
        pt = _aim_point(locked)
        if not _has_sm:
            _aim_sm, _has_sm = (float(pt[0]), float(pt[1])), True
        else:
            _aim_sm = (_aim_sm[0] + (pt[0] - _aim_sm[0]) * 0.55,
                       _aim_sm[1] + (pt[1] - _aim_sm[1]) * 0.55)
        _move(_aim_sm, cx, cy)

    _trigger(ents)


def _trigger(ents):
    global _last_trigger
    if not config.TriggerEnabled:
        return
    now = time.monotonic()
    if now - _last_trigger <= 0.12:
        return
    cx, cy = engine.screen_w / 2, engine.screen_h / 2
    for e in ents:
        if not e.onscreen:
            continue
        if math.hypot(e.head2[0] - cx, e.head2[1] - cy) <= config.TriggerRadius:
            _user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
            _user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
            _last_trigger = now
            break
