# VAJA AI (วาจา เอไอ) · Multi-input Thai ASR

เว็บถอดเสียงภาษาไทยแบบ local ตาม `Multi_Input_Thai_ASR_Blueprint.md` Phase 1 ใช้ FastAPI + FFmpeg/FFprobe + faster-whisper ไม่มี speech API ภายนอก ไม่มีข้อความถอดเสียงจำลองในแอป

## ติดตั้งบนเครื่องอื่น (กดปุ่มเดียว ไม่ต้องใช้ cmd)

1. บนเครื่องนี้สร้างไฟล์ติดตั้ง: `.\.venv\Scripts\python -m scripts.make_package` ได้ `dist\VAJA-AI-<วันที่>.zip` (ไม่รวม `.env`, API key, งานใน `data/`, โมเดล และ `.venv`)
2. คัดลอก zip ไปเครื่องปลายทาง แตกไฟล์ไปไว้ที่ใดก็ได้ (เช่น `Documents\VAJA AI`)
3. ดับเบิลคลิก **`Install VAJA AI.cmd`** (ถ้า Windows ถามความปลอดภัยให้กด Run / เรียกใช้) แล้วกด **ติดตั้ง**

ตัวติดตั้งทำให้เองทั้งหมด: Python 3.11 ส่วนตัว (ถ้าเครื่องยังไม่มี, ไม่ต้องใช้สิทธิ์ admin), FFmpeg ในโฟลเดอร์ `tools\`, ไลบรารี, NVIDIA runtime เมื่อพบการ์ดจอ NVIDIA, `.env` เริ่มต้น (GPU หรือ CPU), ดาวน์โหลดโมเดล และไอคอน **VAJA AI** บน Desktop / Start Menu ต้องต่ออินเทอร์เน็ตระหว่างติดตั้ง บันทึกอยู่ที่ `data\logs\install.log` กดติดตั้งซ้ำได้อย่างปลอดภัย

หลังติดตั้ง ดับเบิลคลิกไอคอน **VAJA AI** โปรแกรมทำงานเบื้องหลังโดยไม่มีหน้าต่างดำและเปิดเบราว์เซอร์ให้ ปิดได้ด้วยปุ่ม **⏻ ปิดโปรแกรม** ในหน้าเว็บ หรือไอคอน **ปิด VAJA AI** ใน Start Menu (log: `data\logspi.log`, `worker.log`) ถอนการติดตั้ง: ลบไอคอนและโฟลเดอร์โปรแกรม และ `%LOCALAPPDATA%\Programs\VAJA-AI` ถ้าตัวติดตั้งลง Python ไว้

## ตั้งค่าผ่านหน้าเว็บ

เมนู **⚙ ตั้งค่า** แก้ค่าได้ทุกค่า (โมเดล, GPU/CPU, คุณภาพภาษาไทย, ขีดจำกัดไฟล์, AI วิเคราะห์, API key) พร้อมตรวจค่าก่อนบันทึก และปุ่มดาวน์โหลดโมเดลที่ตั้งไว้ ค่าที่บันทึกเก็บใน `data/settings.json` และมีผลแทน `.env` ทันทีโดยไม่ต้องรีสตาร์ท ค่าการถอดเสียงจะใช้กับงานถัดไป (worker โหลดโมเดลใหม่ให้เอง) ปุ่ม "ใช้ค่าจาก .env" ล้างค่าที่ตั้งจากหน้าเว็บ API key แสดงเป็นแบบซ่อนและแก้ได้อย่างเดียว

ค่าเริ่มโปรแกรมและค่าความปลอดภัย (`APP_ENV`, `HOST`, `PORT`, `DATA_DIR`, `MODEL_CACHE_DIR`, `API_TOKEN`, `CLAUDE_CLI_PATH`, `WORKER_CONCURRENCY`) แสดงในหน้าเว็บแบบอ่านอย่างเดียว แก้ใน `.env` แล้วเปิดโปรแกรมใหม่ ตัวกรองเสียงรับเฉพาะ filter ประมวลผลเสียงที่ปลอดภัย (เช่น highpass, dynaudnorm, loudnorm) เพราะ filter บางตัวของ FFmpeg อ่านหรือเขียนไฟล์ได้ ในโหมด server ทุกคนที่มี API_TOKEN แก้การตั้งค่าได้

## เริ่มใช้งานบน Windows (นักพัฒนา)

ต้องมี **Python 3.11**, FFmpeg และ FFprobe ใน PATH เครื่องที่ใช้พัฒนามีทั้งสามอย่างแล้ว และติดตั้ง `.venv` พร้อมดาวน์โหลด multilingual `small` ไว้ใน `data/models` แล้ว

```powershell
# สำหรับการติดตั้งใหม่
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
ffmpeg -version
ffprobe -version
.\.venv\Scripts\python -m scripts.download_model

