# VAJA Transcript Analyst · Microsoft 365 Copilot declarative agent

เอกสารสำหรับทีมพัฒนา VAJA AI และผู้ดูแล Microsoft 365 / Entra ID ขององค์กร ตรวจสอบกับเอกสาร Microsoft Learn เมื่อ 15 ตุลาคม 2026 (declarative agent schema v1.8, plugin manifest v2.4)

> **สถานะ:** ไฟล์ agent package พร้อมและผ่าน schema validation แล้ว แต่ **VAJA AI ยังไม่มี endpoint `/api/v1/*` และยังไม่รองรับ Entra ID** (ปัจจุบันมีแค่ `/api/jobs/...` + HTTP Basic และ bind เฉพาะ `127.0.0.1`) ต้องทำส่วน backend ในหัวข้อ 6 ก่อน agent จะเรียก VAJA ได้จริง

## 1. ชื่อและคำอธิบาย

- **ชื่อ:** VAJA Transcript Analyst
- **คำอธิบาย:** ตรวจทานและวิเคราะห์ transcript ภาษาไทยจาก VAJA AI สำหรับงานบริการลูกค้าการไฟฟ้า: แก้คำผิดจาก ASR โดยไม่เปลี่ยนความหมาย สรุปบทสนทนา วิเคราะห์ sentiment ของลูกค้าแยกจากเจ้าหน้าที่ และจัดหมวดหัวข้อ ส่งผลเป็น JSON และบันทึกกลับ VAJA AI เมื่อผู้ใช้ยืนยัน

## 2. ไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| [appPackage/manifest.json](../integrations/m365-copilot/appPackage/manifest.json) | Microsoft 365 app manifest v1.19 อ้างถึง declarative agent |
| [appPackage/declarativeAgent.json](../integrations/m365-copilot/appPackage/declarativeAgent.json) | ชื่อ คำอธิบาย conversation starters 8 ข้อ disclaimer และ action; **ไม่เปิด WebSearch** เพื่อไม่ให้ข้อมูลลูกค้าถูกใช้ค้นเว็บ |
| [appPackage/instruction.txt](../integrations/m365-copilot/appPackage/instruction.txt) | instructions ฉบับเต็ม (ไม่เกิน 8,000 ตัวอักษร) |
| [appPackage/ai-plugin.json](../integrations/m365-copilot/appPackage/ai-plugin.json) | API plugin v2.4: `getTranscript`, `getLatestAnalysis`, `saveAnalysis` + confirmation card + Entra SSO |
| [appPackage/apiSpecificationFile/vaja-openapi.yaml](../integrations/m365-copilot/appPackage/apiSpecificationFile/vaja-openapi.yaml) | OpenAPI 3.0.3 ของ endpoint ที่เสนอ และ JSON schema ของผลวิเคราะห์ (`AnalysisInput`) |
| [examples/analysis.example.json](../integrations/m365-copilot/examples/analysis.example.json) | ตัวอย่าง JSON สังเคราะห์ (ไม่ใช่ข้อมูลลูกค้า) ผ่าน schema |
| [env/.env.dev.example](../integrations/m365-copilot/env/.env.dev.example) | ค่าที่ต้องกรอก: app ID, URL, tenant, scope, auth config ID (ไม่มี secret) |
| [build_package.py](../integrations/m365-copilot/build_package.py) | แทนค่า `${{VAR}}` รวม instructions ตรวจข้อจำกัด สร้าง icon และ zip |

## 3. สองรูปแบบการเชื่อมต่อ (ไม่เทียบเท่ากัน)

