# Multi-Input Thai ASR Web Application — Implementation Blueprint

> **เอกสารสำหรับใช้เป็น Prompt ให้ AI Coding Agent**  
> Version: 1.0 | 15 October 2026 | Language: Thai-first UI, English technical names

## 0. คำสั่งสำหรับ AI Coding Agent

คุณคือ Senior Full-Stack Python Engineer และ ML Systems Engineer จงพัฒนา **เว็บแอปพลิเคชันถอดเสียงภาษาไทยจากไฟล์เสียง ไมโครโฟน และไฟล์วิดีโอ** ให้ใช้งานได้จริงบนเครื่อง Local และย้ายขึ้น Linux Server ได้ โดยอ้างอิง Blueprint นี้เป็นข้อกำหนดหลัก

**ข้อบังคับ:**
1. สร้างโค้ดที่รันได้จริง ไม่ใช่เพียง mockup; ไม่สร้างข้อความถอดเสียงจำลอง
2. ทำ MVP ตามลำดับ Phase 1 ก่อน อย่าเพิ่ม LLM, sentiment, summary, translation หรือฐานข้อมูลโดยไม่จำเป็น
3. ใช้ ASR ภายในเครื่อง/เซิร์ฟเวอร์ ไม่ส่งเสียงหรือวิดีโอไปยังบริการภายนอก
4. รองรับ **Audio File + Microphone Recording + Video File** ตั้งแต่ MVP
5. รองรับ `.avi` โดยใช้ FFmpeg ตรวจสอบและแยก audio stream ก่อนถอดเสียง
6. แสดงสถานะงานจริงและ error ที่เข้าใจได้ ห้ามสร้าง progress percentage ที่ไม่มีข้อมูลรองรับ
7. เก็บผล AI ต้นฉบับแยกจากผลที่ผู้ใช้แก้ไข และเก็บไฟล์สื่อต้นฉบับไว้
8. ป้องกันการรั่วไหลของข้อมูลส่วนบุคคล; ไม่ log เนื้อหาเสียง/ข้อความหรือข้อมูลลับ
9. สร้าง unit/integration tests, README, `.env.example`, Dockerfile และ `compose.yaml`
10. เมื่อมีข้อจำกัดของ library, model, hardware หรือ codec ให้แจ้งตามจริง ไม่อ้างว่ารองรับโดยไม่ทดสอบ

## 1. วัตถุประสงค์

สร้าง Web App สำหรับการสาธิตการถอดเสียงภาษาไทย และการประมวลผลไฟล์สนทนาระหว่าง Contact Center กับลูกค้า รองรับเสียงภาษาไทยปนอังกฤษ ผู้ใช้สามารถฟังสื่อเดิม ดูข้อความพร้อมเวลา แก้ไขข้อความ และส่งออก Transcript หรือ Subtitle ได้

### In Scope (MVP)
- อัปโหลดไฟล์เสียงหรือวิดีโอ
- อัดเสียงจากไมโครโฟนในเบราว์เซอร์: Record → Stop → Submit → Transcribe (ไม่ใช่ live streaming)
- ตรวจสอบชนิดสื่อด้วย decoder/probe จริง และแปลง/แยก audio track อย่างปลอดภัย
- คิวงานแบบ asynchronous; เปิดหน้าเว็บดูสถานะได้
- ถอดเสียงภาษาไทยด้วย faster-whisper แบบ Local
- Segment-level timestamps และข้อความต้นฉบับ
- เล่นเสียงต้นฉบับ/วิดีโอ และ seek ตาม timestamp ของ segment
- แก้ไข transcript และเก็บ revision
- Export UTF-8 TXT, JSON, SRT; เพิ่ม VTT หากทำได้โดยไม่กระทบ MVP
- รายการงาน, retry, delete, error handling, health/status page
- ใช้งานบน CPU ก่อน; มี GPU deployment profile แยก

### Out of Scope (MVP)
- Live caption/streaming, speech translation, meeting summarization, topic/sentiment extraction
- Voice biometric identification หรือการระบุตัวตนผู้พูด
- การรับรองความถูกต้องของ transcript โดยไม่ benchmark
- Multi-tenant enterprise RBAC, database, distributed queue, model training
- Speaker diarization แบบรับรองผล: ให้เป็น Phase 2 หลังตรวจตัวอย่างไฟล์จริง

## 2. ประเภท Input

| Source | Examples | Handling |
|---|---|---|
| Audio upload | `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.webm` | Probe → decode → ASR |
| Browser microphone | MediaRecorder-supported audio MIME type | Permission → record → upload → ASR |
| Video upload | `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm` | Probe → select audio stream → extract → ASR |