# เปิด API + worker พร้อมกัน (Ctrl+C เพื่อหยุด)
.\.venv\Scripts\python -m scripts.run_local
# หรือ .\start.ps1 ถ้า PowerShell policy อนุญาต
```

เปิด **http://127.0.0.1:8000** ไม่จำเป็นต้อง activate virtual environment หากใช้คำสั่งด้านบน

ติดตั้ง FFmpeg บน Windows ที่ยังไม่มี: `winget install --id Gyan.FFmpeg --exact` แล้วเปิด terminal ใหม่ ตรวจทั้ง `ffmpeg -version` และ `ffprobe -version`

แยกรันสอง terminal ได้ด้วย:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
.\.venv\Scripts\python -m worker.main
```

`HOST`/`PORT` ใช้โดย launcher; เมื่อเรียก uvicorn โดยตรงให้กำหนด flags เอง หลีกเลี่ยง `--reload` สำหรับ worker และใช้ worker เดียวต่อ data directory

## Linux / Docker CPU

```bash
sudo apt-get update && sudo apt-get install -y python3.11-venv ffmpeg
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
cp .env.example .env
.venv/bin/python -m scripts.download_model
.venv/bin/python -m scripts.run_local
```

Docker Compose ต้องเป็นรุ่นที่รองรับ `env_file.required` (2.24 ขึ้นไป) ใช้ named volume `asr-data` ร่วมระหว่าง API กับ worker และเก็บ model cache ใน volume เดียวกัน:

```bash
docker compose build
docker compose run --rm worker python -m scripts.download_model
docker compose up -d
docker compose logs --tail=50 api worker
docker compose down
```

เปิด http://127.0.0.1:8000 ข้อมูลคงอยู่หลัง `down` ห้ามใช้ `down -v` หากต้องการเก็บงาน ใช้ `docker compose run --rm worker python -m scripts.download_model` อีกครั้งหลังเปลี่ยนชื่อโมเดล

Container ใช้ non-root user, จำกัด 4 CPU / RAM 4 GB, จำนวน process และพื้นที่ `/tmp` การแปลงไฟล์ยาวหรือหลาย channels อาจต้องเพิ่ม RAM/พื้นที่ทำงาน Docker runtime ยังไม่ได้ทดสอบบนเครื่องพัฒนานี้เนื่องจาก daemon ไม่ได้เปิด; ตรวจ `docker compose config --quiet` ผ่านแล้ว

## การใช้งาน

1. เลือกอัปโหลดเสียง, อัดไมโครโฟน หรืออัปโหลดวิดีโอ ใส่ชื่องานและ metadata ได้
2. ไมโครโฟนใช้ Record → Stop → ฟัง → เริ่มถอดเสียง ไม่ใช่ live streaming ต้องอนุญาตไมค์และใช้ localhost/HTTPS
3. HTTP ตอบ `202` หลังบันทึกไฟล์และ probe โดยไม่ทำ ASR ใน request สถานะจะเปลี่ยน queued → processing → succeeded/failed
   แถบความคืบหน้าในรายการงานและรายละเอียดอัปเดตทุก 3 วินาที แสดงขั้นตอนตรวจไฟล์ → เตรียมเสียง → โหลดโมเดล → ถอดเสียง → บันทึกผล ระหว่างถอดเสียง เปอร์เซ็นต์คือตำแหน่งเวลาเสียงจาก segment ล่าสุดเทียบกับความยาวเสียงที่ decode จริง ไม่ใช่เปอร์เซ็นต์เวลาประมวลผลหรือการประมาณเวลาที่เหลือ ช่วงโหลดโมเดล/VAD/ช่วงเงียบอาจแสดงแถบรอข้อมูลหรือขยับเป็นช่วง ๆ งานสำเร็จจึงแสดงว่าเสร็จแล้ว Retry และ recovery จะเริ่มข้อมูล progress ใหม่