| | **A. Copilot เรียก VAJA AI** (สิ่งที่ package นี้ทำ) | **B. VAJA AI เรียก Microsoft AI service** |
|---|---|---|
| ใครเรียกใคร | Microsoft 365 Copilot (cloud) → API plugin/MCP → VAJA AI | VAJA backend → Azure OpenAI / Azure AI Foundry API |
| ใครทำการวิเคราะห์ | โมเดลของ Copilot ตาม instructions ของ agent | โมเดลที่ deploy ใน Azure subscription ขององค์กร |
| ผู้ใช้ทำงานที่ไหน | แชตใน Copilot / Teams | หน้า VAJA AI (กดปุ่ม "วิเคราะห์") หรือประมวลผลอัตโนมัติ |
| สิทธิ์ | delegated token ของผู้ใช้ (Entra SSO) | Managed identity / service principal ของ VAJA |
| ค่าใช้จ่าย | ตาม license / Copilot Credits ของ M365 | ตาม Azure consumption แยกจาก M365 license |
| ใช้ได้เมื่อ | tenant อนุญาต custom app + Copilot access | มี Azure subscription และอนุมัติให้ส่งข้อมูลไป Azure |
| VAJA ต้องเปิด public HTTPS | **ต้อง** (Copilot เรียกมาจาก cloud) | ไม่ต้อง (VAJA เรียกออกอย่างเดียว) |

ทั้งสองแบบ **ส่ง transcript ออกจากเครื่อง VAJA ไปยัง Microsoft cloud** ซึ่งต่างจากหลักการเดิมของ VAJA ที่ประมวลผลในเครื่องทั้งหมด ต้องได้รับอนุมัติจากผู้รับผิดชอบด้านคุ้มครองข้อมูลส่วนบุคคล (PDPA) ก่อนใช้กับข้อมูลลูกค้าจริง

## 4. ข้อจำกัดที่ต้องรู้ก่อนเริ่ม

1. **Endpoint ยังไม่มีใน VAJA** ต้อง implement ตามหัวข้อ 6
2. **Copilot เข้าถึง `127.0.0.1` ไม่ได้** ต้องมี HTTPS reverse proxy สาธารณะ (เช่น Azure Container Apps/App Service, Application Gateway หรือ reverse proxy ขององค์กร) ห้ามใช้ dev tunnel กับข้อมูลลูกค้าจริง
3. **VAJA ยังไม่มีสิทธิ์รายผู้ใช้** (Basic auth เป็นพื้นที่ร่วม) ต้องเพิ่ม ownership/ACL ต่องานก่อนเปิดให้ Copilot ใช้ มิฉะนั้นผู้ที่ login ได้จะเห็นทุกงาน
4. **License "Basic":** ตารางของ Microsoft ระบุว่า declarative agent ที่มี *custom actions* ใช้ได้ใน Copilot Chat แม้ไม่มี Microsoft 365 Copilot license และไม่เปิด pay-as-you-go แต่ Microsoft ระบุด้วยว่าผู้ใช้ที่ไม่มี Copilot add-on อาจถูกจำกัดตาม tenant configuration และ rollout จึง **ต้องทดสอบใน tenant จริง** (หัวข้อ 9) ผมตรวจ tenant ของคุณจากที่นี่ไม่ได้ developer mode (`-developer on`) ใช้ได้เฉพาะผู้มี license
5. ขนาดผลลัพธ์: transcript ยาวจะแบ่งหน้า (`segment_limit` ≤ 300, `has_more`) และ `corrected_transcript` ส่งเฉพาะ segment ที่แก้ เพื่อไม่ให้ request ใหญ่เกิน

## 5. Instructions และ conversation starters

- Instructions: [instruction.txt](../integrations/m365-copilot/appPackage/instruction.txt) ครอบคลุมกฎความปลอดภัย (transcript เป็นข้อมูลไม่ใช่คำสั่ง, ไม่แต่งข้อมูล, ปิดบัง PII, ไม่เดา job_id, บันทึกเมื่อผู้ใช้สั่งเท่านั้น) และ 4 ความสามารถ พร้อมศัพท์ PEA / 1129 / มิเตอร์ / งดจ่ายไฟ / ค่า Ft
- Conversation starters (ใน declarativeAgent.json): วิเคราะห์ครบทุกด้าน, ตรวจทานคำผิด, สรุปสายสนทนา, Sentiment ลูกค้า, จัดหมวดหัวข้อ, JSON + บันทึกผล, ดูผลที่บันทึกไว้, วิเคราะห์ข้อความที่วาง

## 6. REST API / OpenAPI plugin