- การรองรับขึ้นกับ **codec จริงภายใน container** ไม่ใช่นามสกุลไฟล์อย่างเดียว; ถ้าไม่มี audio stream ให้แจ้งข้อผิดพลาด `NO_AUDIO_STREAM` อย่างชัดเจน
- ไฟล์ AVI สามารถมี codec หลายชนิด; ต้องตรวจด้วย `ffprobe` และทดลอง decode ก่อนรับรองว่าใช้ได้
- สำหรับไฟล์หลาย audio tracks ให้แสดงรายการ track (index, language ถ้ามี, codec, channels) และเลือก track ได้; ค่าเริ่มต้นเลือก first usable audio track อย่างชัดเจน
- สำหรับไฟล์วิดีโอ เก็บต้นฉบับไว้เพื่อ playback; ใช้เสียงที่แยกเป็น working file สำหรับ ASR
- ค่าเริ่มต้นจำกัดไฟล์ 100 MB และ duration 2 ชั่วโมง (configurable); ไม่โหลดไฟล์ทั้งหมดเข้า RAM
- การเล่น AVI ใน HTML5 browser อาจไม่รองรับแม้ FFmpeg ถอดเสียงได้: แสดงข้อความพร้อมทางเลือกฟังเสียงที่ extract หรือสร้าง preview MP4/WebM เฉพาะเมื่อมีความจำเป็นและ resource เพียงพอ

## 3. User Experience / หน้าจอ

### 3.1 Upload / Record
- Tabs: **Upload Audio**, **Record Microphone**, **Upload Video**
- Drag-and-drop หรือ browse; แสดงชื่อ ขนาด format และ duration หลังตรวจสอบ
- สำหรับวิดีโอ แสดง available audio tracks และตัวเลือก track
- ปุ่ม Record/Stop/Play/Submit พร้อมสถานะ permission และ input level (optional)
- ตั้งชื่องานและ optional metadata: `call_id`, `source_system`, `recorded_at`

### 3.2 Job List
- ตารางชื่อ, ประเภท input, created time, duration, status, model, actions
- สถานะ `queued`, `processing`, `succeeded`, `failed`
- Retry เฉพาะงานล้มเหลว; Delete พร้อมยืนยัน

### 3.3 Transcript Detail
- Audio player หรือ Video player (เมื่อ browser รองรับ)
- รายการ segments `[start–end] text` กด timestamp เพื่อ seek
- Transcript editable; ปุ่ม Save, Reset to AI Original
- Export TXT / JSON / SRT (และ VTT หากเปิดใช้)
- แสดง model id, input track, processing duration, error/warnings
- ถ้ามี speaker labels ใน Phase 2 ต้องระบุว่ามาจาก channel mapping หรือ diarization และแก้ไขได้

### 3.4 System Status
- API health, worker heartbeat, model name, device CPU/GPU, FFmpeg availability
- ไม่แสดงค่าความแม่นยำหรือเปอร์เซ็นต์ความคืบหน้าที่ไม่ได้วัดจริง

## 4. Architecture

```text
Browser (HTML/CSS/JavaScript)
   | Upload Audio / Video / Recorded Mic
   v
FastAPI API
   | validate request + stream upload to disk
   | ffprobe metadata / create persistent job
   v
File Repository (data/jobs/<uuid>/...)
   |
   v
Single ASR Worker (persistent filesystem queue)
   | media probe -> choose audio stream -> FFmpeg extract/decode
   | preserve original and channel metadata
   | resample/convert as required by model
   | optional VAD -> faster-whisper ASR -> timestamps
   v
Transcript JSON (original) + status manifest
   |
   v
FastAPI -> Browser transcript editor -> edited revision -> TXT/JSON/SRT
```

**Separation of concerns**
- `MediaService`: upload validation, FFprobe, audio extraction, temporary files
- `JobService`: lifecycle, retries, cancellation/deletion safety
- `ASREngine`: model initialization and transcription
- `TranscriptService`: read, edit, version and export
- `JobRepository` / `TranscriptRepository`: interfaces; filesystem implementations first
- `Worker`: process queued jobs, heartbeat, crash recovery, cleanup

