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


def test_part_time_file_blocks_shifts(tmp_path, monkeypatch):
    # (v1.00.26) làm part-time trong năm: school/part_time.json dùng chung engine đọc giờ của thực tập hè
    import json
    (tmp_path / 'school').mkdir()
    (tmp_path / 'school' / 'part_time.json').write_text(json.dumps(
        [{'ten': 'Gia sư', 'tu': '2026-11-02', 'den': '2026-11-15', 'gio': 'T3 19h-21h'}], ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(sp, 'HERE', tmp_path)
    x = sp.extra(None)
    shifts = [g for g in x['going'] if g.get('kind') == 'intern']
    assert [str(g['day']) for g in shifts] == ['2026-11-03', '2026-11-10']          # 2 Thứ 3 trong khoảng
    assert all((sp._hm(g['start']), sp._hm(g['end'])) == ('19:00', '21:00') for g in shifts)


def test_no_part_time_file_means_none(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, 'HERE', tmp_path)
    assert not [g for g in sp.extra(None)['going'] if g.get('kind') == 'intern']
