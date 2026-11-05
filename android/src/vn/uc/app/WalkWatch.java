package vn.uc.app;

import android.app.usage.UsageEvents;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/** (chủ 05/11) Đếm bước ĐÚNG các lượt bạn bấm "bắt đầu" trong iCTSV, ngay trên điện thoại thật (không máy ảo, không trợ năng).
 *  - iCTSV bấm bắt đầu = nó bật dịch vụ nền loại sức khoẻ; bấm kết thúc = tắt. App đọc 2 sự kiện đó qua "Truy cập dữ liệu sử dụng".
 *  - Số bước = hiệu số cảm biến bước chân của máy (cùng nguồn iCTSV dùng) giữa lúc bật và lúc tắt.
 *  - Mỗi lượt + nhịp "còn sống" gửi về UC trên laptop (POST /api/walk-phone qua Tailscale, cookie khoá điện thoại).
 *  Đi tắt: cảm biến đếm từ lúc bật máy -> khởi động lại điện thoại giữa lượt thì lượt đó tính từ 0 (bỏ phần trước khi tắt máy). */
final class WalkWatch implements SensorEventListener, android.location.LocationListener {
    static final String PKG = "com.bk.ctsv";
    private final Context c;
    // (chủ 05/11) chặng đường của lượt: định vị đọc CÙNG LÚC với iCTSV (chỉ trong lượt), điểm cách nhau >= 5 m, tối đa 3000 điểm
    private final java.util.List<double[]> route = new java.util.ArrayList<>();
    private boolean gpsOn;
    private volatile float counter = -1;   // giá trị cảm biến gần nhất (bước từ lúc bật máy)
    private long lastQuery, lastBeat;

    WalkWatch(Context c) { this.c = c; }

    private SharedPreferences p() { return c.getSharedPreferences("uc_walk", Context.MODE_PRIVATE); }

    void start() {
        try {
            SensorManager sm = c.getSystemService(SensorManager.class);
            Sensor s = sm.getDefaultSensor(Sensor.TYPE_STEP_COUNTER);
            if (s != null) sm.registerListener(this, s, SensorManager.SENSOR_DELAY_NORMAL, 60_000_000);   // gom tối đa 60 s
            else android.util.Log.w("UCWALK", "may khong co cam bien buoc");
        } catch (Exception e) { android.util.Log.w("UCWALK", "sensor " + e); }
        lastQuery = p().getLong("q", System.currentTimeMillis() - 3600_000L);
        if (p().getLong("run_start", 0) > 0) gps(true);   // app chạy lại giữa lượt: ghi tiếp phần còn lại
    }

    @Override public void onLocationChanged(android.location.Location l) {
        synchronized (route) {
            if (route.size() >= 3000) return;
            if (!route.isEmpty()) {
                double[] q = route.get(route.size() - 1); float[] d = new float[1];
                android.location.Location.distanceBetween(q[0], q[1], l.getLatitude(), l.getLongitude(), d);
                if (d[0] < 5) return;
            }
            route.add(new double[]{l.getLatitude(), l.getLongitude(), l.getTime() / 1000.0});
        }
    }

    private void gps(boolean on) {
        if (on == gpsOn) return;
        android.location.LocationManager lm = c.getSystemService(android.location.LocationManager.class);
        try {
            if (on) {
                synchronized (route) { route.clear(); }
                lm.requestLocationUpdates(android.location.LocationManager.GPS_PROVIDER, 3000, 3, this, c.getMainLooper());
                android.util.Log.w("UCWALK", "bat dinh vi");
            } else { lm.removeUpdates(this); android.util.Log.w("UCWALK", "tat dinh vi, " + route.size() + " diem"); }
            gpsOn = on;
        } catch (SecurityException e) { android.util.Log.w("UCWALK", "chua co quyen dinh vi"); }
        catch (Exception e) { android.util.Log.w("UCWALK", "gps " + e); }
    }

    private JSONArray routeJson() {
        JSONArray a = new JSONArray();
        synchronized (route) {
            for (double[] q : route) {
                try { a.put(new JSONArray().put(Math.round(q[0] * 1e6) / 1e6).put(Math.round(q[1] * 1e6) / 1e6).put((long) q[2])); }
                catch (Exception e) { /* bỏ điểm hỏng */ }
            }
        }
        return a;
    }

    @Override public void onSensorChanged(SensorEvent e) { counter = e.values[0]; }
    @Override public void onAccuracyChanged(Sensor s, int a) {}