## 5. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic |
| Frontend | HTML/CSS/Vanilla JavaScript served from same backend |
| ASR | faster-whisper + CTranslate2 |
| Media probe / extraction | FFmpeg / FFprobe; optionally PyAV |
| Mic capture | Browser MediaRecorder API |
| Storage | Filesystem + JSON manifests; no DB in MVP |
| Queue | Single worker process with persistent filesystem job states |
| Deploy | Docker Compose with separate API and worker services |
| Testing | pytest, FastAPI TestClient, browser manual E2E checklist |

- เริ่มด้วย multilingual `small` model, CPU `int8`; ให้เปลี่ยนเป็น `medium` / `large-v3` ผ่าน config หลัง benchmark
- ใช้ NVIDIA GPU เมื่อ driver, CUDA, cuDNN และ CTranslate2 version เข้ากันจริง; ไม่สมมติว่า Apple Silicon รองรับ CUDA
- Pin dependency versions หลังตรวจการติดตั้งและ integration tests ผ่าน

## 6. Media Processing Pipeline

1. รับไฟล์ผ่าน streaming upload พร้อมขนาดสูงสุด; สร้าง UUID และเก็บ original โดยไม่ใช้ชื่อไฟล์จากผู้ใช้เป็น filesystem path
2. ตรวจ file signature/probe/decode; reject malformed file และไฟล์ไม่มี audio stream
3. ตรวจ `format`, `codec`, `duration`, `sample_rate`, `channels`, `audio stream indexes`, optional channel metadata
4. หาก video มีหลาย tracks ให้เลือกตาม user selection หรือ first usable track
5. Extract audio ด้วย FFmpeg ผ่าน subprocess **argument list** ไม่ใช้ shell interpolation; timeout, CPU/memory/disk limits ตาม environment
6. รักษาต้นฉบับและ metadata; สร้าง working audio ใน temp folder เท่านั้น
7. ตรวจ layout ของ stereo ก่อน downmix: หากทราบว่าแยก agent/customer ตาม channel ต้องเก็บข้อมูลนี้เพื่อ Phase 2
8. ทำ ASR แบบ offline, language=`th` (หรือ configurable auto detect สำหรับ use case อื่น), VAD ตามผลทดสอบ
9. เก็บ segments พร้อม `start`, `end`, `text`; อย่าสร้าง speaker identity เอง
10. สร้าง transcript และอัปเดต status แบบ atomic; ลบ temp หลังเสร็จโดยไม่ลบ original

**FFmpeg reference example** (สำหรับ track แรก, ใช้เมื่อ input ผ่าน validation แล้ว):

```bash
ffmpeg -nostdin -hide_banner -loglevel error -i input.avi -map 0:a:0 -vn -acodec pcm_s16le -ar 16000 output.wav
```

`-ac 1` ใช้ได้เฉพาะกรณีตั้งใจ downmix หลังตรวจ channel layout แล้ว; อย่า downmix ไฟล์ Call Center ที่อาจแยกสองฝ่ายโดยไม่ได้ตรวจ

## 7. API Contract (suggested)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | API health |
| `GET` | `/api/system` | model/worker/media tool status |
| `POST` | `/api/media/probe` | validate temporary upload / inspect audio tracks (optional, avoid duplicate large uploads) |
| `POST` | `/api/jobs` | upload file or mic recording, create job; return `202` and job_id |
| `GET` | `/api/jobs` | list jobs |
| `GET` | `/api/jobs/{job_id}` | job status and metadata |
| `GET` | `/api/jobs/{job_id}/transcript` | original and edited transcript |
| `PUT` | `/api/jobs/{job_id}/transcript` | save reviewed transcript with revision conflict detection |
| `GET` | `/api/jobs/{job_id}/media` | authorized range-capable media playback |
| `GET` | `/api/jobs/{job_id}/export?format=txt` | download TXT/JSON/SRT |
| `POST` | `/api/jobs/{job_id}/retry` | retry failed job |
| `DELETE` | `/api/jobs/{job_id}` | safe delete |

- Upload API ต้องตอบเร็วโดยไม่ทำ ASR ใน HTTP request; UI polling ทุก 2–5 วินาที
- Error responses: stable code + safe user message + request/job identifier
- หาก media probe ใช้ temp upload ต้องมี cleanup และ quota; หรือทำ probe ในขั้นสร้าง job เพื่อลด upload ซ้ำ

## 8. Storage Schema

```text
data/
  jobs/
    <job_uuid>/
      manifest.json
      original.<validated_ext>
      transcript.original.json
      transcript.edited.json
      working/                # temporary only
```

`manifest.json` fields:

