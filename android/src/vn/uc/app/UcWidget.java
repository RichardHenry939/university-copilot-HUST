package vn.uc.app;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;
import java.util.TimeZone;

/** Widget 4x2 (04/11, chủ: "ít nhất phải có đồng hồ 24h và danh sách task rút gọn — giống widget desktop"):
 *  trái = đồng hồ 24 giờ cùng luật màu ui/widget.html; phải = giờ (TextClock, tự chạy) + dải tóm tắt + 3 việc + buổi học / thi tới.
 *  Mặt 24h + kim giờ là ảnh tĩnh: vẽ lại mỗi ~15 phút (báo thức không đánh thức máy) và khi chạm ↻; kim giờ lệch tối đa ~4° (15 phút).
 *  Kim phút + giây = AnalogClock của hệ thống đè lên (chạy thật từng giây; kim phút/giây 12h hay 24h như nhau). */
public class UcWidget extends AppWidgetProvider {
    static final String REFRESH = "vn.uc.app.REFRESH";
    static final java.util.Map<String, String> LOCK_NAMES = new java.util.HashMap<String, String>() {{
        put("default", "PhoneDefaultLock"); put("focus", "PhoneFocusLock"); put("nap", "PhoneNapLock"); put("night", "PhoneNightLock"); }};
    private static final TimeZone VN = TimeZone.getTimeZone("Asia/Ho_Chi_Minh");

    @Override public void onUpdate(Context c, AppWidgetManager m, int[] ids) { schedule(c, true); refresh(c, true); }

    @Override public void onDisabled(Context c) { schedule(c, false); }

    @Override public void onReceive(Context c, Intent i) {
        if (REFRESH.equals(i.getAction())) refresh(c, !i.getBooleanExtra("noFetch", false));
        else super.onReceive(c, i);
    }

