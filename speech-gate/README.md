# Speech gate: audio → text → compact (127.0.0.1:8340)

The second half of **Ghi bài giảng** (lecture recording). The recorder (`../lecture-recorder`) sends audio to n8n, and n8n hands it to this gate.

**Audio never goes to Gemini.** Everything below runs on the machine:

1. **Quality check (VAD).** If there is too little speech, the job is marked `unusable` and stops. Nothing is transcribed and no tokens are spent.
2. **Transcription with PhoWhisper-large.**
   - Runs on the **NPU** (OpenVINO INT8, about 4.5× realtime).
   - Falls back to the CPU (faster-whisper int8) if the NPU fails.
3. **Garbage filter.** Drops hallucinated lines ("đăng ký kênh"…), repeated words and low-confidence segments.
4. **Compaction with LM Studio** (qwen3-14b), in ~8-minute chunks. Formulas, definitions, homework and deadlines are kept verbatim.
5. **Callback to n8n.** Sends the compacted notes, stats and slide photos. Only this compacted text reaches Gemini.

**05/10/2026 patch**
- `lm()` retries 4 times with backoff. If qwen3-14b cannot be loaded (for example, the machine is low on memory), it falls back to **qwen3-8b**. Before this, one LM Studio error threw away the whole lecture, even though transcription had already finished.
- The transcript is saved to `kept.json`.
- `POST /jobs/<id>/retry` reruns a failed job **from the compaction step**, without re-transcribing.

**HTTP API**

| Method | Path | Purpose |
|---|---|---|
| POST | `/jobs?captureId=&startedAt=&endedAt=&markers=&callback=` | Body = audio (mp3/wav/webm) |
| POST | `/jobs/<id>/retry` | Rerun a failed job |
| GET | `/jobs/<id>` | Job status |
| GET | `/jobs?captureId=<id>` | Job status by capture ID |
| GET | `/health` | Health check |
| POST | `/slides?captureId=&name=` | Body = a slide photo |

**Model conversion**
- `export_ov.py` and `quantize_ov.py` convert PhoWhisper to OpenVINO INT8 for the NPU.
- `bakeoff/` holds the scripts used to compare models. Each takes one recording as an argument.
- `tests/` holds the scripts that generate test audio.

**Secret:** `UC_SECRET_FILE`, which defaults to `../.copilot-secret`, the same file the UC web app uses. It is not committed to Git.
