package vn.uc.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

/** App UC bản điện thoại.
 *  Mở ra là hiện NGAY bản chỉ-xem (assets/app.html, dữ liệu connector Firebase); cùng lúc tải CHÍNH UC web trên laptop qua
 *  Tailscale ở lớp dưới, tải xong mới chuyển sang (giống hệt bản máy, bấm được tập trung / hạn / Fitness).
 *  (04/11) Tailscale đang đi vòng qua máy trung gian (~600 ms/lượt): UC web cần 10–30 s, nên không chờ trên màn trắng nữa. */
public class MainActivity extends Activity {
    private static final String OFFLINE = "file:///android_asset/app.html";
    private WebView view, laptop;
    private boolean onLaptop;

    private static final String REVANCED = "app.revanced.android.youtube";

    private WebView make() {
        WebView w = new WebView(this);
        WebSettings s = w.getSettings();
        s.setJavaScriptEnabled(true);
        s.setAllowFileAccess(false);
        s.setDomStorageEnabled(true);
        return w;
    }

    /** (chủ 04/11) Link ra ngoài UC không mở trong WebView: giao cho Android (link YouTube -> app ReVanced, vì web YouTube
     *  trên điện thoại bị PhoneDNS chặn). -> true nếu đã giao đi. Trang UC (laptop qua Tailscale, bản chỉ-xem) vẫn ở lại. */
    private boolean external(android.net.Uri u) {
        String sc = u.getScheme() == null ? "" : u.getScheme();
        if (sc.equals("file") || sc.equals("about") || sc.equals("data") || sc.equals("javascript")) return false;
        String h = u.getHost() == null ? "" : u.getHost();
        if ((sc.equals("http") || sc.equals("https")) && h.startsWith("100.")) return false;   // UC trên laptop
        Intent i = new Intent(Intent.ACTION_VIEW, u).addCategory(Intent.CATEGORY_BROWSABLE).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (h.equals("youtu.be") || h.equals("youtube.com") || h.endsWith(".youtube.com")) {
            try { startActivity(new Intent(i).setPackage(REVANCED)); return true; }   // thẳng vào ReVanced
            catch (android.content.ActivityNotFoundException e) { /* chưa cài -> để Android chọn */ }
        }
        try { startActivity(i); } catch (android.content.ActivityNotFoundException e) { android.util.Log.w("UCAPP", "no app " + sc); }
        return true;
    }

    /** (chủ 05/11) alert / confirm của trang: hộp tự vẽ đề "UC" — hộp mặc định của WebView lấy địa chỉ laptop làm tiêu đề. */
    private class Dialogs extends android.webkit.WebChromeClient {
        private boolean box(String msg, android.webkit.JsResult r, boolean ask) {
            android.app.AlertDialog.Builder b = new android.app.AlertDialog.Builder(MainActivity.this).setTitle("UC").setMessage(msg)
                    .setPositiveButton("OK", (d, w) -> r.confirm()).setOnCancelListener(d -> r.cancel());
            if (ask) b.setNegativeButton("Huỷ", (d, w) -> r.cancel());
            b.show(); return true;
        }
        @Override public boolean onJsAlert(WebView w, String url, String msg, android.webkit.JsResult r) { return box(msg, r, false); }
        @Override public boolean onJsConfirm(WebView w, String url, String msg, android.webkit.JsResult r) { return box(msg, r, true); }
    }

