package vn.uc.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/** (chủ 05/11) Thông báo của chính app University Copilot thay cho app ntfy.
 *  UC trên laptop vẫn đẩy tin lên kênh ntfy cũ (cả tin hẹn trước khi laptop ngủ — phone_sched); app này tự nghe kênh đó
 *  (luồng JSON của ntfy.sh) rồi hiện thông báo của mình: bấm vào mở đúng link (YouTube -> ReVanced), nút bấm gửi lệnh như ntfy.
 *  Chạy như dịch vụ nền có 1 thông báo thường trực im lặng (Android bắt buộc để giữ kết nối).
 *  Đi tắt: không có Firebase Cloud Messaging (build không Gradle) -> giữ 1 kết nối mở, giống app ntfy; tắt tối ưu pin cho app thì mới chắc nhận khi máy ngủ. */
public class NotifyService extends Service {
    static final String CH_ALERT = "uc_alert", CH_INFO = "uc_info", CH_SVC = "uc_service";
    private static final String REVANCED = "app.revanced.android.youtube";
    private volatile boolean run;

    static SharedPreferences p(Context c) { return c.getSharedPreferences("uc", Context.MODE_PRIVATE); }
    static String topic(Context c) { return p(c).getString("ntfy", ""); }
    static void setTopic(Context c, String t) { p(c).edit().putString("ntfy", t).apply(); }

    static void start(Context c) {
        if (topic(c).isEmpty() && Store.lan(c).isEmpty()) return;   // (05/11) chạy cả khi chỉ có đường về laptop (đếm bước iCTSV)
        try { c.startForegroundService(new Intent(c, NotifyService.class)); } catch (Exception e) { android.util.Log.w("UCNTF", "start " + e); }
    }