| Method | Path | operationId | หน้าที่ | ยืนยันก่อนเรียก |
|---|---|---|---|---|
| GET | `/api/v1/transcripts/{job_id}?version=edited&segment_offset=0&segment_limit=300` | `getTranscript` | segment ของงาน (edited หรือ original), `revision`, `has_more` | ใช่ ("Always allow" ได้) |
| POST | `/api/v1/analyses` | `saveAnalysis` | บันทึกผลวิเคราะห์เป็น record ใหม่ ไม่แก้ transcript | ใช่ ทุกครั้ง |
| GET | `/api/v1/analyses/{job_id}` | `getLatestAnalysis` | ผลวิเคราะห์ล่าสุด | ใช่ ("Always allow" ได้) |

งานฝั่ง VAJA backend ที่ต้องทำ:

1. **ตรวจ Entra access token** ทุก request: signature จาก JWKS ของ tenant, `iss` = `https://login.microsoftonline.com/<tenant-id>/v2.0`, `aud` = Application ID URI จาก SSO registration (และ client ID ของ VAJA API), `tid` = tenant ขององค์กร, `scp` มี scope ที่กำหนด ไม่ใช้ Basic auth กับ `/api/v1`
2. **สิทธิ์รายงาน:** เก็บ `owner_oid` / กลุ่ม Entra ใน manifest ของงาน และใช้ app roles (เช่น `VAJA.Reader`, `VAJA.Analyst`) ตอบ `404` เมื่อไม่มีสิทธิ์ เพื่อไม่บอกว่ามีงานนั้นอยู่
3. **`saveAnalysis` ตรวจ:** `transcript_revision` ตรงกับ revision ปัจจุบัน (ไม่ตรงตอบ `409 REVISION_CONFLICT`), ทุก `segment_id` มีจริง, `original_text` ตรงกับข้อความที่เก็บไว้ทุกตัวอักษร (ไม่ตรงตอบ `422 INVALID_ANALYSIS`), ขนาด body จำกัด
4. เก็บเป็น `data/jobs/<id>/analysis.<n>.json` แบบ atomic แยกจาก transcript โดย `created_by` = `oid` จาก token, `producer` = `m365-copilot-agent` ผู้ตรวจทานนำ corrected text ไปใช้ผ่านหน้าแก้ไขเดิม ซึ่งจะสร้าง revision ใหม่
5. Logs เก็บเฉพาะ request ID, job ID, oid และ status code ห้ามเก็บข้อความ transcript และตั้ง rate limit
6. ตั้ง `APP_ENV=server`, ส่ง host/proto ที่ถูกต้องจาก proxy และใช้ HTTPS (Copilot เรียกแบบ server-to-server ไม่ต้องเปิด CORS)

MCP: plugin manifest v2.4 รองรับ runtime `RemoteMCPServer` และ Entra SSO สำหรับ MCP (MCP ไม่รองรับ API key) แต่ VAJA เป็น REST อยู่แล้ว จึงแนะนำ OpenAPI ก่อน ถ้าภายหลังต้องการ MCP ให้ห่อ 3 operation เดิมเป็น MCP tools ที่ชื่อเดียวกัน และเปลี่ยน runtime ใน ai-plugin.json

## 7. Authentication (Microsoft Entra SSO)

1. **Entra admin center → App registrations → New:** `VAJA AI API` (single tenant) → Expose an API: ตั้ง Application ID URI และ delegated scope เช่น `Analyses.ReadWrite` → App roles ตามข้อ 6.2
2. **Teams developer portal → Tools → Microsoft Entra SSO client ID registration → Register client ID:** Base URL = `VAJA_API_BASE_URL` (ต้องตรงกับ `servers` ใน OpenAPI), Restrict usage by org = tenant ของคุณ, Client ID = client ID ของข้อ 1, Scope = scope ของข้อ 1 → ได้ **Microsoft Entra SSO registration ID** (ใส่ใน `VAJA_ENTRA_SSO_AUTH_CONFIG_ID`) และ **Application ID URI**
3. **กลับไปที่ app registration:**
   - เพิ่ม Application ID URI จากข้อ 2 ใน `identifierUris` (แก้ผ่าน Manifest editor)
   - Authentication → Web redirect URI `https://teams.microsoft.com/api/platform/v1.0/oAuthConsentRedirect`
   - Expose an API → Add a client application: `ab3be6b7-f5df-413d-ac2d-abf1e3fd9c0b` (Microsoft Enterprise token store)
