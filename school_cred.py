# -*- coding: utf-8 -*-
"""Cất / xoá tài khoản trường cho bộ đồng bộ (Claude 2026-10-03).

Lưu vào Windows Credential Manager (mã hoá theo tài khoản Windows của bạn), mục "uc-school-sync".
Chính BẠN nhập — mật khẩu gõ vào ô ẩn, không hiện ra màn hình, không ghi ra file, không gửi đi đâu.

  python school_cred.py            nhập / thay tài khoản
  python school_cred.py --delete   xoá
  python school_cred.py --status   chỉ cho biết đã có hay chưa (không in mật khẩu)
"""
import getpass, sys
from pathlib import Path
import keyring

SERVICE = "uc-school-sync"
LOCK = Path(__file__).resolve().parent / "school" / "login.lock"


def get():
    """-> (email, mật khẩu) hoặc (None, None)."""
    email = keyring.get_password(SERVICE, "__email__")
    return (email, keyring.get_password(SERVICE, email)) if email else (None, None)


def main():
    if "--status" in sys.argv:
        e, p = get()
        print(f"Đã có tài khoản {e} (mật khẩu đã cất)." if e and p else "Chưa có tài khoản.")
        if LOCK.exists(): print("Đang KHOÁ tự đăng nhập (lần trước bị từ chối) — chạy lại lệnh nhập để mở khoá.")
        return
    if "--delete" in sys.argv:
        e, _ = get()
        if e:
            keyring.delete_password(SERVICE, e); keyring.delete_password(SERVICE, "__email__")
        print("Đã xoá tài khoản khỏi Credential Manager.")
        return
    e = input("Email Office 365 của trường (…@sis.hust.edu.vn): ").strip()
    if not e.lower().endswith("@sis.hust.edu.vn"):
        print("Chỉ nhận email @sis.hust.edu.vn."); return
    p = getpass.getpass("Mật khẩu (gõ sẽ không hiện ra): ")
    if not p:
        print("Chưa nhập mật khẩu."); return
    old, _ = get()
    if old and old != e: keyring.delete_password(SERVICE, old)
    keyring.set_password(SERVICE, "__email__", e)
    keyring.set_password(SERVICE, e, p)
    if LOCK.exists(): LOCK.unlink()
    print("Đã cất vào Windows Credential Manager. Bộ đồng bộ sẽ tự đăng nhập lại khi trường hết phiên.")


if __name__ == "__main__":
    main()