    /** Gọi định kỳ (mỗi ~20 s) từ luồng của NotifyService. */
    void poll() {
        long now = System.currentTimeMillis();
        try {
            UsageStatsManager um = c.getSystemService(UsageStatsManager.class);
            UsageEvents ev = um.queryEvents(lastQuery, now);
            UsageEvents.Event e = new UsageEvents.Event();
            while (ev.hasNextEvent()) {
                ev.getNextEvent(e);
                int t = e.getEventType();
                if (!PKG.equals(e.getPackageName())) {   // chẩn đoán: thấy được dịch vụ nền của app khác không
                    if (t == UsageEvents.Event.FOREGROUND_SERVICE_START || t == UsageEvents.Event.FOREGROUND_SERVICE_STOP)
                        android.util.Log.w("UCWALK", "fgs " + t + " " + e.getPackageName());
                    continue;
                }
                if (t == UsageEvents.Event.FOREGROUND_SERVICE_START) onStart(e.getTimeStamp());
                else if (t == UsageEvents.Event.FOREGROUND_SERVICE_STOP) onStop(e.getTimeStamp());
            }
            lastQuery = now; p().edit().putLong("q", now).apply();
        } catch (Exception ex) { android.util.Log.w("UCWALK", "usage " + ex); }
        if (now - lastBeat > 600_000L || !p().getString("pending", "[]").equals("[]")) { lastBeat = now; send(); }
        lateTick(now);
    }

    // ---- (chủ 05/11) CHỐNG MUỘN: 15 phút trước buổi học trực tiếp, mỗi phút đo vị trí (mức tiết kiệm pin) và so NGAY TRÊN MÁY.
    // Chỉ gửi về UC 2 cờ: khác chỗ so với phút trước (> 100 m) / đã tới toà của buổi học (<= bán kính). Toạ độ không rời điện thoại.
    private long lastLate; private String lateId; private double[] lateLast;

    private void lateTick(long now) {
        if (now - lastLate < 55_000L) return;
        lastLate = now;
        try {
            String plan = http("GET", "/api/late-plan", null);
            if (plan == null) return;
            JSONObject j = new JSONObject(plan);
            if (j.isNull("id") || j.optBoolean("done")) { lateId = null; lateLast = null; return; }
            String id = j.getString("id");
            if (!id.equals(lateId)) { lateId = id; lateLast = null; }
            android.location.Location l = here();
            if (l == null) { android.util.Log.w("UCWALK", "chong muon: khong lay duoc vi tri"); return; }
            float[] d = new float[1];
            boolean moved = false;
            if (lateLast != null) { android.location.Location.distanceBetween(lateLast[0], lateLast[1], l.getLatitude(), l.getLongitude(), d); moved = d[0] > 100; }
            boolean at = false;
            JSONObject t = j.optJSONObject("target");
            if (t != null) { android.location.Location.distanceBetween(t.getDouble("lat"), t.getDouble("lon"), l.getLatitude(), l.getLongitude(), d); at = d[0] <= t.optDouble("r", 80); }
            lateLast = new double[]{l.getLatitude(), l.getLongitude()};   // chỉ giữ trong bộ nhớ, để so với phút sau
            http("POST", "/api/late-check", new JSONObject().put("id", id).put("moved", moved).put("at", at).put("left", j.optInt("left")).toString());
            android.util.Log.w("UCWALK", "chong muon: khac cho=" + moved + " toi toa=" + at);
        } catch (Exception e) { android.util.Log.w("UCWALK", "chong muon " + e); }
    }

    /** Một lần đo vị trí (mạng / Wi-Fi trước, tiết kiệm pin), chờ tối đa 25 s. */
    private android.location.Location here() {
        android.location.LocationManager lm = c.getSystemService(android.location.LocationManager.class);
        String prov = lm.isProviderEnabled(android.location.LocationManager.NETWORK_PROVIDER) ? android.location.LocationManager.NETWORK_PROVIDER
                : android.location.LocationManager.GPS_PROVIDER;
        final android.location.Location[] out = new android.location.Location[1];
        java.util.concurrent.CountDownLatch done = new java.util.concurrent.CountDownLatch(1);
        try {
            lm.getCurrentLocation(prov, null, java.util.concurrent.Executors.newSingleThreadExecutor(), loc -> { out[0] = loc; done.countDown(); });
            done.await(25, java.util.concurrent.TimeUnit.SECONDS);
        } catch (SecurityException e) { android.util.Log.w("UCWALK", "chua co quyen dinh vi"); }
        catch (Exception e) { android.util.Log.w("UCWALK", "here " + e); }
        return out[0];
    }

