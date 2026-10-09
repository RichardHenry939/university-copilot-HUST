// Lecture Recorder Companion v2 — Claude 2026-10-02 (bản cũ: Program.cs.bak-codex-freebuff-20260927)
//
// LUẬT (người dùng chốt 2/10): CHỈ ghi khi người dùng bấm Start trong giao diện (University Copilot),
// CHỈ dừng khi người dùng bấm Stop. Không còn vòng hỏi lệnh từ n8n/Notion (gốc của 8 bản ghi tự động 14–25/9).
// Lưới an toàn duy nhất: ngưỡng thời gian (mặc định 3h30, tối thiểu 3h10), cảnh báo trước 10 phút, gia hạn được.
//
// Ghi âm: "máy bơm" theo đồng hồ thật, 16 kHz mono 16-bit cho mọi chế độ:
//   O1 dung lượng nhỏ (3h ≈ 350 MB)  O2 tự chèn khoảng lặng (loopback im lặng không gửi dữ liệu) -> mốc giờ luôn đúng
//   O3 đổi loa/tai nghe/micro mặc định giữa giờ -> tự chuyển nguồn, vẫn ghi tiếp cùng file
//   O4 thu riêng âm thanh 1 ứng dụng (Chrome/Teams/Zoom) bằng Windows process loopback   O5 trộn thêm giọng mình (micro)
//   O6 (Claude 5/10) chế độ "teams": thu CHỈ tiếng Teams qua cáp ảo VB-CABLE (Teams chọn loa = CABLE Input),
//      tự phát lại ra loa/tai nghe mặc định hiện tại (đổi theo khi tai nghe rớt) — bản ghi không lẫn ứng dụng khác,
//      không phụ thuộc tai nghe. (Process loopback O4 KHÔNG nhận được tiếng họp Teams: Windows trả toàn 0.)
//   O7 30 giây đầu toàn im lặng -> báo lỗi rõ ràng (sáng 5/10 mất 7 phút vì file toàn số 0 mà không ai biết)
// Chỉ nghe 127.0.0.1:5681.
using System.Diagnostics;
using System.Net.Http.Headers;
using System.Runtime.InteropServices;
using System.Text.Json;
using NAudio.CoreAudioApi;
using NAudio.CoreAudioApi.Interfaces;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.UseUrls("http://127.0.0.1:5681");
builder.Services.AddSingleton<Recorder>();
var app = builder.Build();

app.MapGet("/health", (Recorder r) => Results.Ok(r.Status()));
app.MapGet("/audio-devices", () => Results.Ok(Recorder.Devices()));
app.MapGet("/audio-apps", () => Results.Ok(Recorder.AudioApps()));
app.MapPost("/start", (StartRequest req, Recorder r) => Results.Ok(r.Start(req)));
app.MapPost("/stop", async (Recorder r) => Results.Ok(await r.StopAsync("user")));
app.MapPost("/marker", (MarkerRequest m, Recorder r) => Results.Ok(r.AddMarker(m)));
app.MapPost("/extend", (ExtendRequest e, Recorder r) => Results.Ok(r.Extend(e.Minutes <= 0 ? 60 : e.Minutes)));
app.MapPost("/retry-upload", async (RetryRequest q, Recorder r) => Results.Ok(await r.RetryUploadAsync(q.CaptureId)));
app.MapGet("/pending", () => Results.Ok(Recorder.Pending()));
// Lệnh cũ (/command start-room/start-online/stop) giữ cho tương thích, vẫn chỉ gọi được từ máy này.
app.MapPost("/command", async (LegacyCommand c, Recorder r) => c.Action.ToLowerInvariant() switch
{
    "start-room" => Results.Ok(r.Start(new StartRequest { Mode = "room" })),
    "start-online" => Results.Ok(r.Start(new StartRequest { Mode = "online" })),
    "stop" => Results.Ok(await r.StopAsync("user")),
    _ => Results.BadRequest(new { error = "action must be start-room, start-online, or stop" })
});
app.Lifetime.ApplicationStopping.Register(() => app.Services.GetRequiredService<Recorder>().EmergencyFinalize());
app.Run();

record LegacyCommand(string Action);
record MarkerRequest(string? Kind, string? Note);
record ExtendRequest(int Minutes);
record RetryRequest(string CaptureId);
sealed class StartRequest
{
    public string Mode { get; set; } = "room";          // room | online | teams (O6: cáp VB-CABLE)
    public bool IncludeMic { get; set; }                 // O5 (online)
    public int? AppPid { get; set; }                     // O4 (online): chỉ thu âm thanh của ứng dụng này
    public string? AppName { get; set; }
    public string? Course { get; set; }                  // ghi chú để hiển thị
    public string? SimulateFile { get; set; }            // KIỂM THỬ: phát file thay cho thiết bị (không ghi âm thật)
    public bool Test { get; set; }                       // KIỂM THỬ: chỉ đo mức âm, Stop thì XOÁ file, không gửi n8n
}