    private class Links extends WebViewClient {
        @Override public boolean shouldOverrideUrlLoading(WebView w, WebResourceRequest r) { return r.isForMainFrame() && external(r.getUrl()); }
    }

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        requestWindowFeature(android.view.Window.FEATURE_NO_TITLE);   // bỏ thanh tiêu đề "UC" của hệ thống (che nóc trang)
        // laptop đẩy đường dẫn qua dây cắm: am start -n vn.uc.app/.MainActivity --es uc_url <connector /w/…> --es uc_lan <http://100.x:8320/?k=…>
        String u = getIntent().getStringExtra("uc_url");
        if (u != null && u.matches("https://[^\\s/]+/w/[A-Za-z0-9_-]{20,}")) Store.setUrl(this, u);
        String lan = getIntent().getStringExtra("uc_lan");
        if (lan != null && lan.matches("http://100\\.[0-9.]+:8320/\\?k=[A-Za-z0-9_-]{30,}")) Store.setLan(this, lan);
        // (05/11) kênh thông báo (laptop đẩy qua dây / adb): --es uc_ntfy <tên kênh ntfy trong school/ntfy.json>
        String nt = getIntent().getStringExtra("uc_ntfy");
        if (nt != null && nt.matches("[A-Za-z0-9_-]{8,64}")) NotifyService.setTopic(this, nt);
        if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 7);
        else askBattery();
        NotifyService.start(this);

        view = make();
        view.addJavascriptInterface(new Bridge(), "UC");
        view.setWebViewClient(new Links());
        view.loadUrl(OFFLINE);
        laptop = make();
        view.setWebChromeClient(new Dialogs());
        laptop.setWebChromeClient(new Dialogs() {   // lỗi JS của trang laptop -> nhật ký
            @Override public boolean onConsoleMessage(android.webkit.ConsoleMessage m) {
                if (m.messageLevel() == android.webkit.ConsoleMessage.MessageLevel.ERROR)
                    android.util.Log.w("UCAPP", "js " + m.message() + " @" + m.lineNumber());
                return true;
            }
        });
        laptop.setVisibility(View.INVISIBLE);   // INVISIBLE (không GONE) để vẫn tải ở lớp dưới
        laptop.setWebViewClient(new Links() {
            @Override public void onPageStarted(WebView w, String url, android.graphics.Bitmap f) { android.util.Log.w("UCAPP", "start " + url.replaceAll("k=[^&]+", "k=***")); }
            @Override public void onReceivedHttpError(WebView w, WebResourceRequest r, android.webkit.WebResourceResponse resp) {
                android.util.Log.w("UCAPP", "http " + resp.getStatusCode() + " " + r.getUrl().getPath() + " main=" + r.isForMainFrame());
            }
            // trang laptop bắt đầu vẽ được -> chuyển sang luôn (không chờ tải xong hẳn: UC web còn nạp dữ liệu sau đó)
            @Override public void onPageCommitVisible(WebView w, String url) {
                android.util.Log.w("UCAPP", "visible " + url.replaceAll("k=[^&]+", "k=***"));
                if (url.startsWith("http://100.") && !url.contains("?k=") && !onLaptop) showLaptop();
            }
            @Override public void onPageFinished(WebView w, String url) {
                android.util.Log.w("UCAPP", "finished " + url.replaceAll("k=[^&]+", "k=***") + " p=" + w.getProgress());
                // chẩn đoán: trang laptop đang mở tab nào, hero cao bao nhiêu, có lỗi JS không
                w.postDelayed(() -> w.evaluateJavascript("(function(){try{var h=document.getElementById('p-home'),i=document.getElementById('hero-img');"
                        + "return JSON.stringify({w:innerWidth,h:innerHeight,app:(document.querySelector('.app')||{}).className,homeOn:h&&h.classList.contains('on'),"
                        + "homeH:h&&h.offsetHeight,homeDisp:h&&getComputedStyle(h).display,heroH:(document.getElementById('home-hero')||{}).offsetHeight,"
                        + "img:i&&i.currentSrc,imgW:i&&i.naturalWidth,err:window.__ucErr||null})}catch(e){return 'ERR '+e}})()",
                        v -> android.util.Log.w("UCAPP", "state " + v)), 4000);
                // khung trang chính xong là chuyển (UC web có yêu cầu chạy liên tục nên tiến độ có thể không bao giờ chạm 100)
                if (url.startsWith("http://100.") && !url.contains("?k=") && !onLaptop) showLaptop();
            }
            @Override public void onReceivedError(WebView w, WebResourceRequest r, WebResourceError e) {
                android.util.Log.w("UCAPP", "error " + e.getErrorCode() + " " + e.getDescription() + " " + r.getUrl().getPath() + " main=" + r.isForMainFrame());
                if (r.isForMainFrame()) { onLaptop = false; laptop.setVisibility(View.INVISIBLE); view.setVisibility(View.VISIBLE); }
            }
        });
        // Android 15+ vẽ tràn dưới 2 thanh hệ thống -> chừa đúng chỗ bằng đệm của khung chứa
        FrameLayout box = new FrameLayout(this);
        box.setBackgroundColor(getColor(R.color.paper));
        box.addView(view);
        box.addView(laptop);
        box.setOnApplyWindowInsetsListener((v, ins) -> {
            android.graphics.Insets bars = ins.getInsets(android.view.WindowInsets.Type.systemBars());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return ins;
        });
        setContentView(box);
        tryLaptop();
    }

    @Override public void onRequestPermissionsResult(int code, String[] perms, int[] res) { if (code == 7) askBattery(); }

    /** Xin tắt tối ưu pin cho app (một lần, bạn tự bấm Cho phép): để máy ngủ vẫn nhận thông báo đúng giờ. */
    private void askBattery() {
        android.os.PowerManager pm = getSystemService(android.os.PowerManager.class);
        if (NotifyService.topic(this).isEmpty() || pm.isIgnoringBatteryOptimizations(getPackageName())) return;
        try { startActivity(new Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, android.net.Uri.parse("package:" + getPackageName()))); }
        catch (Exception e) { android.util.Log.w("UCAPP", "battery " + e); }
    }

    private void tryLaptop() {
        String lan = Store.lan(this);
        if (!lan.isEmpty()) laptop.loadUrl(lan);
    }

    private void showLaptop() {
        onLaptop = true;
        laptop.setVisibility(View.VISIBLE);
        view.setVisibility(View.INVISIBLE);
    }

    @Override public void onBackPressed() {
        if (onLaptop) { if (laptop.canGoBack()) laptop.goBack(); else finish(); return; }
        view.evaluateJavascript("window.back && back()", v -> { if (!"true".equals(v)) finish(); });
    }

    final class Bridge {
        @JavascriptInterface public String cached() { return Store.cached(MainActivity.this); }
        @JavascriptInterface public long cachedAt() { return Store.cachedAt(MainActivity.this); }
        @JavascriptInterface public boolean hasUrl() { return Store.url(MainActivity.this).startsWith("https://"); }
        @JavascriptInterface public boolean hasLan() { return !Store.lan(MainActivity.this).isEmpty(); }
        @JavascriptInterface public void setUrl(String u) { Store.setUrl(MainActivity.this, u); }
        /** Từ bản chỉ-xem: thử mở lại UC web trên laptop. */
        @JavascriptInterface public void tryLaptop() { runOnUiThread(MainActivity.this::tryLaptop); }

        /** Tải mới ở luồng nền, xong gọi window.onData(json|null) trên trang + cập nhật widget. */
        @JavascriptInterface public void refresh() {
            new Thread(() -> {
                String j = Store.fetch(MainActivity.this);
                sendBroadcast(new Intent(UcWidget.REFRESH).setClass(MainActivity.this, UcWidget.class).putExtra("noFetch", true));
                String arg = j == null ? "null" : "JSON.parse(" + org.json.JSONObject.quote(j) + ")";
                runOnUiThread(() -> view.evaluateJavascript("window.onData && onData(" + arg + ")", null));
            }).start();
        }
    }
}
