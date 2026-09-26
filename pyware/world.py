from . import config, engine, sdk

O = __import__("pyware.offsets", fromlist=["get"]).get

_cached = False
_amb = _out = (1.0, 1.0, 1.0)
_bright = _fog_s = _fog_e = 0.0
_fb_on = _fog_on = False
_zoom_lp = 0
_max_z = _min_z = 0.0
_zoom_cached = _zoom_on = False


def _ensure(mem, la):
    global _cached, _amb, _out, _bright, _fog_s, _fog_e
    if _cached:
        return
    _amb = mem.vec3(la + O("Lighting.Ambient"))
    _out = mem.vec3(la + O("Lighting.OutdoorAmbient"))
    _bright = mem.f32(la + O("Lighting.Brightness"))
    _fog_s = mem.f32(la + O("Lighting.FogStart"))
    _fog_e = mem.f32(la + O("Lighting.FogEnd"))
    _cached = True


def tick():
    global _fb_on, _fog_on, _zoom_lp, _max_z, _min_z, _zoom_cached, _zoom_on
    mem = engine.mem
    if not mem.attached or not engine.resolved or config.SafeMode:
        return
    try:
        la = engine.lighting_addr
        lok = mem.is_valid(la)
        if config.Fullbright and lok:
            _ensure(mem, la)
            mem.write_vec3(la + O("Lighting.Ambient"), (1, 1, 1))
            mem.write_vec3(la + O("Lighting.OutdoorAmbient"), (1, 1, 1))
            mem.write_f32(la + O("Lighting.Brightness"), 3.0)
            _fb_on = True
        elif _fb_on and lok:
            mem.write_vec3(la + O("Lighting.Ambient"), _amb)
            mem.write_vec3(la + O("Lighting.OutdoorAmbient"), _out)
            mem.write_f32(la + O("Lighting.Brightness"), _bright)
            _fb_on = False

        if config.NoFog and lok:
            _ensure(mem, la)
            mem.write_f32(la + O("Lighting.FogStart"), 100000.0)
            mem.write_f32(la + O("Lighting.FogEnd"), 100000.0)
            _fog_on = True
        elif _fog_on and lok:
            mem.write_f32(la + O("Lighting.FogStart"), _fog_s)
            mem.write_f32(la + O("Lighting.FogEnd"), _fog_e)
            _fog_on = False

        if config.ClockEnabled and lok:
            mem.write_f32(la + O("Lighting.ClockTime"), config.ClockTime)

        lp = sdk.localplayer
        if config.InfZoom and mem.is_valid(lp):
            if not _zoom_cached or _zoom_lp != lp:
                _max_z = mem.f32(lp + O("Player.MaxZoomDistance"))
                _min_z = mem.f32(lp + O("Player.MinZoomDistance"))
                _zoom_lp, _zoom_cached = lp, True
            mem.write_f32(lp + O("Player.MaxZoomDistance"), 100000.0)
            mem.write_f32(lp + O("Player.MinZoomDistance"), 0.0)
            _zoom_on = True
        elif _zoom_on and mem.is_valid(_zoom_lp):
            mem.write_f32(_zoom_lp + O("Player.MaxZoomDistance"), _max_z)
            mem.write_f32(_zoom_lp + O("Player.MinZoomDistance"), _min_z)
            _zoom_on = False
    except Exception:
        pass