// ======================================================================= Recorder
sealed class Recorder
{
    public const int Rate = 16000;
    static readonly string Root = Environment.GetEnvironmentVariable("LRC_RECORDING_DIR") is { Length: > 0 } d ? d : @"D:\Data\LectureRecorder";
    static readonly string ConfigPath = Path.Combine(Root, "config.json");
    const string CaptureUrl = "http://localhost:5678/webhook/lecture-capture-upload";
    const int MinCapMinutes = 190;            // 3h10 — người dùng chốt
    const int DefaultCapMinutes = 210;        // 3h30

    readonly object gate = new();
    readonly MMDeviceEnumerator enumerator = new();
    readonly DeviceWatcher watcher;
    MixingSampleProvider? mixer;
    readonly List<ISource> sources = new();
    WaveFileWriter? writer;
    System.Threading.Timer? pump;
    long written;                              // số mẫu đã ghi
    DateTimeOffset? startedAt;
    DateTimeOffset capAt;
    string? captureId, mode, path, appName, course, lastError, deviceName;
    bool includeMic, simulate, testOnly, cable, heardAny, silentWarned;
    CableMonitor? monitor;
    double peakDb = -120, sumDb; long levelTicks;
    int? appPid;
    double levelDb = -120;
    readonly List<object> markers = new();
    readonly List<string> events = new();

    public Recorder()
    {
        Directory.CreateDirectory(Root);
        watcher = new DeviceWatcher(this);
        try { enumerator.RegisterEndpointNotificationCallback(watcher); } catch { /* không có thông báo thiết bị vẫn ghi được */ }
    }