    private static PendingIntent tickIntent(Context c) {
        return PendingIntent.getBroadcast(c, 2, new Intent(REFRESH).setClass(c, UcWidget.class),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    /** Vẽ lại ~15 phút/lần bằng báo thức RTC (không đánh thức máy: màn tắt thì chờ tới lúc mở máy). */
    private static void schedule(Context c, boolean on) {
        AlarmManager am = c.getSystemService(AlarmManager.class);
        if (am == null) return;
        am.cancel(tickIntent(c));
        if (on) am.setInexactRepeating(AlarmManager.RTC, System.currentTimeMillis() + AlarmManager.INTERVAL_FIFTEEN_MINUTES,
                AlarmManager.INTERVAL_FIFTEEN_MINUTES, tickIntent(c));
    }

    private void refresh(Context c, boolean fetch) {
        final PendingResult pr = goAsync();
        new Thread(() -> {
            try {
                String j = fetch ? Store.fetch(c) : null;
                if (j == null) j = Store.cached(c);
                AppWidgetManager m = AppWidgetManager.getInstance(c);
                m.updateAppWidget(new ComponentName(c, UcWidget.class), views(c, j));
            } finally { pr.finish(); }
        }).start();
    }

    private static String hm(String iso) { return iso != null && iso.length() >= 16 ? iso.substring(11, 16) : ""; }

    private static String when(String iso, String today) {
        if (iso == null || iso.length() < 10) return "";
        if (iso.startsWith(today)) return hm(iso);
        return iso.substring(8, 10) + "/" + iso.substring(5, 7);
    }

    private static String shortName(String t) {
        return t == null ? "" : t.replaceAll(" · (LT\\+BT|LT|BT|Thực nghiệm|Online|Offline|Teams đổi lịch)\\b", "")
                .replace("Ôn thi định kỳ hằng ngày môn ", "Ôn thi ");
    }

    private static void span(SpannableStringBuilder b, String s, int color, boolean bold) {
        int st = b.length(); b.append(s);
        if (color != 0) b.setSpan(new ForegroundColorSpan(color), st, b.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        if (bold) b.setSpan(new StyleSpan(Typeface.BOLD), st, b.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
    }

    static RemoteViews views(Context c, String json) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget);
        Calendar now = Calendar.getInstance(VN);
        String[] dows = {"Chủ nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"};
        v.setTextViewText(R.id.dow, dows[now.get(Calendar.DAY_OF_WEEK) - 1] + ", " + now.get(Calendar.DAY_OF_MONTH) + "/" + (now.get(Calendar.MONTH) + 1));
        SimpleDateFormat d = new SimpleDateFormat("yyyy-MM-dd", Locale.US); d.setTimeZone(VN);
        String today = d.format(now.getTime());
        int[] lines = {R.id.l1, R.id.l2, R.id.l3};
        JSONObject w = null;
        try {
            if (json == null || json.isEmpty()) throw new Exception("trong");
            JSONObject o = new JSONObject(json);
            w = o.optJSONObject("widget");
            if (w == null) w = new JSONObject();
            JSONArray viec = w.optJSONArray("viec");
            int left = 0;
            for (int k = 0; viec != null && k < viec.length(); k++) {
                String l = viec.getJSONObject(k).optString("loai");
                if ("on_thi".equals(l) || "han_hom_nay".equals(l)) left++;
            }
            for (int k = 0; k < lines.length; k++) {
                if (viec != null && k < viec.length()) {
                    JSONObject x = viec.getJSONObject(k);
                    boolean on = "on_thi".equals(x.optString("loai")), hot = on || "han_hom_nay".equals(x.optString("loai"));
                    SpannableStringBuilder b = new SpannableStringBuilder();
                    span(b, (on ? "Ôn" : when(x.optString("han"), today)) + "  ", c.getColor(on ? R.color.amber : hot ? R.color.red : R.color.ink2), true);
                    span(b, shortName(x.optString("ten")), on ? c.getColor(R.color.amber) : 0, on);
                    v.setTextViewText(lines[k], b);
                } else v.setTextViewText(lines[k], k == 0 ? "Hôm nay không có việc có hạn." : "");
            }
            JSONArray lich = w.optJSONArray("lich");
            if (lich != null && lich.length() > 0) {
                JSONObject e = lich.getJSONObject(0);
                String loc = e.optString("dia_diem", "");
                v.setTextViewText(R.id.next, ("Exam".equals(e.optString("loai")) ? "Thi " : "Học ")
                        + when(e.optString("bat_dau"), today) + "  " + shortName(e.optString("ten")) + (loc.isEmpty() ? "" : " · " + loc));
            } else v.setTextViewText(R.id.next, "Không có buổi học sắp tới.");
            // dải tóm tắt như ui/widget.html: phút tập trung (0 đỏ · >0 hổ phách · >30 xanh biển · >60 xanh lá) · ví · việc còn lại · Fitness
            JSONObject t = w.optJSONObject("tap_trung");
            int fm = t == null ? 0 : t.optInt("phut_hom_nay", 0);
            int col = fm == 0 ? R.color.red : fm <= 30 ? R.color.amber : fm <= 60 ? R.color.blue : R.color.green;
            SpannableStringBuilder s = new SpannableStringBuilder();
            span(s, fm == 0 ? "Chưa tập trung" : (fm >= 60 ? fm / 60 + "h" + String.format(Locale.US, "%02d", fm % 60) : fm + "p") + " tập trung", c.getColor(col), true);
            if (t != null && t.has("so_du")) span(s, " · Ví " + t.optInt("so_du") + "p", 0, false);
            span(s, left > 0 ? " · Còn " + left + " việc" : " · Hết việc", left > 0 ? 0 : c.getColor(R.color.green), false);
            JSONObject st = w.optJSONObject("buoc");
            if (st != null) {
                span(s, " · ", 0, false); span(s, "Fitness", c.getColor(R.color.green), true);
                span(s, st.optBoolean("du") ? " đủ bước" : " " + st.optInt("buoc") + "/" + st.optInt("muc_tieu"), 0, false);
            }
            v.setTextViewText(R.id.sum, s);
            String at = o.optString("lan_cuoi", "");
            v.setTextViewText(R.id.upd, (o.optBoolean("online") ? "↻ " : "⚠ ") + hm(at));
        } catch (Exception e) {
            v.setTextViewText(R.id.l1, Store.url(c).isEmpty() ? "Mở app UC để dán đường dẫn." : "Chưa tải được dữ liệu.");
            v.setTextViewText(R.id.l2, ""); v.setTextViewText(R.id.l3, ""); v.setTextViewText(R.id.next, "");
            v.setTextViewText(R.id.sum, ""); v.setTextViewText(R.id.upd, "↻");
        }
        v.setImageViewBitmap(R.id.clock, clock(c, w, now));
        int fl = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        v.setOnClickPendingIntent(R.id.root, PendingIntent.getActivity(c, 0, new Intent(c, MainActivity.class), fl));
        v.setOnClickPendingIntent(R.id.upd, PendingIntent.getBroadcast(c, 1, new Intent(REFRESH).setClass(c, UcWidget.class), fl));
        return v;
    }

    // ---- đồng hồ 24 giờ: cùng lớp + màu với ui/widget.html (khung 200x200 nhân 1.5) ----
    private static final float K = 1.5f, C = 100 * K;

    private static float hh(String s) {   // "HH:MM" -> giờ thập phân
        try { return Integer.parseInt(s.substring(0, 2)) + Integer.parseInt(s.substring(3, 5)) / 60f; } catch (Exception e) { return -1; }
    }

    private static void sector(Canvas cv, float h0, float h1, int argb, float cap) {
        if (cap >= 0) h1 = Math.min(h1, cap);
        if (h0 < 0 || h1 - h0 < .02f) return;
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG); p.setColor(argb);
        float r = 94 * K;
        cv.drawArc(new RectF(C - r, C - r, C + r, C + r), h0 * 15 - 90, (h1 - h0) * 15, true, p);
    }

    private static void spans(Canvas cv, JSONArray a, int argb, float cap) {
        for (int i = 0; a != null && i < a.length(); i++) {
            JSONArray x = a.optJSONArray(i);
            if (x != null && x.length() == 2) sector(cv, hh(x.optString(0)), hh(x.optString(1)), argb, cap);
        }
    }

    private static int a(double alpha, int rgb) { return ((int) Math.round(alpha * 255) << 24) | (rgb & 0xFFFFFF); }

    static Bitmap clock(Context c, JSONObject w, Calendar now) {
        boolean dark = (c.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        int ink = c.getColor(R.color.ink), ink2 = c.getColor(R.color.ink2);
        Bitmap bm = Bitmap.createBitmap((int) (2 * C), (int) (2 * C), Bitmap.Config.ARGB_8888);
        Canvas cv = new Canvas(bm);
        float nowH = now.get(Calendar.HOUR_OF_DAY) + now.get(Calendar.MINUTE) / 60f;
        Paint face = new Paint(Paint.ANTI_ALIAS_FLAG);
        face.setColor(dark ? a(.9, 0x1A2333) : a(.72, 0xFFFFFF)); cv.drawCircle(C, C, 96 * K, face);
        face.setStyle(Paint.Style.STROKE); face.setStrokeWidth(2.5f * K); face.setColor(ink); cv.drawCircle(C, C, 96 * K, face);
        JSONObject dh = w == null ? null : w.optJSONObject("dong_ho"), tt = w == null ? null : w.optJSONObject("tap_trung");
        // thứ tự lớp = luật tranh chấp: xám lãng phí < tím ăn < xanh lá tập trung < vàng ngủ < đỏ thể dục < xanh biển học
        if (nowH > 6) sector(cv, 6, Math.min(nowH, 22), a(.62, 0x2F343B), -1);
        boolean camp = dh != null && dh.optBoolean("camp");
        float[][] meals = {{7.5f, 8}, {12, 13}, camp ? new float[]{17.5f, 18.5f} : new float[]{19, 20}};
        for (float[] m : meals) sector(cv, m[0], m[1], a(.6, 0x8E44AD), -1);
        if (tt != null) spans(cv, tt.optJSONArray("khoang"), a(.85, 0x2F7D4F), nowH);
        if (dh != null) spans(cv, dh.optJSONArray("ngu_trua"), a(.55, 0xF6C945), -1);
        sector(cv, 22, 24, a(.55, 0xF6C945), -1); sector(cv, 0, 6, a(.55, 0xF6C945), -1);
        if (dh != null) spans(cv, dh.optJSONArray("the_duc"), a(.75, 0xD62828), -1);
        if (dh != null) spans(cv, dh.optJSONArray("hoc"), a(.75, 0x1F6FD1), nowH);
        Paint tk = new Paint(Paint.ANTI_ALIAS_FLAG);
        for (int i = 0; i < 96; i++) {
            boolean big = i % 4 == 0;
            double ang = Math.toRadians(i * 3.75 - 90);
            float r0 = (big ? 82 : 87) * K, r1 = 92 * K;
            tk.setColor(big ? ink : ink2); tk.setStrokeWidth((big ? 2.2f : 1f) * K);
            cv.drawLine(C + r0 * (float) Math.cos(ang), C + r0 * (float) Math.sin(ang), C + r1 * (float) Math.cos(ang), C + r1 * (float) Math.sin(ang), tk);
        }
        Paint num = new Paint(Paint.ANTI_ALIAS_FLAG);
        num.setColor(ink); num.setTextAlign(Paint.Align.CENTER);
        try { num.setTypeface(c.getResources().getFont(R.font.bricolage_heavy)); } catch (Exception e) { num.setTypeface(Typeface.DEFAULT_BOLD); }   // font như widget desktop
        for (int h = 0; h < 24; h++) {
            num.setTextSize((h % 6 == 0 ? 14 : 11) * K);
            double ang = Math.toRadians(h * 15 - 90);
            float x = C + 71 * K * (float) Math.cos(ang), y = C + 71 * K * (float) Math.sin(ang);
            cv.drawText(String.valueOf(h), x, y - (num.descent() + num.ascent()) / 2, num);
        }
        Paint hand = new Paint(Paint.ANTI_ALIAS_FLAG);
        hand.setColor(ink); hand.setStrokeWidth(5 * K); hand.setStrokeCap(Paint.Cap.ROUND);
        double ang = Math.toRadians(nowH * 15 - 90);
        cv.drawLine(C, C, C + 52 * K * (float) Math.cos(ang), C + 52 * K * (float) Math.sin(ang), hand);   // kim giờ 24h (.hh dài 52); phút + giây + trục: AnalogClock
        return bm;
    }
}
