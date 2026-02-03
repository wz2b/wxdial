# wxdial/widgets/wx_icon.py
#
# Weather-aware icon widget that maps TWC icon codes
# to animated sprite assets (.wxs) and delegates rendering
# to IconAnimWidget.
#

from .icon_anim import IconAnimWidget

# twc_map.py
# returns a full path to a .wxs animation

ICON_DIR = "/wxdial/sprites"

TWC_TO_WXS = {
    0: "tornado.wxs",               # tornado    
    1: "heavyrain.wxs",             # substitute for tropical storm
    2: "windy.wxs",                 # substitute for hurricane
    3: "tstorm.wxs",                # Strong Storms
    4: "tstorm.wxs",                # Thunderstorms
    5: "rainsnow.wxs",              # mixed rain and snow
    6: "snowice.wxs",               # mixed rain and sleet
    7: "rainsnow.wxs",              # wintery mix
    8: "rainsnow.wxs",              # freezing drizzle
    9: "drizzle.wxs",               # drizzle
    10: "snowice.wxs",              # substitute for freezing rain
    11: "showers.wxs",              # showers
    12: "rain.wxs",                 # rain
    13: "flurries.wxs",             # snow flurries
    14: "snowshowers.wxs",          # snow showers
    15: "blowingsnow.wxs",          # blowing / drifting snow
    16: "snow.wxs",                 # snow
    17: "hail.wxs",                 # hail  
    18: "snowice.wxs",              # substitute for sleet
    19: "dust.wxs",                 # blowing dust / sandstorm
    20: "fog.wxs",                  # foggy
    21: "haze.wxs",                 # haze
    22: "smoke.wxs",                # smoke    
    23: "windy.wxs",                # substitute for breezy
    24: "windy.wxs",                # windy
    25: "icy.wxs",                  # frigid / ice crystals
    26: "cloudywindy.wxs",          # substitute for just cloudy
    27: "partlycloudynight.wxs",    # substitute for mostly cloudy night
    28: "partlycloudyday.wxs",      # substitute for mostly cloudy day
    29: "partlycloudynight.wxs",    # partly cloudy night
    30: "partlycloudyday.wxs",      # partly cloudy day
    31: "clearnight.wxs",           # clear night
    32: "sunnyday.wxs",             # sunny day
    33: "clearnight.wxs",           # fair / mostly clear night
    34: "sunnyday.wxs",             # fair / mostly clear day
    35: "hailrain.wxs",             # Mixed rain and hail
    36: "sunnyday.wxs",             # hot day
    37: "tstorm.wxs",               # substitute for isolated thunderstorms day
    38: "tstorm.wxs",               # substitute for scattered thunderstorms day
    39: "sctdshowers.wxs",          # substitute for scattered showers day
    40: "heavyrain.wxs",            # heavy rain
    41: "snowshowers.wxs",          # substitute for snow showers
    42: "heavysnow.wxs",            # heavy snow    
    43: "heavysnow.wxs",            # blizzard
    44: "na.wxs",                   # not available (change to question mark?)
    45: "sctdshowers.wxs",          # scattered showers night
    46: "snowshowers.wxs",          # scattered snow showers night
    47: "tstorm.wxs",               # scattered thunderstorms night
}

def twc_icon_path(code: int) -> str:
    name = TWC_TO_WXS.get(int(code), "na.wxs")
    return ICON_DIR + "/" + name


class WxIcon(IconAnimWidget):
    """
    Weather icon widget that understands TWC icon codes.

    Adds:
      - set_code(code): map TWC code → .wxs path → animation

    All animation behavior (timing, frame streaming, transparency)
    is inherited from IconAnimWidget.
    """

    def __init__(self, *, cx, cy, t, icon_path=None, code=None, tile_w=64, tile_h=64, visible=True):
        """
        Params:
          cx, cy: center position
          t: seconds per frame
          code: optional initial TWC icon code (int)
          tile_w, tile_h: fallback size for BMP assets (unused for .wxs)
        """
        # Start with no path; we’ll set it via set_code()
        super().__init__(
            cx=cx,
            cy=cy,
            t=t,
            path=None,
            tile_w=tile_w,
            tile_h=tile_h,
            visible=visible,
        )

        self._code = None
        self._icon_path = icon_path

        if code is not None:
            self.set_code(code)

    def set_code(self, code: int, *, reset=True, force_reload=False, verbose=True):
        try:
            code = int(code)
        except Exception:
            code = 44  # fallback to N/A

        new_path = twc_icon_path(code)

        old_code = self._code
        old_path = self._icon_path

        code_changed = (code != old_code)
        path_changed = (new_path != old_path)

        # Always record latest code
        self._code = code

        # Decide whether we will reload the asset
        will_reload = force_reload or path_changed

        # Print behavior:
        # - Print when code changed (your use-case)
        # - Mark whether asset changed
        if verbose and code_changed:
            tag = "(new asset)" if path_changed else "(same asset)"
            print(code, new_path, tag)

        # If we don't need to reload, we're done
        if not will_reload:
            return False

        # Commit the new asset path and reload
        self._icon_path = new_path
        super().set_path(new_path, reset=reset)
        return True


    @property
    def code(self):
        return self._code
