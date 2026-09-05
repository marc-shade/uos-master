"""Shared helpers for the real-hardware scripts (deploy_hw, hw_*).

Never hardcode addresses that move with the source: the desktop's APP_TICK
vector shifted from $1f2c to $1f31 when five bytes were added at its entry,
and every script that had the literal reported a false FAIL. Resolve labels
from the 64tass listings instead.
"""
import os
import re

UOS = os.path.dirname(os.path.abspath(__file__))


def lst_symbol(module, name):
    """Address of `name` in target/<module>.lst.

    Handles the three 64tass forms:
      ">1f31  bb bb   name: .byte"   data label with bytes on the line
      ".1f31           name:"         label alone (data on the next line)
      "=$1f31          name = *"      assignment-style label
    """
    path = os.path.join(UOS, f"target/{module}.lst")
    lst = open(path, "rb").read().decode("latin-1", errors="replace")
    pats = (
        r"^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?%s:" % re.escape(name),
        r"^=\$([0-9a-fA-F]{4})\s+%s\s*=" % re.escape(name),
    )
    for p in pats:
        m = re.search(p, lst, re.M)
        if m:
            return int(m.group(1), 16)
    raise SystemExit(f"FAIL: {name} not found in {module} listing ({path})")


def desk_tick():
    """The desktop's APP_TICK handler — what $033c must hold when the desktop
    is the registered app."""
    return lst_symbol("uos-desktop", "APP_TICK")
