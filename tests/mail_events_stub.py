# -*- coding: utf-8 -*-
"""mail_events giả cho test: chỉ load / save / when_of (cùng luật đọc giờ với mail_events.when_of thật)."""
import datetime as dt, types

TZ = dt.timezone(dt.timedelta(hours=7))


def when_of(sg):
    if not sg.get('ngay'): return None
    try:
        d = dt.date.fromisoformat(sg['ngay'])
        h, m = (int(x) for x in (sg.get('gio') or '23:59').split(':')[:2])
        return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)
    except Exception:
        return None


def make(events):
    ns = types.SimpleNamespace(state={'events': events}, saved=[], TZ=TZ, when_of=when_of)
    ns.load = lambda: ns.state
    ns.save = lambda st: ns.saved.append(st)
    return ns
