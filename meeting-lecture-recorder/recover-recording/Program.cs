using System.Net.Http.Headers;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;

if (args.Length < 6)
    throw new ArgumentException("source captureId startedAt endedAt sourceMode outputPath are required");

var source = args[0];
var captureId = args[1];
var startedAt = args[2];
var endedAt = args[3];
var sourceMode = args[4];
var output = args[5];
var pcmPath = output + ".pcm.wav";

using (var reader = new WaveFileReader(source))
{
    ISampleProvider samples = reader.ToSampleProvider();
    if (samples.WaveFormat.Channels == 2)
        samples = new StereoToMonoSampleProvider(samples) { LeftVolume = 0.5f, RightVolume = 0.5f };
    var resampled = new WdlResamplingSampleProvider(samples, 16000);
    WaveFileWriter.CreateWaveFile16(pcmPath, resampled);
}

using (var pcmReader = new WaveFileReader(pcmPath))
    MediaFoundationEncoder.EncodeToMp3(pcmReader, output, 24000);
File.Delete(pcmPath);

var bytes = await File.ReadAllBytesAsync(output);
using var http = new HttpClient { Timeout = TimeSpan.FromMinutes(10) };
using var content = new ByteArrayContent(bytes);
content.Headers.ContentType = new MediaTypeHeaderValue("audio/mpeg");
var url = "http://localhost:5678/webhook/lecture-capture-upload" +
    "?captureId=" + Uri.EscapeDataString(captureId) +
    "&startedAt=" + Uri.EscapeDataString(startedAt) +
    "&endedAt=" + Uri.EscapeDataString(endedAt) +
    "&markers=%5B%5D&sourceMode=" + Uri.EscapeDataString(sourceMode) + "&format=mp3";
var response = await http.PostAsync(url, content);
var responseText = await response.Content.ReadAsStringAsync();
Console.WriteLine($"status={(int)response.StatusCode} bytes={bytes.Length} body={responseText}");
response.EnsureSuccessStatusCode();
