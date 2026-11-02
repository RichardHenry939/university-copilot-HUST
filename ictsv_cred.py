# -*- coding: utf-8 -*-
"""(v1.00.49) Cất / xoá tài khoản app iCTSV (com.bk.ctsv) cho UC tự đăng nhập lại khi hết phiên.

iCTSV dùng mật khẩu RIÊNG, khác tài khoản trường (eHUST dùng lại tài khoản trường trong school_cred.py).
Lưu vào Windows Credential Manager, mục "uc-ictsv" (mã hoá theo tài khoản Windows của bạn; UC giải được để
tự đăng nhập, nên KHÔNG phải mã băm — mã băm một chiều thì không đăng nhập được).
Chính BẠN nhập — mật khẩu gõ vào ô ẩn, không hiện ra màn hình, không ghi ra file, không gửi đi đâu.

  python ictsv_cred.py            nhập / thay tài khoản
  python ictsv_cred.py --delete   xoá
  python ictsv_cred.py --status   chỉ cho biết đã có hay chưa (không in tài khoản, mật khẩu)
  python ictsv_cred.py --verify   gõ lại để so với bản đã cất (chỉ báo khớp / không khớp)
"""
import getpass, sys
from pathlib import Path
import keyring

SERVICE = "uc-ictsv"
LOCK = Path(__file__).resolve().parent / "school" / "ictsv_login.lock"   # bị từ chối 1 lần -> khoá tự đăng nhập, tránh khoá tài khoản


def get():
    """-> (tài khoản, mật khẩu) hoặc (None, None). Chỉ code UC gọi, trong bộ nhớ."""
    user = keyring.get_password(SERVICE, "__user__")
    return (user, keyring.get_password(SERVICE, user)) if user else (None, None)


def main():
    if "--status" in sys.argv:
        u, p = get()
        print("Đã cất tài khoản iCTSV." if u and p else "Chưa có tài khoản iCTSV.")
        if LOCK.exists(): print("Đang KHOÁ tự đăng nhập iCTSV (lần trước bị từ chối) — chạy lại lệnh nhập để mở khoá.")
        return
    if "--verify" in sys.argv:   # bạn gõ lại -> so với bản đã cất, chỉ báo khớp / không khớp (không in gì đã cất)
        import hmac
        u, p = get()
        if not (u and p): print("Chưa có tài khoản iCTSV để so."); return
        u2 = input("Gõ lại tài khoản iCTSV: ").strip()
        p2 = getpass.getpass("Gõ lại mật khẩu iCTSV (không hiện chữ): ")
        ok_u, ok_p = hmac.compare_digest(u2.encode(), u.encode()), hmac.compare_digest(p2.encode(), p.encode())
        print(f"Tài khoản: {'KHỚP' if ok_u else 'KHÔNG khớp'} · Mật khẩu: {'KHỚP' if ok_p else 'KHÔNG khớp'}")
        if not (ok_u and ok_p): print("Chạy lại `python ictsv_cred.py` để nhập lại cho đúng.")
        return
    if "--delete" in sys.argv:
        u, _ = get()
        if u:
            try: keyring.delete_password(SERVICE, u)
            except Exception: pass
        try: keyring.delete_password(SERVICE, "__user__")
        except Exception: pass
        print("Đã xoá tài khoản iCTSV khỏi Credential Manager.")
        return
    user = input("Tài khoản iCTSV: ").strip()
    pw = getpass.getpass("Mật khẩu iCTSV (gõ không hiện chữ): ")
    if not user or not pw:
        print("Thiếu tài khoản hoặc mật khẩu, không lưu."); return
    keyring.set_password(SERVICE, "__user__", user)
    keyring.set_password(SERVICE, user, pw)
    LOCK.unlink(missing_ok=True)
    print("Đã cất tài khoản iCTSV (mã hoá theo tài khoản Windows). Đã mở khoá tự đăng nhập.")


if __name__ == "__main__":
    main()
