# Local performance check — 15 October 2026

ตรวจไฟล์ AVI ที่ผู้ใช้ให้เป็นตัวอย่าง: ความยาว 1122.08 วินาที (18:42), ขนาด 103,545,058 bytes, video codec msrle, audio PCM s16le 8 kHz mono อยู่ absolute stream index 1

เครื่องมี NVIDIA GeForce RTX 5050 Laptop GPU ประมาณ 8 GB VRAM การตั้งค่าเดิมใช้ CPU/int8, small, beam 5 และ 4 CPU threads ทดลอง CUDA ครั้งแรกพบขาด `cublas64_12.dll` จึงติดตั้ง runtime แบบ optional ใน `.venv` และเพิ่มการค้นหา DLL ใน process ของแอป

## ผลวัดจากเสียง 60 วินาทีแรก

| Configuration | Extract | Model load | Transcription | Segments |
|---|---:|---:|---:|---:|
| CPU / int8 / small / beam 5 / batch 1 | 0.117 s | 1.923 s | 307.739 s | 0 |
| CUDA / float16 / small / beam 5 / batch 1 | 0.209 s | 3.274 s | 73.613 s | 0 |
| CUDA / float16 / small / beam 5 / batch 8 | 0.041 s | 1.850 s | 46.209 s | 2 |
| CUDA / float16 / small / beam 1 / batch 8 | 0.051 s | 2.274 s | 49.649 s | 2 |

GPU แบบเดิมเร็วกว่า CPU ประมาณ 4.2 เท่า; batch 8 ประมาณ 6.7 เท่าใน sample นี้ สกัดเสียงใช้เวลาน้อยเมื่อเทียบกับ inference ขนาดวิดีโอจึงไม่ใช่คอขวดหลักของการทดสอบนี้

ข้อมูลวัดอยู่ `data/benchmarks/` และไม่มีข้อความถอดเสียงในรายงาน การทดสอบ CPU และ GPU บางช่วงมีเวลาทับซ้อนกัน จึงเป็นตัวเลขใช้งานเบื้องต้น ไม่ใช่ benchmark แบบควบคุมสภาวะ ต้องวัดซ้ำกับโหลดเครื่องและ power mode เดียวกันเพื่อเทียบละเอียด

Batch pipeline ให้จำนวน segments ต่างจาก standard แม้ใช้ model/beam เท่ากัน ไม่ได้รับรองความแม่นยำเท่ากัน ยังไม่มี reference transcript สำหรับตัวอย่างนี้และยังไม่ได้วัดไฟล์เต็ม 18:42 จึงไม่รับประกันเวลาทั้งไฟล์หรือคุณภาพจาก sample 60 วินาทีนี้ ไม่พิมพ์เสียงหรือข้อความของผู้ใช้ลง logs และไม่มีการส่งสื่อไปบริการภายนอก

ลด beam เป็น 1 ไม่ได้เร็วกว่า beam 5 ในการวัดครั้งนี้ จึงคง beam 5 ไว้ ตรวจชุดทดสอบทั่วไปผ่าน 35 รายการ (2 model tests เป็น opt-in) และเปิด GPU/batch 8 ทดสอบโมเดลจริงผ่านอีก 2 รายการ รวม worker subprocess และ public Thai sample ใน WAV/MP3/M4A/AVI/MP4; `pip check` ผ่าน

## ค่าที่ตั้งให้เครื่องนี้

`.env` ใช้ `ASR_DEVICE=cuda`, `ASR_COMPUTE_TYPE=float16`, `ASR_MODEL=small`, `ASR_BEAM_SIZE=5`, `ASR_BATCH_SIZE=8` หลังแก้ config ให้หยุดและเริ่ม API/worker ใหม่ งานที่เสร็จแล้วไม่ถูกประมวลผลซ้ำเอง ต้องอัปโหลดใหม่หากต้องการทดลอง settings ใหม่

หากต้องการใช้เส้นทางถอดเสียงมาตรฐาน ให้เปลี่ยน `ASR_BATCH_SIZE=1` หากต้องการเน้นความเร็วเพิ่ม ทดลอง `ASR_BEAM_SIZE=1` แล้วเทียบคุณภาพข้อความก่อนใช้จริง ลด CPU/GPU workload อื่น และใช้โหมดพลังงานที่เหมาะสมของเครื่องระหว่างวัดผล

ใช้ `scripts.benchmark_asr` ตาม README เพื่อวัดไฟล์อื่น รายงานแยก extract/load/inference และไม่บันทึก transcript ในรายงาน ใช้ `requirements-gpu-windows.txt` สำหรับเครื่อง Windows NVIDIA ใหม่; CPU dependencies และ Docker CPU ยังแยกจาก runtime GPU นี้

## ความแม่นยำภาษาไทย — 15 October 2026 (ไฟล์ AVI เดียวกัน, RTX 5050, ตรวจด้วยสายตา ไม่มี reference)

| Configuration | ผล 4 นาทีแรก | ไฟล์เต็ม 18:42 |
|---|---|---|
| small / batch 8 (เดิม) | segment ยาว 30 s, วนซ้ำ "สวัสดีครับ"/"คือ..."/"ค่อย", ค่าไฟ → "ข้าวไฟ/ค้าไฟ" | 54 s, 34 segments, 4 segments วนซ้ำ |
| small + timestamps + repetition fix | ไม่วนซ้ำ แต่ข้ามประโยคและสะกดผิดมาก | — |
| large-v3-turbo + filter | ไม่ hallucinate, คำผิดปานกลาง ("ข้าไฟ", "การใส่ฟ้า") | — |
| Pathumma large-v3 (s2p2 CT2) | แปลเป็นภาษาอังกฤษแทนถอดเสียง — ใช้ไม่ได้ | — |
| Thonburian large-v3, 30 s chunks | ข้อความจำจากข้อมูลฝึกแทบทั้งไฟล์ | — |
| **Thonburian + filter + 10 s chunks + turbo fallback** | ประโยคครบ คำศัพท์ถูกเกือบทั้งหมด (ค่าไฟ, การไฟฟ้า, มิเตอร์, 6,900/7,800 บาท) | **266 s, 108 segments, 0 hallucination** |

ยังมีคำผิดบางจุด (เช่น "รอบวิญญาณ" แทน "รอบบิล") และตัวเลขที่ฟังผิดได้ ควรตรวจทานก่อนใช้จริง