```json
{
  "schema_version": 1,
  "job_id": "uuid",
  "title": "Sample call",
  "input_kind": "audio|microphone|video",
  "original_filename": "call.avi",
  "media_type": "video/x-msvideo",
  "size_bytes": 0,
  "sha256": "checksum",
  "audio_stream_index": 0,
  "channels": 2,
  "duration_seconds": 0,
  "call_id": null,
  "status": "queued",
  "attempt": 0,
  "model_id": "small",
  "language": "th",
  "created_at": "ISO-8601 UTC",
  "updated_at": "ISO-8601 UTC",
  "error_code": null
}
```

`transcript.original.json` fields:

```json
{
  "schema_version": 1,
  "job_id": "uuid",
  "language": "th",
  "model_id": "small",
  "segments": [
    {"id": 1, "start": 0.5, "end": 3.2, "text": "สวัสดีครับ"}
  ],
  "full_text": "สวัสดีครับ",
  "created_at": "ISO-8601 UTC"
}
```

- ข้อมูล JSON ด้านบนเป็น **schema example** ไม่ใช่ transcript จากการรันโมเดล
- ใช้ atomic writes, revision/version checks, path containment, and filesystem locking เพื่อป้องกัน race condition
- Timestamp ใน storage เป็น UTC; UI แสดง Asia/Bangkok
- `transcript.edited.json` ต้องมี `revision`, `edited_at` และไม่เขียนทับ AI original

## 9. Job Lifecycle / Worker

```text
queued -> processing -> succeeded
                    \-> failed -> retry -> queued
```

- Worker โหลดโมเดลเพียงครั้งเดียวต่อ process และประมวลผลทีละงานใน MVP
- เก็บ worker heartbeat, started/finished times, attempt count
- Restart แล้ว recover งานที่ worker ตาย โดยใช้ lease/lock ที่ปลอดภัย; ไม่รันงานซ้ำพร้อมกัน
- Delete งานที่ processing ต้องใช้ cancel/deferred delete เพื่อไม่ลบไฟล์ขณะ worker อ่าน
- Timeout FFmpeg และ inference configurable; แยก error ประเภท unsupported codec, corrupt file, no audio, resource exhausted, transcription failed

## 10. Security and Privacy

- Local mode bind `127.0.0.1` เป็นค่าเริ่มต้น; server mode ต้องมี HTTPS, authentication และ access control ก่อนเปิดให้ผู้อื่นใช้งาน
- Mic capture บน server ใช้ HTTPS (localhost เป็นข้อยกเว้นที่ browser รองรับ)
- จำกัด upload size, media duration, disk quota, processing concurrency และ rate limit ตาม deployment
- ห้ามใช้ user-supplied path, shell=True, หรือให้ URL ไปดึงสื่อภายนอกโดยอิสระ
- จำกัด FFmpeg/FFprobe ด้วย timeout และ resource limits; ใช้ image/dependencies ที่อัปเดตด้านความปลอดภัย
- ตรวจ path traversal, symlink, malformed media, content-type spoofing
- ไม่ log transcript, raw audio, PII หรือ secrets; redact errors
- กำหนด retention/delete policy, backup และการเข้าถึงข้อมูลให้สอดคล้องกับนโยบายองค์กรและกฎหมายที่เกี่ยวข้อง
- ใช้ไฟล์เสียง Contact Center ที่ได้รับอนุญาตเท่านั้น

## 11. Speaker Handling — Phase 2

| Actual source | Correct handling |
|---|---|
| Mono/mixed audio | ถอดตามเวลา; ไม่เดาบทบาท |
| Stereo with confirmed agent/customer channel mapping | Transcribe channels separately and merge by original timestamps; preserve overlaps |
| Mixed speech requiring separation | Evaluate optional diarization module; output Speaker A/B, not identities |

ห้ามถือว่า stereo = สองคนเสมอ และห้าม label เจ้าหน้าที่/ลูกค้าโดยไม่มี channel mapping ที่ยืนยันได้

## 12. Export

- **TXT**: full transcript UTF-8; optional timestamped lines
- **JSON**: metadata + segments + selected revision
- **SRT**: standard sequence number, `HH:MM:SS,mmm --> HH:MM:SS,mmm`, text
- **VTT (optional)**: `WEBVTT` header, dot milliseconds
- Export timestamps จาก segment ที่ได้จริง; ตรวจว่า `start <= end`, timestamps monotonic เท่าที่ข้อมูลรองรับ และรองรับ overlaps อย่างเหมาะสม
- ผู้ใช้เลือก Original AI / Edited transcript ก่อน export

## 13. Project Structure