    static int CapMinutes()
    {
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(ConfigPath));
            if (doc.RootElement.TryGetProperty("capMinutes", out var v)) return Math.Max(MinCapMinutes, v.GetInt32());
        }
        catch { }
        return DefaultCapMinutes;
    }

    public object Status()
    {
        lock (gate)
        {
            var rec = writer is not null;
            var elapsed = rec && startedAt is not null ? (DateTimeOffset.Now - startedAt.Value).TotalSeconds : 0;
            var capLeft = rec ? (capAt - DateTimeOffset.Now).TotalSeconds : 0;
            return new
            {
                recording = rec, mode, captureId, startedAt, elapsedSec = Math.Round(elapsed), levelDb = Math.Round(levelDb, 1),
                capMinutes = CapMinutes(), capAt = rec ? capAt : (DateTimeOffset?)null, capLeftSec = Math.Round(capLeft),
                capWarning = rec && capLeft <= 600, includeMic, test = testOnly, appName, appPid, course, device = deviceName, simulate,
                markers = markers.Count, cable, monitor = monitor?.DeviceName, lastError = lastError ?? ProcessLoopbackSource.LastError, events = events.TakeLast(6).ToArray(), pending = Pending().Length
            };
        }
    }

    public object Start(StartRequest req)
    {
        lock (gate)
        {
            if (writer is not null) return new { ok = true, alreadyRecording = true, captureId, mode };
            try
            {
                cable = req.Mode == "teams";
                mode = req.Mode is "online" or "teams" ? "online" : "room";
                heardAny = false; silentWarned = false; ProcessLoopbackSource.LastError = null;
                includeMic = mode == "online" && req.IncludeMic;
                appPid = mode == "online" && !cable ? req.AppPid : null;
                appName = req.AppName; course = req.Course; simulate = !string.IsNullOrEmpty(req.SimulateFile); testOnly = req.Test;
                peakDb = -120; sumDb = 0; levelTicks = 0;
                captureId = "lecture-" + DateTimeOffset.Now.ToUnixTimeMilliseconds();
                path = Path.Combine(Root, captureId + ".wav");
                mixer = new MixingSampleProvider(WaveFormat.CreateIeeeFloatWaveFormat(Rate, 1)) { ReadFully = true };
                sources.Clear(); markers.Clear(); events.Clear(); lastError = null;
                if (simulate) AddSource(new FileSource(req.SimulateFile!), "mô phỏng: " + Path.GetFileName(req.SimulateFile));
                else if (mode == "room") AddSource(DeviceSource.Microphone(enumerator, out var n), n);
                else
                {
                    if (cable)
                    {
                        var src = DeviceSource.Cable(enumerator, out var cn);
                        monitor = new CableMonitor(enumerator); src.Tap += monitor.Feed; monitor.Open(src.Format);
                        AddSource(src, "Teams qua cáp: " + cn);
                    }
                    else if (appPid is int pid) AddSource(ProcessLoopbackSource.Create(pid), "chỉ ứng dụng: " + (appName ?? pid.ToString()));
                    else AddSource(DeviceSource.Loopback(enumerator, out var n), "âm thanh máy: " + n);
                    if (includeMic) AddSource(DeviceSource.Microphone(enumerator, out var m), "micro: " + m);
                }
                writer = new WaveFileWriter(path, new WaveFormat(Rate, 16, 1));
                written = 0;
                startedAt = DateTimeOffset.Now;
                capAt = startedAt.Value.AddMinutes(CapMinutes());
                pump = new System.Threading.Timer(_ => Pump(), null, 100, 100);
                Log($"Bắt đầu ghi ({mode}{(simulate ? ", MÔ PHỎNG" : "")}) — {deviceName}");
                return new { ok = true, recording = true, captureId, mode, startedAt, capAt, device = deviceName };
            }
            catch (Exception ex)
            {
                foreach (var s in sources) s.Dispose();
                monitor?.Dispose(); monitor = null;
                sources.Clear(); writer?.Dispose(); writer = null; mixer = null;
                if (path is not null && File.Exists(path)) File.Delete(path);
                lastError = "Không bắt đầu ghi được: " + ex.Message;
                return new { ok = false, error = lastError };
            }
        }
    }

    void AddSource(ISource s, string name)
    {
        sources.Add(s); mixer!.AddMixerInput(s.Output); s.Start();
        deviceName = deviceName is null || sources.Count == 1 ? name : deviceName + " + " + name;
    }

    // O2: ghi đúng bằng thời gian thật; nguồn im lặng/thiếu dữ liệu -> mixer trả 0 (khoảng lặng)
    void Pump()
    {
        float[] buf; int n;
        lock (gate)
        {
            if (writer is null || mixer is null || startedAt is null) return;
            var target = (long)((DateTimeOffset.Now - startedAt.Value).TotalSeconds * Rate);
            n = (int)Math.Min(target - written, Rate * 2);
            if (n <= 0) return;
            buf = new float[n];
            mixer.Read(buf, 0, n);
            double sum = 0;
            var pcm = new byte[n * 2];
            for (int i = 0; i < n; i++)
            {
                var v = Math.Clamp(buf[i], -1f, 1f); sum += v * v;
                var s = (short)(v * 32767);
                pcm[2 * i] = (byte)s; pcm[2 * i + 1] = (byte)(s >> 8);
            }
            writer.Write(pcm, 0, pcm.Length);
            written += n;
            levelDb = 10 * Math.Log10(sum / n + 1e-12);
            peakDb = Math.Max(peakDb, levelDb); sumDb += levelDb; levelTicks++;
            if (levelDb > -90) heardAny = true;
            if (!heardAny && !silentWarned && !simulate && written > Rate * 30)
            {
                silentWarned = true;
                lastError = cable ? "30 giây đầu HOÀN TOÀN im lặng qua cáp — trong Teams: Cài đặt → Thiết bị → Loa = CABLE Input (VB-Audio Virtual Cable)."
                                  : "30 giây đầu HOÀN TOÀN im lặng — nguồn thu không nhận được tiếng (kiểm tra ứng dụng / thiết bị).";
                events.Add($"{DateTime.Now:HH:mm:ss} CẢNH BÁO: {lastError}");
            }
            if (DateTimeOffset.Now >= capAt) _ = Task.Run(() => StopAsync("cap"));
        }
    }

    // O3: đổi thiết bị mặc định giữa giờ -> thay nguồn, giữ nguyên file
    public void OnDefaultDeviceChanged(DataFlow flow)
    {
        Task.Run(() =>
        {
            lock (gate)
            {
                if (writer is null || simulate || mixer is null) return;
                try
                {
                    if (flow == DataFlow.Render && cable) { monitor?.Reopen(); Log("Đổi loa nghe lại -> " + monitor?.DeviceName); }
                    else if (flow == DataFlow.Render && mode == "online" && appPid is null)
                        Swap(s => s is DeviceSource d && d.IsLoopback, () => DeviceSource.Loopback(enumerator, out var n), "âm thanh máy");
                    else if (flow == DataFlow.Capture && (mode == "room" || includeMic))
                        Swap(s => s is DeviceSource d && !d.IsLoopback, () => DeviceSource.Microphone(enumerator, out var n), "micro");
                }
                catch (Exception ex) { lastError = "Đổi thiết bị lỗi: " + ex.Message; }
            }
        });
    }

    void Swap(Func<ISource, bool> match, Func<DeviceSource> make, string what)
    {
        var old = sources.FirstOrDefault(match);
        var fresh = make();
        if (old is not null) { mixer!.RemoveMixerInput(old.Output); old.Dispose(); sources.Remove(old); }
        sources.Add(fresh); mixer!.AddMixerInput(fresh.Output); fresh.Start();
        Log($"Đổi {what} -> {fresh.Name}");
    }

    public object AddMarker(MarkerRequest m)
    {
        lock (gate)
        {
            if (writer is null || startedAt is null) return new { ok = false, error = "Chưa ghi." };
            var t = Math.Round((DateTimeOffset.Now - startedAt.Value).TotalSeconds, 1);
            markers.Add(new { t, kind = m.Kind ?? "Quan trọng", note = m.Note ?? "" });
            return new { ok = true, t, count = markers.Count };
        }
    }

    public object Extend(int minutes)
    {
        lock (gate)
        {
            if (writer is null) return new { ok = false, error = "Chưa ghi." };
            capAt = capAt.AddMinutes(Math.Clamp(minutes, 15, 180));
            Log($"Gia hạn thêm {minutes} phút (dừng an toàn lúc {capAt:HH:mm})");
            return new { ok = true, capAt };
        }
    }

    public async Task<object> StopAsync(string reason)
    {
        WaveFileWriter? w; string? id, p, m; DateTimeOffset? began; object[] mk;
        lock (gate)
        {
            if (writer is null) return new { ok = true, alreadyStopped = true };
            pump?.Dispose(); pump = null;
            foreach (var s in sources) s.Dispose();
            monitor?.Dispose(); monitor = null;
            sources.Clear(); mixer = null;
            w = writer; writer = null; id = captureId; p = path; m = mode; began = startedAt; mk = markers.ToArray();
            if (reason == "cap") lastError = $"Đã tự dừng ở ngưỡng an toàn ({CapMinutes()} phút + gia hạn). Bản ghi vẫn được gửi xử lý.";
            Log(reason == "cap" ? "Tự dừng ở ngưỡng an toàn" : "Dừng theo lệnh người dùng");
        }
        w!.Dispose();
        if (testOnly)
        {
            var stats = new { ok = true, test = true, discarded = true, seconds = Math.Round((DateTimeOffset.Now - began!.Value).TotalSeconds, 1),
                peakDb = Math.Round(peakDb, 1), avgDb = Math.Round(levelTicks > 0 ? sumDb / levelTicks : -120, 1), source = deviceName };
            try { File.Delete(p!); } catch { }
            lock (gate) { startedAt = null; captureId = null; deviceName = null; testOnly = false; }
            Log("Bản ghi kiểm thử đã xoá (không gửi n8n)");
            return stats;
        }
        var meta = new { captureId = id, startedAt = began, endedAt = DateTimeOffset.Now, mode = m, markers = mk, course };
        await File.WriteAllTextAsync(p! + ".json", JsonSerializer.Serialize(meta));
        var up = await UploadAsync(p!);
        lock (gate) { startedAt = null; captureId = null; deviceName = null; }
        return up;
    }

    public void EmergencyFinalize()
    {
        lock (gate) { pump?.Dispose(); foreach (var s in sources) s.Dispose(); writer?.Dispose(); writer = null; }
    }

    public static string[] Pending() =>
        Directory.Exists(Root) ? Directory.GetFiles(Root, "lecture-*.wav").Select(Path.GetFileNameWithoutExtension).ToArray()! : Array.Empty<string>();

    public async Task<object> RetryUploadAsync(string captureId)
    {
        var p = Path.Combine(Root, Path.GetFileName(captureId) + ".wav");
        if (!File.Exists(p)) return new { ok = false, error = "Không còn file chờ gửi." };
        return await UploadAsync(p);
    }

    async Task<object> UploadAsync(string wavPath)
    {
        try
        {
            using var metaDoc = JsonDocument.Parse(await File.ReadAllTextAsync(wavPath + ".json"));
            var meta = metaDoc.RootElement;
            var mp3 = Path.ChangeExtension(wavPath, ".upload.mp3");
            await Task.Run(() => { using var reader = new WaveFileReader(wavPath); MediaFoundationEncoder.EncodeToMp3(reader, mp3, 24000); });
            var bytes = await File.ReadAllBytesAsync(mp3);
            using var http = new HttpClient { Timeout = TimeSpan.FromMinutes(10) };
            using var content = new ByteArrayContent(bytes);
            content.Headers.ContentType = new MediaTypeHeaderValue("audio/mpeg");
            var q = "?captureId=" + Uri.EscapeDataString(meta.GetProperty("captureId").GetString()!) +
                    "&startedAt=" + Uri.EscapeDataString(meta.GetProperty("startedAt").GetDateTimeOffset().ToString("O")) +
                    "&endedAt=" + Uri.EscapeDataString(meta.GetProperty("endedAt").GetDateTimeOffset().ToString("O")) +
                    "&markers=" + Uri.EscapeDataString(meta.GetProperty("markers").GetRawText()) +
                    "&sourceMode=" + Uri.EscapeDataString(meta.GetProperty("mode").GetString() == "online" ? "online-class" : "lecture-room") +
                    "&format=mp3";
            var resp = await http.PostAsync(CaptureUrl + q, content);
            var text = await resp.Content.ReadAsStringAsync();
            resp.EnsureSuccessStatusCode();
            File.Delete(wavPath); File.Delete(wavPath + ".json"); File.Delete(mp3);
            Log("Đã gửi bản ghi sang n8n để xử lý");
            return new { ok = true, uploaded = true, captureId = meta.GetProperty("captureId").GetString(), bytes = bytes.Length, response = text };
        }
        catch (Exception ex)
        {
            lock (gate) lastError = "Gửi bản ghi lỗi (file vẫn giữ, bấm 'Gửi lại'): " + ex.Message;
            return new { ok = false, error = ex.Message, retained = Path.GetFileName(wavPath) };
        }
    }

    void Log(string s)
    {
        events.Add($"{DateTime.Now:HH:mm:ss} {s}");
        try { File.AppendAllText(Path.Combine(Root, "recorder.log"), $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {s}\n"); } catch { }
    }

    public static object Devices()
    {
        using var e = new MMDeviceEnumerator();
        object list(DataFlow f) => e.EnumerateAudioEndPoints(f, DeviceState.Active).Select(d => new { id = d.ID, name = d.FriendlyName }).ToArray();
        string def(DataFlow f) { try { return e.GetDefaultAudioEndpoint(f, Role.Multimedia).FriendlyName; } catch { return ""; } }
        return new { capture = list(DataFlow.Capture), render = list(DataFlow.Render), defaultCapture = def(DataFlow.Capture), defaultRender = def(DataFlow.Render) };
    }

    // O4: ứng dụng đang có phiên âm thanh -> chọn để thu riêng (gộp theo tên, lấy tiến trình gốc cũ nhất)
    public static object AudioApps()
    {
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            using var e = new MMDeviceEnumerator();
            foreach (var dev in e.EnumerateAudioEndPoints(DataFlow.Render, DeviceState.Active))
            {
                var sessions = dev.AudioSessionManager.Sessions;
                for (int i = 0; i < sessions.Count; i++)
                {
                    var s = sessions[i];
                    if (s.IsSystemSoundsSession) continue;
                    try { var p = Process.GetProcessById((int)s.GetProcessID); names.Add(p.ProcessName); } catch { }
                }
            }
        }
        catch { }
        return names.Select(n =>
        {
            var procs = Process.GetProcessesByName(n);
            var root = procs.OrderBy(p => { try { return p.StartTime; } catch { return DateTime.MaxValue; } }).FirstOrDefault();
            return new { name = n, pid = root?.Id, title = root?.MainWindowTitle ?? "" };
        }).Where(a => a.pid is not null).OrderBy(a => a.name).ToArray();
    }
}

