# Lecture Recorder Companion v2 (2/10/2026)

Local Windows audio recorder. Listens only on `127.0.0.1:5681`. It is controlled from **University Copilot → tab "Ghi bài giảng"**.

**Rule (decided by the owner on 2/10):**
- It records ONLY when the user presses Start in that UI, and stops ONLY when the user presses Stop.
- There is no polling of n8n/Notion any more. That polling caused the 8 unintended auto-recordings on 14–25/9.
- The only automatic stop is a safety cap: default 3h30, never below 3h10. The UI warns 10 minutes before and can extend.

**Endpoints:**

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Status: elapsed time, level (dB), cap, markers, device, last events |
| POST | `/start` | `{mode: "room", "online" or "teams", includeMic?, appPid?, appName?, course?, simulateFile?}` |
| POST | `/stop` | Writes the WAV, encodes MP3 24 kbps, uploads to n8n `lecture-capture-upload` with markers |
| POST | `/marker` | `{kind, note}` |
| POST | `/extend` | `{minutes}` |
| POST | `/retry-upload` | `{captureId}` |
| GET | `/pending` | Recordings that failed to upload |
| GET | `/audio-devices` | Audio devices |
| GET | `/audio-apps` | Apps with active audio sessions |

**How recording works:** a wall-clock "pump" writes 16 kHz mono 16-bit for every mode.
- 3 hours is about 350 MB.
- Silent gaps are filled, so timestamps and markers stay correct.
- Default-device changes are followed mid-session.
- Online mode can capture a single app through Windows process loopback.
- Online mode can mix in your own microphone.

**Teams mode (5/10/2026):**
- Windows process loopback returns only digital silence for Teams meeting audio, whether it targets the parent or the child process.
- `mode: "teams"` therefore captures the VB-CABLE virtual device instead. In Teams, set Speaker = CABLE Input; the recorder captures "CABLE Output".
- Only Teams audio ends up in the recording. The recorder plays it back to the current default speaker and follows headphone disconnects.
- If the first 30 s are completely silent, the recorder reports an error with a hint, instead of failing silently.

**Testing:** `simulateFile` plays a local audio file instead of a device. No real recording happens.

After upload, n8n workflow "University — Lecture Analysis" (v2) takes over:
1. The local speech gate does audio → text → compact (PhoWhisper + LM Studio).
2. Gemini reads only the compacted text plus slide photos.
3. The results become a Lecture Note and a University Inbox item.

The previous source is kept as `Program.cs.bak-codex-freebuff-20260927`.