    static void channels(Context c) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CH_ALERT, "Nhắc gấp (hạn, buổi học, thi)", NotificationManager.IMPORTANCE_HIGH));
        nm.createNotificationChannel(new NotificationChannel(CH_INFO, "Nhắc thường", NotificationManager.IMPORTANCE_DEFAULT));
        NotificationChannel s = new NotificationChannel(CH_SVC, "Đang nghe thông báo (thường trực)", NotificationManager.IMPORTANCE_MIN);
        s.setShowBadge(false); nm.createNotificationChannel(s);
    }

    @Override public int onStartCommand(Intent i, int flags, int id) {
        channels(this);
        Notification n = new Notification.Builder(this, CH_SVC).setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("University Copilot đang nghe thông báo").setOngoing(true)
                .setContentIntent(PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE)).build();
        // (05/11) thêm loại "định vị" khi đã có quyền: ghi chặng đường lượt đi iCTSV lúc màn hình tắt
        boolean loc = checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(android.Manifest.permission.ACCESS_BACKGROUND_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED;
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE | (loc ? ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION : 0));
        else startForeground(1, n);
        if (!run) {
            run = true; new Thread(this::loop, "uc-ntfy").start();
            // (05/11) đếm bước theo lượt iCTSV (WalkWatch): luồng riêng, 20 s một lần
            WalkWatch w = new WalkWatch(this); w.start();
            new Thread(() -> { while (run) { w.poll(); try { Thread.sleep(20000); } catch (InterruptedException e) { return; } } }, "uc-walk").start();
        }
        return START_STICKY;
    }

    @Override public void onDestroy() { run = false; super.onDestroy(); }
    @Override public IBinder onBind(Intent i) { return null; }

    private void loop() {
        long wait = 5000;
        while (run) {
            String t = topic(this);
            if (t.isEmpty()) { try { Thread.sleep(60000); } catch (InterruptedException e) { return; } continue; }   // chưa có kênh: chỉ đếm bước
            String since = p(this).getString("ntfy_last", "");
            HttpURLConnection h = null;
            try {
                h = (HttpURLConnection) new URL("https://ntfy.sh/" + t + "/json?since=" + (since.isEmpty() ? "2m" : since)).openConnection();
                h.setConnectTimeout(20000); h.setReadTimeout(120000);   // ntfy gửi keepalive mỗi ~45 s
                BufferedReader r = new BufferedReader(new InputStreamReader(h.getInputStream(), "UTF-8"));
                wait = 5000; String line;
                while (run && (line = r.readLine()) != null) {
                    JSONObject m = new JSONObject(line);
                    if (!"message".equals(m.optString("event"))) continue;
                    String mid = m.optString("id");
                    if (mid.equals(p(this).getString("ntfy_last", ""))) continue;
                    p(this).edit().putString("ntfy_last", mid).apply();
                    show(this, m);
                }
            } catch (Exception e) {
                android.util.Log.w("UCNTF", "loop " + e);
            } finally { if (h != null) h.disconnect(); }
            try { Thread.sleep(wait); } catch (InterruptedException e) { return; }
            wait = Math.min(wait * 2, 60000);
        }
    }

    /** Intent mở một link: YouTube -> ReVanced (nếu có), còn lại để Android chọn app. */
    static Intent view(Context c, String url) {
        Uri u = Uri.parse(url); String h = u.getHost() == null ? "" : u.getHost();
        Intent i = new Intent(Intent.ACTION_VIEW, u).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (h.equals("youtu.be") || h.equals("youtube.com") || h.endsWith(".youtube.com")) {
            try { c.getPackageManager().getPackageInfo(REVANCED, 0); i.setPackage(REVANCED); } catch (Exception e) { /* chưa cài */ }
        }
        return i;
    }

    static void show(Context c, JSONObject m) {
        int nid = (m.optString("id").hashCode() & 0x7fffffff) | 1;
        int pr = m.optInt("priority", 3);
        String click = m.optString("click", "");
        Intent open = click.startsWith("http") ? view(c, click) : new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        String title = m.optString("title", ""), text = m.optString("message", "");
        Notification.Builder b = new Notification.Builder(c, pr >= 4 ? CH_ALERT : CH_INFO).setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(title.isEmpty() ? "University Copilot" : title).setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text)).setAutoCancel(true).setWhen(m.optLong("time", 0) * 1000).setShowWhen(true)
                .setContentIntent(PendingIntent.getActivity(c, nid, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        JSONArray acts = m.optJSONArray("actions");
        for (int k = 0; acts != null && k < Math.min(3, acts.length()); k++) {
            JSONObject a = acts.optJSONObject(k); if (a == null) continue;
            String kind = a.optString("action"), label = a.optString("label"), url = a.optString("url");
            PendingIntent pi;
            if ("view".equals(kind)) pi = PendingIntent.getActivity(c, nid + k + 1, view(c, url), PendingIntent.FLAG_IMMUTABLE);
            else if ("http".equals(kind)) pi = PendingIntent.getBroadcast(c, nid + k + 1, new Intent(c, Act.class)
                    .putExtra("url", url).putExtra("method", a.optString("method", "POST")).putExtra("body", a.optString("body", ""))
                    .putExtra("nid", nid).putExtra("clear", a.optBoolean("clear", false)), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            else continue;
            b.addAction(new Notification.Action.Builder(null, label, pi).build());
        }
        c.getSystemService(NotificationManager.class).notify(nid, b.build());
    }

    /** Nút "http" (như ntfy): gửi lệnh có chữ ký về kênh lệnh của UC; UC vẫn hỏi Xác nhận như trước. */
    public static class Act extends BroadcastReceiver {
        @Override public void onReceive(Context c, Intent i) {
            PendingResult pr = goAsync();
            new Thread(() -> {
                HttpURLConnection h = null;
                try {
                    String u = i.getStringExtra("url");
                    if (u == null || !u.startsWith("https://ntfy.sh/")) return;   // chỉ gửi về ntfy (kênh lệnh của UC)
                    h = (HttpURLConnection) new URL(u).openConnection();
                    h.setRequestMethod(i.getStringExtra("method")); h.setDoOutput(true); h.setConnectTimeout(15000); h.setReadTimeout(15000);
                    try (OutputStream o = h.getOutputStream()) { o.write(String.valueOf(i.getStringExtra("body")).getBytes("UTF-8")); }
                    android.util.Log.w("UCNTF", "act " + h.getResponseCode());
                    if (i.getBooleanExtra("clear", false)) c.getSystemService(NotificationManager.class).cancel(i.getIntExtra("nid", 0));
                } catch (Exception e) { android.util.Log.w("UCNTF", "act " + e); }
                finally { if (h != null) h.disconnect(); pr.finish(); }
            }).start();
        }
    }

    /** Bật máy / cập nhật app -> nghe lại. */
    public static class Boot extends BroadcastReceiver {
        @Override public void onReceive(Context c, Intent i) { start(c); }
    }
}