    /** Gọi UC trên laptop (Tailscale, cookie khoá điện thoại). -> nội dung trả về hoặc null. */
    private String http(String method, String path, String body) {
        String lan = Store.lan(c); int q = lan.indexOf("/?k="); if (q < 0) return null;
        HttpURLConnection h = null;
        try {
            h = (HttpURLConnection) new URL(lan.substring(0, q) + path).openConnection();
            h.setRequestMethod(method); h.setConnectTimeout(15000); h.setReadTimeout(20000);
            h.setRequestProperty("Cookie", "uc_k=" + lan.substring(q + 4));
            if (body != null) {
                h.setDoOutput(true); h.setRequestProperty("Content-Type", "application/json");
                try (OutputStream o = h.getOutputStream()) { o.write(body.getBytes("UTF-8")); }
            }
            if (h.getResponseCode() != 200) return null;
            java.io.InputStream in = h.getInputStream(); java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream();
            byte[] b = new byte[4096]; int n; while ((n = in.read(b)) > 0) bo.write(b, 0, n);
            return bo.toString("UTF-8");
        } catch (Exception e) { android.util.Log.w("UCWALK", "http " + path + " " + e); return null; }
        finally { if (h != null) h.disconnect(); }
    }

    private void onStart(long ts) {
        if (p().getLong("run_start", 0) > 0) return;   // đã đang trong lượt
        p().edit().putLong("run_start", ts).putFloat("run_c0", counter).apply();
        android.util.Log.w("UCWALK", "bat dau luot " + ts + " c0=" + counter);
        gps(true);
        send();
    }

    private void onStop(long ts) {
        long st = p().getLong("run_start", 0); if (st == 0) return;
        float c0 = p().getFloat("run_c0", -1);
        long steps = (c0 >= 0 && counter >= c0) ? Math.round(counter - c0) : (counter >= 0 && c0 >= 0 ? Math.round(counter) : -1);
        try {
            JSONArray pend = new JSONArray(p().getString("pending", "[]"));
            gps(false);
            pend.put(new JSONObject().put("id", Long.toString(st)).put("start", st).put("end", ts).put("steps", steps).put("route", routeJson()));
            p().edit().putString("pending", pend.toString()).putLong("run_start", 0).apply();
        } catch (Exception ex) { android.util.Log.w("UCWALK", "save " + ex); }
        android.util.Log.w("UCWALK", "ket thuc luot " + ts + " buoc=" + steps);
        send();
    }

    /** Gửi các lượt chưa gửi + trạng thái hiện tại. Lỗi mạng -> giữ lại, lần sau gửi tiếp. */
    private void send() {
        String lan = Store.lan(c);   // http://100.x:8320/?k=<khoá>
        int q = lan.indexOf("/?k="); if (q < 0) return;
        String base = lan.substring(0, q), key = lan.substring(q + 4);
        HttpURLConnection h = null;
        try {
            String pend = p().getString("pending", "[]");
            long st = p().getLong("run_start", 0);
            JSONObject b = new JSONObject().put("runs", new JSONArray(pend)).put("at", System.currentTimeMillis())
                    .put("active", st > 0 ? new JSONObject().put("start", st) : JSONObject.NULL).put("sensor", counter >= 0);
            h = (HttpURLConnection) new URL(base + "/api/walk-phone").openConnection();
            h.setRequestMethod("POST"); h.setDoOutput(true); h.setConnectTimeout(15000); h.setReadTimeout(20000);
            h.setRequestProperty("Content-Type", "application/json"); h.setRequestProperty("Cookie", "uc_k=" + key);
            try (OutputStream o = h.getOutputStream()) { o.write(b.toString().getBytes("UTF-8")); }
            if (h.getResponseCode() == 200 && !pend.equals("[]")) {
                JSONArray left = new JSONArray(p().getString("pending", "[]")), sent = new JSONArray(pend), keep = new JSONArray();
                for (int i = 0; i < left.length(); i++) {
                    boolean done = false;
                    for (int j = 0; j < sent.length(); j++) if (left.getJSONObject(i).getString("id").equals(sent.getJSONObject(j).getString("id"))) done = true;
                    if (!done) keep.put(left.get(i));
                }
                p().edit().putString("pending", keep.toString()).apply();
            }
        } catch (Exception ex) { android.util.Log.w("UCWALK", "send " + ex); }
        finally { if (h != null) h.disconnect(); }
    }
}