// ======================================================================= nguồn âm thanh -> 16 kHz mono float
interface ISource : IDisposable { ISampleProvider Output { get; } string Name { get; } void Start(); }

static class Convert16k
{
    public static ISampleProvider From(IWaveProvider buffered)
    {
        ISampleProvider s = buffered.ToSampleProvider();
        if (s.WaveFormat.Channels == 2) s = new StereoToMonoSampleProvider(s) { LeftVolume = 0.5f, RightVolume = 0.5f };
        else if (s.WaveFormat.Channels > 2) s = new DownmixToMono(s);
        if (s.WaveFormat.SampleRate != Recorder.Rate) s = new WdlResamplingSampleProvider(s, Recorder.Rate);
        return s;
    }
}

sealed class DownmixToMono : ISampleProvider
{
    readonly ISampleProvider src; readonly int ch; float[] tmp = Array.Empty<float>();
    public DownmixToMono(ISampleProvider s) { src = s; ch = s.WaveFormat.Channels; WaveFormat = WaveFormat.CreateIeeeFloatWaveFormat(s.WaveFormat.SampleRate, 1); }
    public WaveFormat WaveFormat { get; }
    public int Read(float[] buffer, int offset, int count)
    {
        if (tmp.Length < count * ch) tmp = new float[count * ch];
        var got = src.Read(tmp, 0, count * ch) / ch;
        for (int i = 0; i < got; i++) { float s = 0; for (int c = 0; c < ch; c++) s += tmp[i * ch + c]; buffer[offset + i] = s / ch; }
        return got;
    }
}