4. **VAJA backend** รับ audience ใหม่จากข้อ 2 และ client `ab3be6b7-...` ตามข้อ 6.1
5. หลัง publish แล้ว ผูก SSO registration กับ Teams app ID จริงใน developer portal

ไม่มี API key หรือ secret อยู่ใน prompt, manifest หรือไฟล์ env ของ package เพราะ token ถูกเก็บใน Microsoft Enterprise token store และอ้างอิงด้วย `reference_id`

## 8. JSON schema

Schema หลักอยู่ที่ `components.schemas.AnalysisInput` ใน [vaja-openapi.yaml](../integrations/m365-copilot/appPackage/apiSpecificationFile/vaja-openapi.yaml) ตัวอย่างอยู่ที่ [analysis.example.json](../integrations/m365-copilot/examples/analysis.example.json)

| Field | เนื้อหา |
|---|---|
| `job_id`, `transcript_revision`, `source_version`, `schema_version` | อ้างอิง transcript ที่วิเคราะห์ |
| `corrected_transcript[]` | เฉพาะ segment ที่แก้: `segment_id`, เวลา, `speaker` + `speaker_inferred`, `original_text` (ตรงทุกตัวอักษร), `corrected_text`, `changes[]` พร้อม confidence |
| `summary` | `reason_for_contact`, `main_issue`, `key_issues`, `requests`, `responses`, `resolution_status`, `resolution`, `confirmed_facts[]` (มี segment_ids), `uncertain_information[]` |
| `sentiment` | `customer` และ `agent` แยกกัน: `label` Positive/Neutral/Negative/Mixed, `confidence`, `trajectory`, `explanation` |
| `sentiment_evidence[]` | `speaker`, `segment_id`, `excerpt` (คำพูดตรงตัว), `interpretation` |
| `topics[]` | `category` ∈ power_outage, billing, meter, service_request, complaint, general_inquiry, other; `primary`, `confidence`, `segment_ids` |
| `pending_actions[]` | `item`, `owner` (agent/customer/field_team/other/unknown), `due` (เฉพาะที่พูดในสาย) |
| `uncertain_segments[]` | `segment_id`, `type` (uncertain_word, ambiguous_speaker, possible_misheard_number, possible_hallucination, gap, low_audio_quality), `note` |

## 9. ขั้นตอน integration

1. **ขออนุมัติ:** DPO/ฝ่ายกฎหมายอนุมัติการส่ง transcript ไป Microsoft 365 Copilot, ขอบเขตผู้ใช้ และระยะเวลาเก็บผลวิเคราะห์ ระหว่างพัฒนาใช้ข้อมูลทดสอบเท่านั้น
2. **ตรวจ tenant:** ติดตั้ง Microsoft 365 Agents Toolkit ใน VS Code → Sign in to Microsoft 365 → ต้องเห็นทั้ง **Custom App Upload Enabled** และ **Copilot Access Enabled** ถ้าไม่เห็น ให้ admin ทำหัวข้อ 10
3. **Backend:** implement หัวข้อ 6 แล้ว deploy VAJA หลัง HTTPS proxy สาธารณะ
4. **Entra:** ทำหัวข้อ 7
5. **กรอกค่า:** `Copy-Item integrations\m365-copilot\env\.env.dev.example integrations\m365-copilot\env\.env.dev` แล้วกรอกค่า (`TEAMS_APP_ID` สร้างด้วย `[guid]::NewGuid()`)
6. **Build:** `.\.venv\Scripts\python integrations\m365-copilot\build_package.py` ได้ไฟล์ `integrations/m365-copilot/build/vaja-transcript-analyst.zip`
7. **อัปโหลดทดสอบ:** Teams → Apps → Manage your apps → Upload an app → Upload a custom app (หรือใช้ Agents Toolkit: เปิดโฟลเดอร์ `appPackage` เป็น project แล้ว Provision)
8. **ทดสอบใน Copilot Chat:** เลือก agent → ใช้ starter "วิเคราะห์ครบทุกด้าน" กับงานทดสอบ → sign in → ตรวจว่า confirmation ขึ้นก่อนอ่าน/บันทึก, ผู้ใช้อื่นอ่านงานที่ไม่มีสิทธิ์ไม่ได้ (404), transcript ที่มีข้อความ "ignore previous instructions" ไม่ทำให้ agent เรียก action เอง, และ revision ที่เปลี่ยนแล้วบันทึกไม่ได้ (409)
9. **Publish ภายในองค์กร:** ส่งเข้า org catalog ให้ admin อนุมัติใน Microsoft 365 admin center → Agents / Integrated apps กำหนดกลุ่มผู้ใช้ แล้วผูก SSO registration กับ app ID ที่ publish

