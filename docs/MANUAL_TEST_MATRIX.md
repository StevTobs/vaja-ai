# Manual acceptance matrix

ใช้ไฟล์ที่ได้รับอนุญาตเท่านั้น หน้าเว็บอยู่ http://127.0.0.1:8000 API และ worker ต้องทำงานพร้อมกัน

| กรณี | ขั้นตอน | ผลที่ต้องได้ | การตรวจใน session นี้ |
|---|---|---|---|
| WAV / MP3 / M4A ภาษาไทย | อัปโหลดแล้วเปิดงาน | 202 ก่อน inference, genuine Thai segments และ export | ผ่าน API + โมเดลจริงครบ 3 รูปแบบ |
| AVI mpeg4 + PCM | อัปโหลด AVI | ffprobe index ถูกต้อง, ถอดเสียงจริง, ฟัง extracted WAV | ผ่าน API + โมเดลจริง; browser playback ยังต้องตรวจ |
| MP4 mpeg4 + AAC | อัปโหลด MP4 | extract audio และถอดเสียงจริง | ผ่าน API + โมเดลจริง; codec นี้ browser บางตัวเล่นวิดีโอไม่ได้ |
| วิดีโอไม่มีเสียง | อัปโหลด MP4 ไม่มี audio | NO_AUDIO_STREAM | ผ่าน FFmpeg integration |
| ไฟล์เสีย / MIME ปลอม | ใช้ไฟล์ text เปลี่ยนนามสกุลเป็น wav | safe error ไม่มี raw stderr | ผ่าน automated test |
| หลาย tracks | อัปโหลด MKV 2 tracks | งานรอเลือก track; ไม่มี upload ซ้ำ | ผ่าน API integration |
| Mic Chrome/Edge Windows | อนุญาต → Record → Stop → Play → Submit | transcript จริง, ปิด mic track หลัง stop | ยังไม่ทดสอบผ่าน browser |
| Mic Firefox | อัด OGG/WebM ตาม MIME ที่รองรับ | ส่งและ decode สำเร็จ | ยังไม่ทดสอบผ่าน browser |
| Mic Safari | อัด audio/mp4 ถ้ารองรับ | ส่งเป็น m4a และถอดเสียง | ยังไม่ทดสอบผ่าน browser |
| Mic permission denied / HTTP remote | ปฏิเสธ permission / insecure origin | ข้อความเข้าใจได้ ไม่มี recording ค้าง | ยังไม่ทดสอบผ่าน browser |
| Timestamp seek | กดเวลาของ segment | player เลื่อนไปฟังช่วงนั้น | HTTP Range ผ่าน; interaction ยังไม่ทดสอบ |
| Transcript revisions | แก้ไข Save → Reset | original ไม่เปลี่ยน มี revision ใหม่ทุกครั้ง | ผ่าน API integration |
| สองหน้าต่างแก้พร้อมกัน | Save revision เดิมสองครั้ง | ครั้งที่สอง 409 REVISION_CONFLICT | ผ่าน API integration |
| Export | เลือก Original/Edited ดาวน์โหลด TXT/JSON/SRT/VTT | UTF-8 และ timestamps ถูกต้อง | ผ่าน automated tests |
| Retry / delete | retry failed / delete processing | ไม่ลบไฟล์ที่ worker อ่านอยู่ | ผ่าน API/worker integration |
| Worker restart | หยุด worker ระหว่างงานแล้วเริ่มใหม่ | interrupted processing กลับเข้าคิว; original/completed คงอยู่ | ผ่าน manifest recovery test; hard-kill OS ขณะ inference ยังไม่ทดสอบ |
| Server access | APP_ENV=server และ token | ทุก route ป้องกัน auth รวม media/export/static | ผ่าน TestClient; HTTPS proxy ยังไม่ทดสอบ |
| Docker CPU | build → download model → up | health ผ่านและถอดไฟล์จริง | Compose config ผ่าน; daemon ไม่ทำงานจึงยังไม่ได้รัน |
| Large / long media | เกิน 100 MB / 2 ชั่วโมง | FILE_TOO_LARGE / DURATION_TOO_LONG | ตรวจ limit ด้วยค่าเล็กใน automated tests; ไฟล์ยาว 2 ชั่วโมงยังไม่ทดสอบ |

ไม่รับรองความแม่นยำ WER/CER จาก smoke test นี้ ต้อง benchmark ไฟล์สนทนาจริงก่อนใช้ตัดสินใจสำคัญ ไม่มีการระบุผู้พูดหรือสรุป/วิเคราะห์อารมณ์