sealed class DeviceSource : ISource
{
    readonly IWaveIn capture; readonly BufferedWaveProvider buffer;
    public bool IsLoopback { get; }
    public string Name { get; }
    public event Action<byte[], int>? Tap;           // O6: chép nguyên dữ liệu cho bộ phát lại
    public WaveFormat Format => capture.WaveFormat;
    public ISampleProvider Output { get; }
    DeviceSource(IWaveIn c, bool loopback, string name)
    {
        capture = c; IsLoopback = loopback; Name = name;
        buffer = new BufferedWaveProvider(c.WaveFormat) { BufferDuration = TimeSpan.FromSeconds(10), DiscardOnBufferOverflow = true, ReadFully = true };
        c.DataAvailable += (_, e) => { buffer.AddSamples(e.Buffer, 0, e.BytesRecorded); Tap?.Invoke(e.Buffer, e.BytesRecorded); };
        Output = Convert16k.From(buffer);
    }
    public static DeviceSource Microphone(MMDeviceEnumerator e, out string name)
    {
        // Không tin "default role" (từng trỏ vào Bluetooth đã ngắt sau khi máy ngủ): ưu tiên micro mặc định còn Active, rồi Microphone Array
        MMDevice dev;
        try { dev = e.GetDefaultAudioEndpoint(DataFlow.Capture, Role.Communications); if (dev.State != DeviceState.Active) throw new Exception(); }
        catch { dev = e.EnumerateAudioEndPoints(DataFlow.Capture, DeviceState.Active).OrderByDescending(d => d.FriendlyName.Contains("Microphone Array", StringComparison.OrdinalIgnoreCase)).First(); }
        name = dev.FriendlyName;
        return new DeviceSource(new WasapiCapture(dev, false, 100), false, name);
    }
    public static DeviceSource Loopback(MMDeviceEnumerator e, out string name)
    {
        var dev = e.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia);
        name = dev.FriendlyName;
        return new DeviceSource(new WasapiLoopbackCapture(dev), true, name);
    }
    // O6: đầu ra của cáp ảo VB-Audio ("CABLE Output") — chỉ có những gì Teams phát vào "CABLE Input"
    public static DeviceSource Cable(MMDeviceEnumerator e, out string name)
    {
        var dev = e.EnumerateAudioEndPoints(DataFlow.Capture, DeviceState.Active)
                   .FirstOrDefault(d => d.FriendlyName.Contains("CABLE Output", StringComparison.OrdinalIgnoreCase))
                   ?? throw new InvalidOperationException("Chưa có cáp ảo VB-CABLE (thiết bị CABLE Output). Cài VB-CABLE rồi thử lại.");
        name = dev.FriendlyName;
        return new DeviceSource(new WasapiCapture(dev, false, 50), false, name);
    }
    public void Start() => capture.StartRecording();
    public void Dispose() { try { capture.StopRecording(); } catch { } capture.Dispose(); }
}