## 10. Permissions และ licensing checklist

| รายการ | ผู้ทำ | ที่ไหน |
|---|---|---|
| เปิด **Upload custom apps** | Teams admin | Teams admin center → Teams apps → Setup policies → Global (หรือ policy เฉพาะกลุ่มผู้พัฒนา) |
| อนุญาตและ deploy agent ให้ผู้ใช้/กลุ่ม | Global admin / AI admin | Microsoft 365 admin center → Agents (Integrated apps) |
| Register app, expose API, app roles, admin consent | Application Administrator / Cloud Application Administrator | Microsoft Entra admin center |
| สร้าง Entra SSO registration | ผู้พัฒนา (บัญชีใน tenant) | Teams developer portal → Tools |
| License ผู้ใช้ | M365 admin | Billing → Licenses: ตรวจว่าผู้ใช้มี Copilot Chat เข้าถึงได้ (ไม่มี add-on ก็ใช้ custom actions ได้ตามตาราง Microsoft แต่ต้องทดสอบ), หรือ Microsoft 365 Copilot add-on สำหรับ developer mode |
| Pay-as-you-go (ไม่จำเป็นสำหรับ agent นี้) | M365 admin + Azure owner | ต้องใช้เมื่อเพิ่ม knowledge จาก SharePoint/connectors เท่านั้น |
| อนุมัติการส่งข้อมูลส่วนบุคคล | DPO | นโยบายองค์กร |

## 11. ทางเลือกเมื่อ integration บางส่วนใช้ไม่ได้

| ปัญหา | ทางเลือก |
|---|---|
| tenant ไม่อนุญาต custom app หรือ custom actions | สร้าง agent แบบ instructions-only ใน Copilot (Create agent / agent builder) โดยวาง instruction.txt ผู้ใช้ export TXT/JSON จาก VAJA แล้ววางในแชต ใช้ starter "วิเคราะห์ข้อความที่วาง" และนำ JSON ไปบันทึกเอง ไม่ต้องเปิด VAJA สู่ภายนอก |
| เปิด VAJA เป็น public HTTPS ไม่ได้ | ใช้แบบ B: VAJA เรียก Azure OpenAI ด้วย structured output (ใช้ instruction.txt เป็น system prompt และ `AnalysisInput` เป็น response schema) แล้วเก็บผลใน VAJA โดยตรง |
| ไม่อนุมัติให้ข้อมูลออกนอกองค์กร | ใช้ LLM ที่รันในเครื่อง/ศูนย์ข้อมูลขององค์กรกับ prompt และ schema เดียวกัน (อยู่นอกขอบเขต Copilot) |

## แหล่งอ้างอิง

- [Declarative agent schema 1.8](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/declarative-agent-manifest-1.8)
- [Plugin manifest schema 2.4](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-manifest-2.4)
- [Configure authentication for MCP and API plugins](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-authentication)
- [Configure Microsoft Entra SSO authentication](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-authentication-entra-sso)
- [Prerequisites and licensing for agents](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/prerequisites)
- [Build API plugins from an existing API](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/build-api-plugins-existing-api)
