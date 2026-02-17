# widgets/__init__.py
# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT
from .widget import Widget
from .wind import WindDialWidget
from .windrose import WindRoseWidget
from .compass import CompassRose
from .arrow import SegmentedWindArrow
from .spider import SpiderWebGrid
from .temp_text import TempText

__all__ = [
    "CompassRose",
    "SegmentedWindArrow",
    "SpiderWebGrid",
    "TempText",
    "Widget",
    "WindDialWidget",
    "WindRoseWidget"
]