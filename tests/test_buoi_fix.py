# -*- coding: utf-8 -*-
"""(03/11) Bộ trích giờ đọc chữ sáng/trưa/chiều/tối/đêm: "tối mai ... 8h30" phải ra 20:30, không phải 08:30."""
from mail_events import _buoi_fix as F

TEAMS = "Các em tối mai online nhé.\n Thời gian từ 8h30 đến 10h (có thể kết thúc sớm)."


def test_toi_dung_truoc_xuong_dong():   # đúng bài Teams 02/11 gây lỗi
    assert F('08:30', TEAMS) == '20:30'


def test_chu_ngay_sau_gio():
    assert F('07:00', 'Họp lớp lúc 7h tối thứ Năm') == '19:00'
    assert F('02:30', 'Thi lúc 2h30 chiều') == '14:30'


def test_sang_giu_nguyen():
    assert F('08:30', 'Sáng mai học từ 8h30 ở D9') == '08:30'


def test_trua_va_dem():
    assert F('01:00', 'Nghỉ trưa đến 1h trưa') == '13:00'
    assert F('11:00', 'Buổi trưa 11h họp') == '11:00'
    assert F('10:00', 'Hạn nộp 10h đêm nay') == '22:00'


def test_khong_co_buoi_hoac_da_24h():
    assert F('08:30', 'Học từ 8:30 phòng D5') == '08:30'
    assert F('20:30', TEAMS) == '20:30'
    assert F(None, TEAMS) is None


def test_chu_gan_nhat_thang():   # sáng 9h, tối 8h: mỗi giờ lấy chữ gần nó
    t = 'Sáng 9h họp lớp. Tối 8h học bù.'
    assert F('09:00', t) == '09:00'
    assert F('08:00', t) == '20:00'
