package vn.uc.app;

import android.content.Context;
import android.content.SharedPreferences;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/** Đường dẫn connector (chủ tự dán, có khoá chỉ đọc) + bản dữ liệu cuối cùng tải được (để widget / app hiện khi mất mạng). */
final class Store {
    private static SharedPreferences p(Context c) { return c.getSharedPreferences("uc", Context.MODE_PRIVATE); }

    static String url(Context c) { return p(c).getString("url", ""); }
    static void setUrl(Context c, String u) { p(c).edit().putString("url", u == null ? "" : u.trim()).apply(); }
    /** (v1.00.60) http://100.x:8320/?k=<khoá điện thoại> — mở chính UC web trên laptop qua Tailscale. */
    static String lan(Context c) { return p(c).getString("lan", ""); }
    static void setLan(Context c, String u) { p(c).edit().putString("lan", u == null ? "" : u.trim()).apply(); }
    static String cached(Context c) { return p(c).getString("json", ""); }
    static long cachedAt(Context c) { return p(c).getLong("at", 0); }

    /** Tải dữ liệu mới (chạy ở luồng nền). Lỗi -> null, giữ bản cũ. */
    static String fetch(Context c) {
        String u = url(c);
        if (!u.startsWith("https://")) return null;
        HttpURLConnection h = null;
        try {
            h = (HttpURLConnection) new URL(u).openConnection();
            h.setConnectTimeout(15000); h.setReadTimeout(20000);
            if (h.getResponseCode() != 200) return null;
            InputStream in = h.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] b = new byte[8192]; int n;
            while ((n = in.read(b)) > 0) out.write(b, 0, n);
            String s = out.toString("UTF-8");
            p(c).edit().putString("json", s).putLong("at", System.currentTimeMillis()).apply();
            return s;
        } catch (Exception e) {
            return null;
        } finally {
            if (h != null) h.disconnect();
        }
    }
}