4. หลาย audio tracks: งานจะอยู่ `queued / awaiting_track` จนเลือก track และกดเริ่ม ไม่มีการอัปโหลดซ้ำ Single-track เริ่มอัตโนมัติ ค่าเริ่มต้นเลือก track แรก; ถ้าถอดรหัสไม่ได้ worker จะลอง track ถัดไป ยกเว้นผู้ใช้เลือกเอง
5. เปิดงาน กด timestamp เพื่อ seek แก้เฉพาะข้อความแล้ว Save จะสร้าง revision ใหม่ AI original และสื่อต้นฉบับยังอยู่ Reset สร้าง revision ใหม่จากต้นฉบับ
6. เลือก AI ต้นฉบับหรือฉบับตรวจทาน แล้วดาวน์โหลด TXT/JSON/SRT/VTT/CSV Export ใช้ข้อมูลที่บันทึกแล้ว ถ้ามีการแยกผู้พูด ทุกไฟล์จะมีชื่อผู้พูด (TXT/SRT `ชื่อ: ข้อความ`, VTT `<v ชื่อ>`) CSV มี 1 แถวต่อช่วงเวลา: ลำดับ, เวลาเริ่ม, เวลาจบ, วินาที, ผู้พูด, ข้อความ (UTF-8 BOM เปิดใน Excel เป็นภาษาไทยได้)
7. Retry ได้เฉพาะ failed; Delete ขอการยืนยันใน UI งาน processing จะรอลบจน worker หยุดอ่านไฟล์ ส่วนไฟล์ที่กำลังส่ง playback จะตอบ `MEDIA_BUSY` ให้ลองใหม่

AVI และ codec บางชนิดเล่นใน browser ไม่ได้ ใช้ปุ่มฟังเสียงที่แยกแล้วหลังงานสำเร็จ เก็บ `playback.wav` แบบรักษา channels ไว้สำหรับ playback; `working/` ถูกลบหลังประมวลผล ASR ผสม channels เป็น mono ภายใน faster-whisper พร้อมคำเตือน; ไม่เดาว่า stereo คือผู้พูดสองคน การแยกผู้พูดดูหัวข้อ **แยกผู้พูด** ด้านล่าง

## โมเดลและ config

ดู [.env.example](.env.example) ค่าเริ่มต้น: `small`, CPU/int8, language `th`, VAD เปิด, สูงสุด 100 MB / 2 ชั่วโมง

`MODEL_LOCAL_FILES_ONLY=true` ป้องกัน worker ดาวน์โหลดโมเดลระหว่างถอดเสียง ต้องดาวน์โหลด weights ก่อนด้วย script ซึ่งดาวน์โหลดเฉพาะโมเดล ไม่เปิดหรือส่งไฟล์เสียงของผู้ใช้ หลังดาวน์โหลดแล้วการประมวลผลไม่ต้องใช้อินเทอร์เน็ต เปลี่ยนเป็น `medium`/`large-v3` ต้องดาวน์โหลดใหม่และประเมินทรัพยากรใหม่

`ASR_TIMEOUT_SECONDS` รวมเวลาเริ่มโมเดลและ inference; inference ทำใน child process แบบ persistent โหลดโมเดลครั้งเดียวต่อ child และ terminate เมื่อเกินเวลา Heartbeat แยกจาก inference/FFmpeg

