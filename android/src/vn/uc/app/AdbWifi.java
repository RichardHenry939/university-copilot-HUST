package vn.uc.app;

import android.content.ContentResolver;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.provider.Settings;

import java.util.HashSet;
import java.util.Set;

/** (chủ 07/11) Android TỰ TẮT "Gỡ lỗi không dây" mỗi khi điện thoại rời Wi-Fi (sang 5G, ra ngoài) -> về nhà UC trên laptop mất tay điều khiển.
 *  App tự bật lại công tắc đó khi điện thoại về lại Wi-Fi "nhà" (= Wi-Fi từng thấy Gỡ lỗi không dây bật).
 *  Cần quyền WRITE_SECURE_SETTINGS, laptop cấp MỘT lần: adb shell pm grant vn.uc.app android.permission.WRITE_SECURE_SETTINGS
 *  KHÔNG BAO GIỜ đụng adb_enabled (Gỡ lỗi USB): app ngân hàng chặn đúng công tắc đó. Không bật Tùy chọn nhà phát triển nếu chủ đã tắt.
 *  Đi tắt: nhận "Wi-Fi nhà" theo tên mạng (SSID) — cần quyền định vị (app đã xin cho đếm bước); không đọc được tên thì không làm gì.
 *  Wi-Fi khác cùng tên (vd mạng công cộng trùng tên) cũng được tính là nhà. */
final class AdbWifi {
    private static final String KEY = "adbwifi_home";

    static boolean granted(Context c) {
        return c.checkSelfPermission("android.permission.WRITE_SECURE_SETTINGS") == PackageManager.PERMISSION_GRANTED;
    }

    private static String ssid(Context c) {
        try {
            ConnectivityManager cm = c.getSystemService(ConnectivityManager.class);
            NetworkCapabilities nc = cm.getNetworkCapabilities(cm.getActiveNetwork());
            if (nc == null || !nc.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return null;
            WifiInfo wi = c.getApplicationContext().getSystemService(WifiManager.class).getConnectionInfo();
            String s = wi == null ? null : wi.getSSID();
            if (s == null || s.isEmpty() || s.contains("unknown ssid")) return null;
            return s.replace("\"", "");
        } catch (Exception e) { return null; }
    }

    /** Gọi định kỳ từ NotifyService. */
    static void tick(Context c) {
        try {
            ContentResolver cr = c.getContentResolver();
            String s = ssid(c);
            if (s == null) return;   // không ở Wi-Fi / không đọc được tên mạng
            SharedPreferences p = NotifyService.p(c);
            Set<String> home = new HashSet<>(p.getStringSet(KEY, new HashSet<>()));
            int on = Settings.Global.getInt(cr, "adb_wifi_enabled", 0);
            if (on == 1) {   // đang bật trên mạng này -> ghi nhớ là Wi-Fi nhà
                if (home.add(s)) p.edit().putStringSet(KEY, home).apply();
                return;
            }
            if (!home.contains(s) || !granted(c)) return;
            if (Settings.Global.getInt(cr, Settings.Global.DEVELOPMENT_SETTINGS_ENABLED, 0) != 1) return;   // chủ tắt hẳn Tùy chọn nhà phát triển -> tôn trọng
            Settings.Global.putInt(cr, "adb_wifi_enabled", 1);
            android.util.Log.i("UCADB", "bật lại Gỡ lỗi không dây trên Wi-Fi nhà");
        } catch (Exception e) {
            android.util.Log.w("UCADB", "tick " + e);
        }
    }
}