// O6: phát lại tiếng cáp ra loa/tai nghe mặc định đang dùng (không bao giờ phát vào chính cáp) — bạn vẫn nghe giảng
sealed class CableMonitor : IDisposable
{
    readonly MMDeviceEnumerator en; readonly object lk = new();
    BufferedWaveProvider? buf; WasapiOut? output; WaveFormat? fmt;
    public string? DeviceName { get; private set; }
    public CableMonitor(MMDeviceEnumerator e) => en = e;
    public void Open(WaveFormat f) { lock (lk) { fmt = f; Begin(); } }
    public void Reopen() { lock (lk) { End(); Begin(); } }
    void Begin()
    {
        MMDevice? dev = null;
        try { dev = en.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia); } catch { }
        if (dev is null || dev.FriendlyName.Contains("CABLE", StringComparison.OrdinalIgnoreCase))
            dev = en.EnumerateAudioEndPoints(DataFlow.Render, DeviceState.Active).FirstOrDefault(d => !d.FriendlyName.Contains("CABLE", StringComparison.OrdinalIgnoreCase));
        if (dev is null || fmt is null) { DeviceName = null; return; }
        buf = new BufferedWaveProvider(fmt) { BufferDuration = TimeSpan.FromSeconds(2), DiscardOnBufferOverflow = true, ReadFully = true };
        output = new WasapiOut(dev, AudioClientShareMode.Shared, true, 60);
        output.Init(buf); output.Play(); DeviceName = dev.FriendlyName;
    }
    void End() { try { output?.Stop(); } catch { } output?.Dispose(); output = null; buf = null; }
    public void Feed(byte[] data, int n) { var b = buf; b?.AddSamples(data, 0, n); }
    public void Dispose() { lock (lk) End(); }
}

