# -*- coding: utf-8 -*-
"""Hạn tự luyện tự gia hạn +1 tuần (deadlines.extend_plan / is_self) và link bấm thông báo (work_link) — dữ liệu giả, không gọi mạng."""
import datetime as dt

import deadlines as D

NOW = dt.datetime(2026, 10, 19, 10, 0, tzinfo=D.TZ)


def row(i, kind, due, **k):
    return dict({'id': i, 'name': f'viec {i}', 'kind': kind, 'due': due, 'status': 'Not started', 'link': '', 'url': f'https://notion.example/{i}'}, **k)


ROWS = [
    row('a', 'Tự luyện', '2026-10-18T21:00:00+07:00'),                                    # quá 13 giờ -> +1 tuần
    row('b', 'Tự luyện cốt lõi', '2026-10-02T21:00:00+07:00'),                            # quá 17 ngày -> +3 tuần
    row('c', 'Môn học', '2026-10-18T21:00:00+07:00'),                                     # hạn của trường -> không dời
    row('d', 'Tự luyện', '2026-10-25T21:00:00+07:00'),                                    # còn sống -> không dời
    row('e', 'Tự luyện', '2026-10-18T21:00:00+07:00', status='Submitted'),                # đã nộp -> không dời
    row('f', 'Tự luyện', '2026-10-18T21:00:00+07:00', link='https://fami.hust.edu.vn/x'), # link trường -> không dời
    row('g', 'Tự luyện', '2026-10-18T21:00:00+07:00', name='Quiz 3 (MOOC)'),              # tên của trường -> không dời
]


def test_chi_hen_tu_luyen_qua_han_moi_duoc_gia_han():
    plan = {x['id']: (new, n) for x, new, n in D.extend_plan(ROWS, NOW)}
    assert set(plan) == {'a', 'b'}
    assert plan['a'] == ('2026-10-25T21:00:00+07:00', 1)
    assert plan['b'] == ('2026-10-23T21:00:00+07:00', 3)
    assert all(dt.datetime.fromisoformat(v[0]) > NOW for v in plan.values())


def test_is_self_loai_dau_hieu_truong():
    assert D.is_self(ROWS[0]) and D.is_self(ROWS[1])
    assert not D.is_self(ROWS[2]) and not D.is_self(ROWS[5]) and not D.is_self(ROWS[6])


def test_work_link_khong_ro_cho_lam_bai_thi_mo_trang_notion():
    x = row('z', 'Tự luyện', '2026-10-25T21:00:00+07:00', name='không có ở đâu cả xyz')
    assert D.work_link(x) == 'https://notion.example/z'
    assert D.work_link({**x, 'link': 'https://example.edu/bai-1'}) in ('https://example.edu/bai-1', 'https://notion.example/z')