`DISK_QUOTA_MB` จำกัดไฟล์งาน รวม original/preview/revisions/working แต่ไม่รวม model cache คำนวณก่อนรับ chunks และก่อน extraction ต้องเผื่อ disk สำหรับ multipart temporary spool ซึ่งใช้ OS temp จำกัด request body ด้วย Content-Length (ไม่รับ chunked upload) ค่า quota เป็น admission check ไม่ใช่ filesystem hard quota; server ควรใช้ volume quota และ proxy request limits ด้วย

`FFMPEG_TIMEOUT_SECONDS` จำกัด probe/extract, `MAX_DURATION_SECONDS` ตรวจทั้ง metadata และ decoded audio จำกัดไม่เกิน 8 channels ต่อ track ไม่รองรับ playlists หรือ URL inputs เลือก format จาก ffprobe จริง ไม่เชื่อ MIME ที่ client ส่ง

GPU เป็น optional และยังไม่มี Docker GPU profile ที่ทดสอบแล้ว สำหรับ Windows NVIDIA ติดตั้ง runtime ใน virtual environment ด้วย `.\.venv\Scripts\python -m pip install -r requirements-gpu-windows.txt` แล้วใช้ค่าใน `.env.gpu.example` ตัวแอปค้นหา DLL จาก NVIDIA wheels ให้อัตโนมัติ ไม่แก้ PATH ของ Windows ทั้งเครื่อง ดูความเข้ากันได้ที่ [เอกสาร faster-whisper](https://github.com/SYSTRAN/faster-whisper#gpu) ไม่รองรับ CUDA บน Apple Silicon

### ความแม่นยำภาษาไทย (โปรไฟล์ GPU)

`small` ถอดเสียงโทรศัพท์ 8 kHz ได้ไม่ดี: วนซ้ำ ("สวัสดีครับ" ซ้ำทั้ง segment), ข้ามประโยค และสะกดคำผิดมาก โปรไฟล์ `.env.gpu.example` จึงใช้:

- **Thonburian Whisper large-v3** (`Vinxscribe/biodatlab-whisper-th-large-v3-faster`) โมเดล fine-tune ภาษาไทย ต้องตั้ง `ASR_TIMESTAMPS=false` (ไม่ได้ฝึก timestamp tokens) และ `ASR_CHUNK_LENGTH=10`
- `ASR_AUDIO_FILTER` กรอง/ปรับระดับเสียงเฉพาะสำเนาที่ส่งให้โมเดล `playback.wav` ยังเป็นเสียงเดิม
- `ASR_REPETITION_PENALTY` + `ASR_COLLAPSE_REPEATS` หยุดและยุบข้อความวนซ้ำ (ไม่ยุบตัวเลขเช่น 1,000,000)
- Thonburian บางครั้งพิมพ์ข้อความที่จำมาจากข้อมูลฝึก (เช่น "วิเคราะห์บอล บอลเต็ง") แทนเสียงจริง segment ที่มี `ASR_HALLUCINATION_MARKERS` จะถอดใหม่เฉพาะช่วงเวลานั้นด้วย `ASR_FALLBACK_MODEL` (large-v3-turbo) ถ้าไม่ตั้ง fallback จะเว้นช่วงนั้นว่างแทนการใส่ข้อความผิด
- `ASR_INITIAL_PROMPT` / `ASR_HOTWORDS` ใส่คำศัพท์เฉพาะงานได้ (optional)

ดาวน์โหลดทั้งสองโมเดลด้วย `python -m scripts.download_model` (อ่าน `ASR_MODEL` และ `ASR_FALLBACK_MODEL`) ใช้ VRAM รวมราว 5–6 GB ผลการเปรียบเทียบอยู่ใน [docs/PERFORMANCE.md](docs/PERFORMANCE.md) ยังไม่มี reference transcript จึงยังไม่ได้วัด WER/CER

### ปรับความเร็วสำหรับไฟล์ยาว

- เปลี่ยนจาก CPU เป็น CUDA/float16 เมื่อทดสอบว่า GPU และ runtime ใช้ได้จริง โดยคงโมเดล `small` และ `ASR_BEAM_SIZE=5` ไว้ก่อน
- `ASR_BATCH_SIZE=1` ใช้เส้นทางเดิม; ตั้ง `8` เพื่อใช้ BatchedInferencePipeline ซึ่งใช้ VRAM เพิ่มและอาจเปลี่ยนการแบ่งช่วง/ผลถอดเสียง ต้องตรวจคุณภาพกับไฟล์จริง
- `ASR_BEAM_SIZE=1` ลดการค้นหาคำตอบเพื่อเน้นเร็ว แต่ผลถอดเสียงอาจเปลี่ยน ควรเปรียบเทียบกับ beam 5 ก่อนเลือกใช้
- ใช้ VAD เพื่อลดช่วงไม่มีเสียงพูด และเก็บ worker ทำงานไว้เพื่อใช้โมเดลที่โหลดแล้วซ้ำ
- เปลี่ยนโมเดลเป็น `base`/`tiny` ได้แต่ต้องดาวน์โหลดและประเมินความแม่นยำภาษาไทยใหม่ อย่าเปลี่ยนเป็นโมเดล `.en` สำหรับภาษาไทย

วัดเวลาบนไฟล์ที่ได้รับอนุญาตโดยไม่พิมพ์ข้อความถอดเสียง:

```powershell
.\.venv\Scripts\python -m scripts.benchmark_asr 'C:\path\call.avi' --device cpu --seconds 60 --report data/benchmarks/cpu.json
.\.venv\Scripts\python -m scripts.benchmark_asr 'C:\path\call.avi' --device cuda --seconds 60 --report data/benchmarks/gpu.json
.\.venv\Scripts\python -m scripts.benchmark_asr 'C:\path\call.avi' --device cuda --batch-size 8 --seconds 60 --report data/benchmarks/gpu-batch8.json
```

รายงานแยกเวลาสกัดเสียง โหลดโมเดล และถอดเสียง ค่า real-time factor คือเวลาถอดเสียง / ความยาว sample; ค่ายิ่งต่ำยิ่งเร็ว ผล sample สั้นไม่ใช่การรับประกันเวลาทั้งไฟล์ หลังเปลี่ยน `.env` ต้องหยุดและเริ่ม worker ใหม่ config ที่ใช้จริงจะเก็บใน manifest ของงานแต่ละ attempt

ผลทดลองบนไฟล์ตัวอย่างของผู้ใช้และ RTX 5050 อยู่ใน [docs/PERFORMANCE.md](docs/PERFORMANCE.md) โปรไฟล์ `.env` ของเครื่องพัฒนาตั้งเป็น CUDA/float16 + batch 8 แล้ว ส่วนค่าเริ่มต้นใน `.env.example` ยังคงใช้ CPU สำหรับการติดตั้งทั่วไป

## แยกผู้พูด

หลังถอดเสียง worker แยกผู้พูดจาก **เสียง** ในเครื่อง (sherpa-onnx: pyannote segmentation 3.0 + NeMo TitaNet-small ประมาณ 45 MB, CPU, ไม่ส่งข้อมูลออก; เลือกจากการเทียบ 5 โมเดลกับเสียงโทรศัพท์ 8 kHz จริง) แต่ละช่วงจะได้ป้าย `ผู้พูด 1`, `ผู้พูด 2` …

- โมเดลดาวน์โหลดพร้อมตัวติดตั้ง หรือกด **ดาวน์โหลด** ในหน้า **⚙ ตั้งค่า > แยกผู้พูด** ถ้ายังไม่มีโมเดล งานจะสำเร็จตามปกติพร้อมคำเตือน
- ตั้งค่า: เปิด/ปิด, จำนวนผู้พูด (2 = สายสนทนา, 0 = นับเอง), ความไว
- งานเก่าที่ถอดเสียงไว้แล้ว: เปิดงานแล้วกด **แยกผู้พูด** ผลบันทึกเป็น revision ใหม่ (AI ต้นฉบับไม่ถูกแก้)
- ตรวจทาน: แก้ชื่อผู้พูด (เช่น ผู้พูด 1 → เจ้าหน้าที่) ซึ่งเปลี่ยนทุกช่วงพร้อมกัน และเปลี่ยนผู้พูดรายช่วงได้ แล้วกดบันทึก
- ถ้าใช้ **AI วิเคราะห์ข้อความ** ระบบจะบอกว่าเสียงไหนคือเจ้าหน้าที่/ลูกค้า ปุ่ม "ใช้คำแก้ไขและชื่อผู้พูด" ตั้งชื่อให้อัตโนมัติ
- ข้อจำกัด: ป้ายผู้พูดเป็นรายช่วงของ ASR; ถ้าช่วงเดียวมีคนพูดสองคน (พบบ่อยกับช่วง 10 วินาทีของ Thonburian) จะได้ป้ายของคนที่พูดนานกว่า เสียงโทรศัพท์ 8 kHz และเสียงพูดซ้อนกันทำให้แยกได้ไม่แม่น ควรตรวจทานก่อนใช้งาน

## วิเคราะห์ข้อความด้วย AI (Local หรือ Claude)

หลังถอดเสียงเสร็จ หน้ารายละเอียดงานมีส่วน **วิเคราะห์ข้อความ** ใช้ได้ 4 อย่างในการเรียกครั้งเดียว คือ แก้คำผิด, สรุปบทสนทนา, วิเคราะห์ความรู้สึกลูกค้า และจัดหมวดหัวข้อ เลือกได้ว่าจะประมวลผลด้วยอะไร:

| ตัวเลือก | ค่าใน `ANALYSIS_PROVIDERS` | ข้อมูลออกนอกเครื่อง | สิ่งที่ต้องมี |
|---|---|---|---|
| Local LLM (Ollama) | `ollama` | ไม่ออก | ติดตั้ง/เปิด [Ollama](https://ollama.com) แล้ว `ollama pull qwen3:8b` (หรือโมเดลภาษาไทยอื่น ตั้งใน `OLLAMA_MODEL`) |
| Claude Code | `claude_cli` | ข้อความ transcript ส่งไป Anthropic | ติดตั้ง Claude Code และ login แล้ว (รัน `claude` ใน terminal หนึ่งครั้ง) ใช้สิทธิ์ subscription เดิม |
| Claude API | `claude_api` | ข้อความ transcript ส่งไป Anthropic | `ANTHROPIC_API_KEY` ใน `.env` (หรือ `ant auth login`) คิดค่าใช้จ่ายตาม token |

- **ปิดไว้เป็นค่าเริ่มต้น** เปิดได้ในหน้า **⚙ ตั้งค่า > AI วิเคราะห์ข้อความ** (หรือ `ANALYSIS_PROVIDERS` ใน `.env`)
- ส่งเฉพาะข้อความ segment (id + text) ไม่ส่งไฟล์เสียงหรือ manifest; ตัวเลือกที่ส่งออกนอกเครื่องจะถามยืนยันก่อนทุกครั้ง
- Claude Code รันแบบ headless (`claude -p`) ในโฟลเดอร์ว่างชั่วคราว ปิด tools, MCP และไม่บันทึก session
- ผลเก็บที่ `data/jobs/<id>/analysis.json` ไม่แก้ transcript อัตโนมัติ; กด **ใช้คำแก้ไขทั้งหมด** เพื่อบันทึกเป็น revision ใหม่ (AI ต้นฉบับยังอยู่) ถ้าข้อความถูกแก้หลังวิเคราะห์ ระบบจะไม่ให้ใช้คำแก้ไขจนกว่าจะวิเคราะห์ใหม่
- ปรับโมเดล: `CLAUDE_CLI_MODEL` (เช่น `opus`, `sonnet`), `CLAUDE_API_MODEL` (ค่าเริ่มต้น `claude-opus-5-5`), `CLAUDE_EFFORT`, `OLLAMA_NUM_CTX`, `ANALYSIS_TIMEOUT_SECONDS`
- การวิเคราะห์ทำใน thread ของ API process ถ้า API ถูกปิดระหว่างทำงาน สถานะจะเปลี่ยนเป็น `ANALYSIS_INTERRUPTED` หลังหมดเวลา ให้กดวิเคราะห์ใหม่

## API

| Method | Endpoint | หน้าที่ |
|---|---|---|
| GET | `/api/health`, `/api/system` | API, heartbeat, model config, media tools |
| POST | `/api/jobs` | multipart file/title/input_kind/call_id/source_system/recorded_at |
| GET | `/api/jobs`, `/api/jobs/{id}` | รายการ / รายละเอียด |
| PUT | `/api/jobs/{id}/track?index=N` | เลือก absolute stream index และปล่อยงานหลาย tracks เข้าคิว |
| POST | `/api/jobs/{id}/retry?index=N` | retry failed; index optional |
| DELETE | `/api/jobs/{id}` | ลบหรือ deferred delete |
| GET/PUT | `/api/jobs/{id}/transcript` | original/edited/revision; PUT `{revision,segments,reset}` |
| GET | `/api/jobs/{id}/media?audio=true` | range-capable original หรือ extracted WAV |
| GET | `/api/jobs/{id}/export?format=csv&version=edited` | TXT/JSON/SRT/VTT/CSV; version original/edited |
| GET/POST | `/api/jobs/{id}/speakers` | สถานะ / แยกผู้พูดให้งานที่ถอดเสียงแล้ว (บันทึกเป็น revision ใหม่) |
| GET/PUT | `/api/settings` | รายการตั้งค่าทั้งหมด / `{values, reset}` บันทึกค่าจากหน้าเว็บ |
| POST | `/api/settings/models/download` | `{name}` ดาวน์โหลดโมเดลที่ตั้งไว้ |
| POST | `/api/shutdown` | ปิดโปรแกรม (เฉพาะเมื่อเปิดผ่านไอคอน VAJA AI) |
| GET | `/api/analysis/providers` | ตัวเลือกวิเคราะห์ที่เปิดไว้และความพร้อม |
| GET/POST | `/api/jobs/{id}/analysis` | อ่านผล / เริ่มวิเคราะห์ `{provider}` (ollama, claude_cli, claude_api) |
| POST | `/api/jobs/{id}/analysis/apply` | `{revision}` ใช้คำแก้ไขเป็น revision ใหม่ |

Error มี stable `code`, ข้อความปลอดภัย และ request ID ไม่ส่ง decoder stderr, request validation values หรือ transcript เข้า logs System endpoint รายงาน model config และ worker heartbeat; heartbeat ไม่ได้รับรองว่า model cache สมบูรณ์จนกว่าจะโหลดโมเดลสำเร็จ

## Persistence / recovery / privacy

เก็บ `data/jobs/<uuid>/manifest.json`, `original.<ext>`, `playback.wav`, `transcript.original.json`, `transcript.edited.json` และ `transcript.revision.N.json` ใช้ atomic replace + fsync ไฟล์, OS filesystem locks, revision conflict detection และ singleton worker lock เก็บ UTC และแสดง UI เป็น Asia/Bangkok

หลัง worker หยุดกะทันหัน งาน processing กลับเข้าคิวเมื่อ restart; งานรอลบถูกลบ; orphan inference มี parent monitor และ inference lock ก่อน cleanup เสร็จงานแล้วไม่ถอดซ้ำ อัปโหลดที่ยังไม่ publish manifest ถูก cleanup เมื่อ worker restart หลังแน่ใจว่าไม่มี uploader กำลังทำงาน File locks ควรใช้ local disk; ไม่รองรับ distributed/NFS multi-worker

Local bind `127.0.0.1` และ Compose publish เฉพาะ loopback ไม่มี external fonts/analytics/CDN สื่อและ transcript ไม่ถูกส่งออกไป ASR ภายนอก ปิด access logs เพื่อไม่เก็บ identifiers ใน URL ไม่มี automatic retention deletion: ผู้ใช้ลบผ่าน UI/API; backup และ volume retention เป็นหน้าที่ผู้ดูแล การลบไม่รับประกัน secure erase หรือการลบจาก backup

ก่อนให้ผู้อื่นใช้ ตั้ง `APP_ENV=server`, `API_TOKEN` สุ่มอย่างน้อย 32 ตัวอักษร และ HTTPS reverse proxy Browser ใช้ HTTP Basic username **vaja**, password คือ API_TOKEN ทุกเส้นทางรวม static/media/export ต้อง authenticate และ mutation ตรวจ same-origin ตั้ง proxy ให้ส่ง host/proto ที่ถูกต้อง, จำกัด trusted proxy IP, body size/rate/concurrency และปิด logs ที่มีข้อมูลส่วนตัว Basic auth นี้เป็นพื้นที่ร่วมของผู้ได้รับ token ไม่มีบัญชีแยกหรือ per-user ACL; ห้ามใช้เป็น multi-tenant service

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m pip check
node --check app/static/app.js
docker compose config --quiet

# ทดสอบโมเดลจริงจาก cache
$env:RUN_MODEL_TESTS='1'
.\.venv\Scripts\python -m pytest -q tests/test_real_model.py

# E2E โมเดลจริงครบ WAV/MP3/M4A/AVI/MP4 จากไฟล์ไทยที่ได้รับอนุญาต
$env:THAI_SAMPLE='C:\path\to\thai.wav'
.\.venv\Scripts\python -m pytest -q tests/test_real_model.py
```

บน Linux ใช้ `RUN_MODEL_TESTS=1 THAI_SAMPLE=/path/thai.wav .venv/bin/python -m pytest -q` Test lifecycle ใช้ **test double ใน tests เท่านั้น** ไม่ใช่ transcription engine ของแอป ส่วน `test_real_model.py` เรียก faster-whisper จริง รายละเอียดผลและขอบเขตที่ยังไม่ได้ตรวจอยู่ใน [docs/VALIDATION.md](docs/VALIDATION.md) และ [docs/MANUAL_TEST_MATRIX.md](docs/MANUAL_TEST_MATRIX.md)

## Troubleshooting

- `FFMPEG_MISSING`: ตรวจ PATH ของ process ที่รันทั้ง API และ worker แล้วเปิด terminal ใหม่
- งานค้าง queued: ตรวจ worker heartbeat, อย่ารัน worker ซ้ำ และเลือก track หากเป็น awaiting_track
- `TRANSCRIPTION_FAILED`: ดาวน์โหลด model ตาม config ให้ครบ ตรวจ RAM, device/compute type และสิทธิ์อ่าน cache ไม่ใช้ transcript จำลองแทน
- `MEDIA_TIMEOUT` / `ASR_TIMEOUT`: ลดความยาวไฟล์หรือเพิ่ม timeout โดยอิงเวลาที่วัดจริง
- `NO_AUDIO_STREAM`: วิดีโอไม่มีเสียง ต้องใช้ไฟล์ที่มี audio track
- `REVISION_CONFLICT`: โหลดรายละเอียดงานใหม่ก่อนแก้ต่อ งานจากอีกหน้าต่างถูกบันทึกแล้ว
- ไมค์ไม่ได้รับอนุญาต: ตรวจ site permission, HTTPS/localhost และ browser MediaRecorder support
- `PermissionError` ที่ Windows multiprocessing Pipe: environment sandbox อาจบล็อก named pipes ให้รันบน terminal ปกติที่มีสิทธิ์สร้าง local processes

Dependencies ทั้งหมดถูก pin หลังติดตั้งบน Python 3.11 Windows และตรวจ `pip check` แล้ว Linux image ยังต้องผ่าน build/runtime test ก่อนนำไป deploy จริง Phase 2 channel mapping, benchmark WER/CER/DER และ Phase 3 analytics/database ยังไม่อยู่ใน build นี้