sealed class FileSource : ISource
{
    readonly AudioFileReader reader;
    public string Name { get; }
    public ISampleProvider Output { get; }
    public FileSource(string file)
    {
        reader = new AudioFileReader(file); Name = Path.GetFileName(file);
        ISampleProvider s = reader;
        if (s.WaveFormat.Channels == 2) s = new StereoToMonoSampleProvider(s);
        if (s.WaveFormat.SampleRate != Recorder.Rate) s = new WdlResamplingSampleProvider(s, Recorder.Rate);
        Output = s;      // máy bơm kéo đúng tốc độ thời gian thực -> "phát" file như đang nghe giảng
    }
    public void Start() { }
    public void Dispose() => reader.Dispose();
}

sealed class DeviceWatcher : IMMNotificationClient
{
    readonly Recorder r;
    public DeviceWatcher(Recorder r) => this.r = r;
    public void OnDefaultDeviceChanged(DataFlow flow, Role role, string defaultDeviceId) { if (role == Role.Multimedia || flow == DataFlow.Capture) r.OnDefaultDeviceChanged(flow); }
    public void OnDeviceStateChanged(string deviceId, DeviceState newState) { }
    public void OnDeviceAdded(string pwstrDeviceId) { }
    public void OnDeviceRemoved(string deviceId) { }
    public void OnPropertyValueChanged(string pwstrDeviceId, PropertyKey key) { }
}

// ======================================================================= O4: Windows process loopback (Windows 10 2004+)
sealed class ProcessLoopbackSource : ISource
{
    public static volatile string? LastError;
    readonly IAudioClientRaw client; readonly IAudioCaptureClientRaw cap; readonly BufferedWaveProvider buffer;
    readonly WaveFormat fmt = new(48000, 16, 2);
    Thread? thread; volatile bool running;
    public string Name { get; }
    public ISampleProvider Output { get; }

    ProcessLoopbackSource(IAudioClientRaw c, int pid)
    {
        client = c; Name = "pid " + pid;
        var wfx = new WAVEFORMATEX { wFormatTag = 1, nChannels = 2, nSamplesPerSec = 48000, wBitsPerSample = 16, nBlockAlign = 4, nAvgBytesPerSec = 192000, cbSize = 0 };
        var p = Marshal.AllocHGlobal(Marshal.SizeOf<WAVEFORMATEX>());
        try
        {
            Marshal.StructureToPtr(wfx, p, false);
            var empty = Guid.Empty;
            const int LOOPBACK = 0x00020000, AUTOCONVERT = unchecked((int)0x80000000), SRC_DEFAULT_QUALITY = 0x08000000;
            client.Initialize(0, LOOPBACK | AUTOCONVERT | SRC_DEFAULT_QUALITY, 2_000_000, 0, p, ref empty);
        }
        finally { Marshal.FreeHGlobal(p); }
        var iid = typeof(IAudioCaptureClientRaw).GUID;
        client.GetService(ref iid, out var svc);
        cap = (IAudioCaptureClientRaw)svc;
        buffer = new BufferedWaveProvider(fmt) { BufferDuration = TimeSpan.FromSeconds(10), DiscardOnBufferOverflow = true, ReadFully = true };
        Output = Convert16k.From(buffer);
    }

