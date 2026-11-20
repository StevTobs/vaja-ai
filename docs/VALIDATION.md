# Verification record — 15 October 2026

บันทึกนี้เป็นผล Phase 1 ก่อนปรับความเร็ว ผล GPU และ batch pipeline ที่ทดสอบเพิ่มเติมภายหลังอยู่ใน [PERFORMANCE.md](PERFORMANCE.md)

สภาพแวดล้อม: Windows, Python 3.11, FFmpeg/FFprobe 8.1.2, CPU/int8, faster-whisper 1.2.1 และ CTranslate2 4.8.3 โมเดล multilingual `small` cache revision `536b0662742c02347bc0e980a01041f333bce120`

## ผลที่ตรวจจริง

- ชุดทดสอบปกติ: **30 passed, 2 skipped** โดย 2 รายการที่ skip เป็นการทดสอบโมเดลจริงแบบ opt-in
- ชุดทดสอบครบโดยเปิด `RUN_MODEL_TESTS=1` และ `THAI_SAMPLE`: **32 passed in 19.07s** รวม silence inference และ Thai E2E ทั้ง WAV/MP3/M4A/AVI/MP4
- Thai E2E ทดสอบ HTTP upload ผ่าน TestClient → durable job → persistent model child process → faster-whisper จริง → transcript ภาษาไทยพร้อม segments → SRT export ตัวเดียวกันถูกแปลงด้วย FFmpeg เป็นแต่ละ container; ไม่ใช่ชุดไฟล์ contact-center จากหลายแหล่ง
- WAV, MP3/libmp3lame, M4A/AAC, FLAC, OGG/Opus, WebM/Opus decode ผ่าน FFmpeg
- AVI/mpeg4+PCM และ MP4/mpeg4+AAC: audio อยู่ absolute stream index 1 และแยกได้ถูกต้อง
- ตรวจ no-audio video, corrupt media, upload/duration limits, multi-track selection และ stereo channel preservation
- ตรวจ UUID/path containment, server auth ทุกเส้นทาง, same-origin mutation, range playback และ media lock ก่อนลบ
- ตรวจ queue/retry/deferred delete, singleton worker lock, interrupted manifest recovery, revision conflict, immutable original และ recovery หลังเขียน revision แต่ยังไม่อัปเดต pointer
- `python -m pip check`: No broken requirements found
- `node --check app/static/app.js`: ผ่าน
- `docker compose config --quiet`: ผ่าน
- รัน API และ worker เป็น process จริงบน `127.0.0.1:18080`: HTML, JS, CSS, health ตอบ HTTP 200 และ worker heartbeat ออนไลน์; หยุด process และลบข้อมูลทดสอบหลังตรวจแล้ว

ตัวอย่างภาษาไทยสาธารณะ: [PyThaiASR Common Voice fixture](https://github.com/PyThaiNLP/pythaiasr/blob/main/tests/common_voice_th_25686161.wav) ดาวน์โหลดมาไว้ `data/samples/common_voice_th_25686161.wav` สำหรับการตรวจ local เท่านั้น ไม่ฝังใน source, UI หรือผลลัพธ์งานของผู้ใช้ ไม่มีการส่งเสียงกลับไปยัง GitHub/Hugging Face

การดาวน์โหลดโมเดลและ sample ต้องใช้อินเทอร์เน็ต แต่ inference รัน local โดย `local_files_only=true` การทดสอบด้วย named pipes ของ Windows ต้องรันนอก sandbox ที่บล็อก `multiprocessing.Pipe`; ข้อจำกัดดังกล่าวไม่ใช่ข้อผิดพลาดของการถอดเสียง

## ยังไม่ได้ตรวจ / ไม่รับรอง

- การกดปุ่มและ permission จริงบน Chrome/Edge/Firefox/Safari, mic device จริง, timestamp seek และ video rendering ใน browser
- Linux image build / Docker runtime เพราะ Docker Desktop daemon ไม่ทำงานในเครื่องนี้
- GPU/CUDA/cuDNN, ไฟล์ contact-center จริง, codec อื่นใน AVI, เสียงสองชั่วโมง และ benchmark WER/CER
- Reverse proxy HTTPS และ load/rate-limit deployment; auth ผ่าน automated API tests เท่านั้น
- Hard-kill worker ระหว่าง native inference และ power-loss durability; ตรวจ recovery จาก manifest interruption แล้ว

การมีข้อความภาษาไทยจากตัวอย่างเดียวเป็น smoke test การทำงาน ไม่ใช่การรับรองความถูกต้องของ transcript ต้องตรวจทานและ benchmark บนข้อมูลที่ได้รับอนุญาตก่อนใช้จริง
