# -*- coding: utf-8 -*-
"""(v1.00.25) Đọc giờ thực tập hè (cột Work Hours, chữ tự do) cho kế hoạch tự học."""
import pytest
import study_plan as sp


@pytest.mark.parametrize('text, want', [
    ('T2-T6 8:00-17:00', [([0, 1, 2, 3, 4], '08:00', '17:00')]),
    ('T2,T4,T6 13h-17h30', [([0, 2, 4], '13:00', '17:30')]),
    ('thứ 2 - thứ 6, 8h30-12h', [([0, 1, 2, 3, 4], '08:30', '12:00')]),
    ('CN 8-12', [([6], '08:00', '12:00')]),
    ('T7 7:30-11:30; T3 18h-21h', [([5], '07:30', '11:30'), ([1], '18:00', '21:00')]),
    ('linh hoạt', []),
])
def test_parse_work_hours(text, want):
    got = [(sorted(d), sp._hm(a), sp._hm(b)) for d, a, b in sp.parse_work_hours(text)]
    assert got == want