    public static ProcessLoopbackSource Create(int pid)
    {
        var prm = new AUDIOCLIENT_ACTIVATION_PARAMS { ActivationType = 1, TargetProcessId = pid, ProcessLoopbackMode = 0 };   // gồm cả tiến trình con
        var prmPtr = Marshal.AllocHGlobal(Marshal.SizeOf<AUDIOCLIENT_ACTIVATION_PARAMS>());
        var pv = Marshal.AllocHGlobal(Marshal.SizeOf<PROPVARIANT_BLOB>());
        try
        {
            Marshal.StructureToPtr(prm, prmPtr, false);
            Marshal.StructureToPtr(new PROPVARIANT_BLOB { vt = 65, cbSize = Marshal.SizeOf<AUDIOCLIENT_ACTIVATION_PARAMS>(), pBlobData = prmPtr }, pv, false);
            var handler = new ActivationHandler();
            ActivateAudioInterfaceAsync("VAD\\Process_Loopback", typeof(IAudioClientRaw).GUID, pv, handler, out _);
            if (!handler.Done.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Windows không phản hồi process loopback");
            if (handler.Hr != 0) throw new COMException("Không thu riêng ứng dụng được", handler.Hr);
            return new ProcessLoopbackSource((IAudioClientRaw)handler.Client!, pid);
        }
        finally { Marshal.FreeHGlobal(prmPtr); Marshal.FreeHGlobal(pv); }
    }

    public void Start()
    {
        client.Start(); running = true;
        thread = new Thread(Loop) { IsBackground = true, Name = "process-loopback" }; thread.Start();
    }

    void Loop()
    {
        while (running)
        {
            Thread.Sleep(10);
            try
            {
                while (running && cap.GetNextPacketSize(out var frames) == 0 && frames > 0)
                {
                    if (cap.GetBuffer(out var data, out var n, out var flags, out _, out _) != 0) break;
                    var bytes = n * fmt.BlockAlign;
                    var arr = new byte[bytes];
                    if ((flags & 0x2) == 0) Marshal.Copy(data, arr, 0, bytes);           // 0x2 = SILENT -> giữ 0
                    buffer.AddSamples(arr, 0, bytes);
                    cap.ReleaseBuffer(n);
                }
            }
            catch (Exception ex) { LastError ??= "Thu riêng ứng dụng lỗi: " + ex.Message; }   // trước đây nuốt im lặng
        }
    }

    public void Dispose() { running = false; thread?.Join(500); try { client.Stop(); } catch { } Marshal.ReleaseComObject(cap); Marshal.ReleaseComObject(client); }

    [DllImport("Mmdevapi.dll", ExactSpelling = true, PreserveSig = false)]
    static extern void ActivateAudioInterfaceAsync([MarshalAs(UnmanagedType.LPWStr)] string deviceInterfacePath,
        [MarshalAs(UnmanagedType.LPStruct)] Guid riid, IntPtr activationParams,
        IActivateAudioInterfaceCompletionHandler completionHandler, out IActivateAudioInterfaceAsyncOperation op);

    [StructLayout(LayoutKind.Sequential)] struct AUDIOCLIENT_ACTIVATION_PARAMS { public int ActivationType; public int TargetProcessId; public int ProcessLoopbackMode; }
    [StructLayout(LayoutKind.Explicit)] struct PROPVARIANT_BLOB { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public int cbSize; [FieldOffset(16)] public IntPtr pBlobData; }
    [StructLayout(LayoutKind.Sequential, Pack = 2)] struct WAVEFORMATEX { public ushort wFormatTag, nChannels; public uint nSamplesPerSec, nAvgBytesPerSec; public ushort nBlockAlign, wBitsPerSample, cbSize; }

    sealed class ActivationHandler : IActivateAudioInterfaceCompletionHandler, IAgileObject
    {
        public readonly ManualResetEventSlim Done = new(false);
        public int Hr; public object? Client;
        public void ActivateCompleted(IActivateAudioInterfaceAsyncOperation op) { op.GetActivateResult(out Hr, out Client); Done.Set(); }
    }
}

[ComImport, Guid("41D949AB-9862-444A-80F6-C261334DA5EB"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IActivateAudioInterfaceCompletionHandler { void ActivateCompleted(IActivateAudioInterfaceAsyncOperation op); }
[ComImport, Guid("72A22D78-CDE4-431D-B8CC-843A71199B6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IActivateAudioInterfaceAsyncOperation { void GetActivateResult(out int hr, [MarshalAs(UnmanagedType.IUnknown)] out object iface); }
[ComImport, Guid("94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAgileObject { }
[ComImport, Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioClientRaw
{
    void Initialize(int shareMode, int streamFlags, long bufferDuration, long periodicity, IntPtr format, ref Guid session);
    void GetBufferSize(out uint frames); void GetStreamLatency(out long latency); void GetCurrentPadding(out int padding);
    void IsFormatSupported(int shareMode, IntPtr format, out IntPtr closest); void GetMixFormat(out IntPtr format);
    void GetDevicePeriod(out long def, out long min); void Start(); void Stop(); void Reset(); void SetEventHandle(IntPtr h);
    void GetService(ref Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object service);
}
[ComImport, Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioCaptureClientRaw
{
    [PreserveSig] int GetBuffer(out IntPtr data, out int frames, out int flags, out long devicePosition, out long qpcPosition);
    [PreserveSig] int ReleaseBuffer(int frames);
    [PreserveSig] int GetNextPacketSize(out int frames);
}