```text
thai-asr-web/
  app/
    main.py
    api/
      health.py
      jobs.py
      transcripts.py
      media.py
    services/
      media_service.py
      job_service.py
      transcript_service.py
    asr/
      base.py
      faster_whisper_engine.py
    repositories/
      base.py
      file_repository.py
    models/
      schemas.py
    static/
      index.html
      styles.css
      app.js
  worker/
    main.py
    processor.py
  tests/
    test_media_validation.py
    test_jobs.py
    test_transcripts.py
    test_exports.py
    test_worker_recovery.py
  data/                    # gitignored
  config/
  .env.example
  .gitignore
  requirements.txt
  Dockerfile
  compose.yaml
  README.md
```

## 14. Config Variables (example)

```dotenv
APP_ENV=local
HOST=127.0.0.1
PORT=8000
DATA_DIR=./data
MAX_UPLOAD_MB=100
MAX_DURATION_SECONDS=7200
ASR_MODEL=small
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
ASR_LANGUAGE=th
WORKER_CONCURRENCY=1
FFMPEG_TIMEOUT_SECONDS=600
JOB_POLL_SECONDS=3
```

Secrets ไม่อยู่ใน repo; server deployment เพิ่ม TLS/auth settings และ storage retention policy

## 15. Implementation Phases

### Phase 1 — Working MVP (required)
1. Scaffold project, config, logging and repository interfaces
2. Media upload and FFprobe/FFmpeg validation for audio/video, including `.avi`
3. Mic recording and upload from browser
4. Durable job manifests + worker + failure/recovery
5. faster-whisper integration with real Thai audio
6. Transcript UI with timestamp seek, editing and save revisions
7. TXT/JSON/SRT exports, retry, delete, status page
8. Unit/integration tests + Docker Compose CPU + README

### Phase 2 — Contact Center specialization
1. Validate real sample formats and channel layouts
2. Channel-aware transcription when mapping is confirmed
3. Optional diarization for mixed audio after evaluation
4. Speaker label editing, metadata search, access control hardening
5. Benchmark WER/CER and real-time factor on representative Thai recordings

### Phase 3 — Future integration (not part of current build)
- Database adapter (PostgreSQL), object storage, multi-worker queue
- VoC topic/sentiment extraction as a separate downstream pipeline with independent evaluation
- Optional GPU inference profile and performance tuning

## 16. Acceptance Criteria

- [ ] Upload `.wav`, `.mp3`, `.m4a` and at least one real `.avi` sample containing supported audio codec, and get genuine Thai transcript
- [ ] Upload `.mp4` with audio, extract track and transcribe correctly
- [ ] Browser mic Record → Stop → Submit → transcript works on supported browsers
- [ ] Files without audio track fail with clear message
- [ ] Unsupported/corrupt media rejected safely; no worker crash
- [ ] HTTP upload returns job_id before ASR completes
- [ ] Worker restart preserves original files and completed transcripts; interrupted jobs recover safely
- [ ] Segment timestamps seek to relevant audio/video position where playback is supported
- [ ] Edited transcript never overwrites AI original
- [ ] TXT/JSON/SRT export valid UTF-8; SRT timing is valid
- [ ] Retry/delete behave safely during failure and processing
- [ ] CPU installation and Docker deployment documented and tested
- [ ] No external speech API calls; no fabricated transcript/progress/accuracy
- [ ] No unauthorized access to media or transcript in server deployment

## 17. Required Deliverables From Coding Agent

1. Complete source tree and all required code files
2. `README.md` with Local installation, FFmpeg install, model download, start/stop, testing and troubleshooting
3. `.env.example`, `.gitignore`, pinned dependencies after validation
4. `Dockerfile` and `compose.yaml` with persistent volumes; CPU profile required, GPU optional
5. `pytest` tests and instructions to run them
6. Manual test matrix for audio, microphone, AVI/MP4, invalid media and no-audio video
7. Honest summary of implemented vs pending features and known limitations

## 18. Suggested Execution Prompt

> Implement this Blueprint in the current repository. Start with a working end-to-end MVP that supports audio files, browser microphone recording and video files including AVI. Use FastAPI, FFmpeg/FFprobe and faster-whisper locally. Do not substitute mocked transcripts. Create the full project structure, actual API/worker/UI code, tests, Docker Compose and README. Run the tests available in the environment, report actual results, and explicitly identify any hardware/model/browser cases that could not be tested. Prioritize correctness, security, persistence and reproducibility over visual polish. Keep advanced diarization, VoC analytics and database integration out of Phase 1.
