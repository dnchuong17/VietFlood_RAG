# Kế hoạch xây dựng Qdrant Knowledge Base cho chatbot lũ lụt

**Ngày lập:** 28/09/2026  
**Phạm vi ưu tiên:** Việt Nam trước, nguồn toàn cầu sau  
**Đầu vào hiện có:** `flood_rag_source_catalog.md` — 59 dòng nguồn, 45 URL duy nhất

## 1. Kết luận nhanh

Danh mục hiện tại **đủ để làm proof of concept và bắt đầu MVP cho kiến thức tĩnh**, nhưng **chưa đủ để phát hành production**. Đây mới là danh mục nguồn, chưa phải corpus đã được tải, làm sạch, xác minh quyền sử dụng, phê duyệt chuyên môn, version hóa và đánh giá retrieval.

Không nên dùng Qdrant như nguồn duy nhất cho câu hỏi thời gian thực. Kiến trúc cần tách:

1. **Knowledge tĩnh đã duyệt** → Qdrant.
2. **Cảnh báo, mực nước, đường đi, điểm sơ tán và tình trạng cứu hộ hiện tại** → adapter/API dữ liệu trực tiếp có TTL, thời điểm phát hành và nguồn xác thực.
3. **Dữ liệu nghiệp vụ của app** như yêu cầu cứu hộ, trạng thái ticket và thông tin người dùng → cơ sở dữ liệu giao dịch; không lưu làm knowledge công khai trong Qdrant.

## 2. Các quyết định kiến trúc đề xuất

### 2.1 Thành phần

```text
Nguồn tĩnh ──> ingest/staging ──> review ──> chunk/embed ──> Qdrant
                                      │
Nguồn động ──> live-source adapters ──┼──> intent router ──> retrieval/rerank ──> LLM
                                      │                              │
App/backend ─> transactional APIs ────┘                              └─> câu trả lời + dẫn nguồn + thời điểm
```

### 2.2 Collection

MVP nên dùng một collection logic cho corpus đồng nhất về embedding, ví dụ `flood_kb_2026_01`, với alias ổn định `flood_kb_active`. Khi re-index hoặc đổi embedding model, tạo collection mới rồi đổi alias sau khi đánh giá đạt chuẩn.

Không tạo một collection cho mỗi topic hoặc mỗi tỉnh. Dùng payload filter và payload index. Chỉ tách collection khi:

- dùng embedding model/kích thước vector khác nhau;
- cần cô lập bảo mật hoặc vòng đời dữ liệu khác hẳn;
- corpus app nội bộ có quyền truy cập khác với knowledge công khai;
- benchmark chứng minh việc tách có lợi.

Đề xuất ban đầu:

- `flood_kb_active`: kiến thức thiên tai, an toàn, WASH, nội dung y tế đã duyệt;
- `app_help_active`: tài liệu sử dụng app, nếu cần deploy/version độc lập;
- nguồn động không nằm trong hai collection này, trừ cache có TTL và bị bắt buộc lọc theo `valid_until`.

### 2.3 Retrieval

Ưu tiên **hybrid retrieval**:

- dense embedding đa ngôn ngữ cho ngữ nghĩa Việt–Anh;
- sparse/lexical retrieval để giữ chính xác địa danh, mã cảnh báo, tên thuốc/hóa chất, số điện thoại và thuật ngữ;
- fusion (ví dụ RRF), sau đó rerank tập ứng viên;
- metadata filter luôn được áp dụng trước/đồng thời với tìm kiếm.

Hai ứng viên embedding để benchmark, không chọn chỉ dựa trên leaderboard:

- `BAAI/bge-m3`: phù hợp để thử dense + sparse và văn bản dài;
- `intfloat/multilingual-e5-large` hoặc biến thể instruct: baseline multilingual mạnh, nhưng phải tuân thủ format query/document của model.

Chọn model bằng bộ câu hỏi tiếng Việt thực tế. Không đổi model trong cùng một collection vì vector dimensions/không gian embedding không tương thích.

## 3. Data contract tối thiểu

Mỗi Qdrant point tương ứng một chunk, có ID tất định từ `document_id + version + chunk_index` hoặc content hash.

```json
{
  "point_id": "sha256:...",
  "document_id": "S06:2026-01",
  "source_id": "S06",
  "chunk_id": "S06:2026-01:0042",
  "title": "...",
  "section_path": ["Trong lũ", "Sơ tán"],
  "text": "...",
  "publisher": "...",
  "canonical_url": "https://...",
  "source_type": "STATIC",
  "content_type": "guidance",
  "language": "vi",
  "country_code": "VN",
  "province_codes": [],
  "hazard_types": ["FLOOD"],
  "topics": ["EVACUATION"],
  "audiences": ["GENERAL_PUBLIC"],
  "review_status": "APPROVED",
  "medical_review_required": false,
  "medical_reviewer": null,
  "license_status": "APPROVED_FOR_RAG",
  "issued_at": "2026-01-23T00:00:00+07:00",
  "valid_from": "2026-01-23T00:00:00+07:00",
  "valid_until": null,
  "retrieved_at": "2026-09-28T00:00:00+07:00",
  "approved_at": "2026-09-28T00:00:00+07:00",
  "document_version": 1,
  "content_hash": "sha256:...",
  "page": 4,
  "source_span": "section-or-paragraph-anchor",
  "app_version_min": null,
  "app_version_max": null
}
```

Payload index tối thiểu:

- keyword: `source_id`, `document_id`, `source_type`, `language`, `country_code`, `province_codes`, `hazard_types`, `topics`, `audiences`, `review_status`, `license_status`;
- boolean: `medical_review_required`;
- datetime/range: `valid_from`, `valid_until`, `issued_at`;
- keyword cho tài liệu app: `platform`, `feature`, `screen_id`, `app_version_min`, `app_version_max`.

Quy tắc deny-by-default: chatbot công khai chỉ truy hồi chunk có `review_status=APPROVED`, `license_status=APPROVED_FOR_RAG`, đúng phạm vi địa lý/phiên bản và chưa hết hiệu lực.

## 4. Pipeline ingest

1. **Registry:** quản lý từng URL, chủ sở hữu, loại file, license, checksum, lịch refresh và người duyệt.
2. **Fetch:** tải có rate limit, lưu bản gốc bất biến, HTTP metadata và thời điểm tải; tuân thủ điều khoản/robots.
3. **Extract:** HTML/PDF/DOCX/OCR; giữ heading, danh sách, bảng, chú thích, số trang và liên kết về nguồn.
4. **Normalize:** Unicode NFC, sửa ngắt dòng/hyphen, loại menu/footer, phát hiện trùng lặp; không làm mất dấu tiếng Việt.
5. **Editorial pass:** dịch/biên tập nguồn EN sang VI nếu được phép; giữ bản gốc và bản dịch liên kết với nhau; không tự hợp nhất các quy trình mâu thuẫn.
6. **Review:** pháp lý/license, nghiệp vụ thiên tai, y tế/WASH; ghi rõ người duyệt, ngày duyệt và phiên bản.
7. **Chunk:** theo cấu trúc ngữ nghĩa, thường bắt đầu thử ở 350–600 token; không cắt rời điều kiện, cảnh báo, danh sách bước hoặc bảng liều lượng. Giữ overlap nhỏ và đo bằng eval thay vì cố định theo cảm tính.
8. **Embed/upsert:** batch, retry idempotent, deterministic IDs; ghi manifest của model, tokenizer và pipeline version.
9. **Validate:** đối chiếu số chunk, hash, metadata bắt buộc, orphan/duplicate, khả năng truy ngược về đoạn nguồn.
10. **Publish:** chạy eval trên collection candidate, sau đó đổi alias; có rollback về collection trước.

## 5. Luồng truy vấn an toàn

1. Phân loại intent: `LIVE_ALERT`, `IMMEDIATE_DANGER`, `STATIC_KNOWLEDGE`, `FIRST_AID`, `APP_USAGE`, `OUT_OF_SCOPE`.
2. Nhận diện và chuẩn hóa địa điểm nhưng không tự suy đoán xã/phường khi chưa đủ dữ kiện.
3. Với `LIVE_ALERT`: gọi nguồn trực tiếp, kiểm tra `issued_at`, `valid_until`, trạng thái và vùng áp dụng; không dùng chunk tĩnh để khẳng định tình hình hiện tại.
4. Với `IMMEDIATE_DANGER`: hiển thị hành động an toàn ngắn, số khẩn cấp đã xác minh, sau đó mới cung cấp giải thích; không để retrieval latency trì hoãn thông tin cứu nguy.
5. Với knowledge tĩnh: filter → dense+sparse → fusion → rerank → chọn 3–6 đoạn hỗ trợ.
6. LLM chỉ trả lời từ evidence được chọn, dẫn nguồn theo từng khẳng định quan trọng và nêu ngày/phiên bản khi liên quan.
7. Nếu nguồn mâu thuẫn, quá cũ, ngoài địa bàn hoặc điểm tin cậy thấp: từ chối khẳng định và hướng dẫn người dùng kiểm tra nguồn chính thức.

## 6. Đánh giá catalog và nguồn cần bổ sung

### 6.1 Đã tốt

- Bao phủ tốt vòng đời trước–trong–sau lũ.
- Có Việt Nam-first và nguồn quốc tế uy tín.
- Đã phân biệt STATIC/DYNAMIC và nhận diện rủi ro y tế, hóa chất, số khẩn cấp.
- Có nhóm tài liệu sử dụng app và metadata sơ bộ.

### 6.2 Thiếu trước production

| Khoảng trống | Việc cần bổ sung |
|---|---|
| Khẩn cấp tại Việt Nam | Nguồn chính thức về tổng đài 112; mapping 112/113/114/115 và quy tắc hiển thị theo tình huống, được rà soát định kỳ |
| Y tế Việt Nam cập nhật | Quyết định 237/QĐ-BYT ngày 23/01/2026 và hướng dẫn 2026 về dịch bệnh, nước sạch, vệ sinh môi trường mùa mưa lũ |
| Pháp lý và thẩm quyền | Luật Phòng, chống thiên tai hiện hành, Luật Phòng thủ dân sự, Nghị định 66/2021/NĐ-CP và văn bản sửa đổi; dùng để xác định nguồn/thẩm quyền, không biến toàn bộ luật thành hướng dẫn sinh tồn |
| Địa phương | Phương án sơ tán, điểm trú ẩn, đầu mối cứu hộ, bản đồ rủi ro và hướng dẫn của UBND/Ban Chỉ huy từng tỉnh/thành triển khai |
| Ngập đô thị | Sở Xây dựng, đơn vị thoát nước và quy hoạch/chống ngập chính thức của thành phố mục tiêu |
| Điện và hạ tầng | Hướng dẫn của EVN/đơn vị điện lực và cơ quan hạ tầng tại Việt Nam, có review kỹ thuật |
| Người dễ bị tổn thương | Người cao tuổi, thai phụ, bệnh mạn tính, người dùng thiết bị y tế cần điện, ngôn ngữ ký hiệu/khả năng tiếp cận |
| Gia súc/vật nuôi | Hướng dẫn thú y, xử lý xác động vật và an toàn dịch bệnh từ cơ quan Việt Nam |
| Chuẩn cảnh báo | Mô hình dữ liệu tương thích CAP: severity, urgency, certainty, area, instruction, issued/expiry |
| Vận hành dữ liệu | License register, owners, SLA cập nhật, expiry policy, audit trail và quy trình thu hồi nội dung |

Nguồn toàn cầu chỉ nên bổ sung sau khi xác định không có hướng dẫn Việt Nam tương đương. Ưu tiên WHO, UNICEF, IFRC, WMO/CAP, UNDRR; GDACS/ReliefWeb có thể dùng làm tín hiệu bổ sung hoặc nghiên cứu sự kiện, không thay thế cảnh báo chính thức của Việt Nam.

## 7. Bộ kiểm thử bắt buộc

Tạo ít nhất 150–300 câu hỏi trước MVP, gồm:

- câu tự nhiên tiếng Việt, không dấu, lỗi chính tả, giọng địa phương phổ biến;
- truy vấn theo tỉnh/huyện/xã và địa danh trùng tên;
- câu hỏi Việt dựa trên tài liệu nguồn tiếng Anh;
- câu hỏi cần lexical match chính xác: 112, tên cơ quan, hóa chất, phiên bản app;
- câu hỏi “bây giờ/hôm nay/ở đây” để kiểm tra routing sang nguồn động;
- tình huống nguy hiểm, y tế, liều lượng và câu hỏi cố ép chatbot suy diễn;
- câu không có đáp án, nguồn mâu thuẫn, tài liệu hết hạn và nội dung chưa duyệt.

Chỉ số retrieval:

- Recall@5/@10, MRR hoặc nDCG;
- tỷ lệ lọc đúng địa lý, trạng thái review và hạn hiệu lực;
- citation precision/coverage;
- tỷ lệ route đúng static/live/emergency/app;
- latency p50/p95 và chi phí mỗi truy vấn.

Chỉ số trả lời:

- groundedness/faithfulness;
- độ đúng nghiệp vụ theo reviewer;
- không bỏ sót cảnh báo an toàn;
- abstention đúng khi thiếu dữ liệu;
- không sử dụng số điện thoại, liều lượng hoặc cảnh báo hết hiệu lực.

Release gate đề xuất: 100% test critical-safety phải đạt; không cho phép một ngưỡng trung bình che lấp lỗi nguy hiểm.

## 8. Kế hoạch triển khai theo phase

### Phase 0 — Chốt phạm vi và governance (2–4 ngày)

- Chọn 2–3 tỉnh/thành thí điểm và nhóm use case MVP.
- Chỉ định content owner, medical/WASH reviewer và người chịu trách nhiệm release.
- Chốt quy tắc license, lưu dữ liệu cá nhân, TTL và incident response.
- Định nghĩa tiêu chí thành công và bộ câu hỏi vàng ban đầu.

**Hoàn thành khi:** có scope, owner, approval matrix, risk register và 50 câu hỏi seed.

### Phase 1 — Data foundation (4–7 ngày)

- Chuẩn hóa source registry và metadata schema.
- Bổ sung nguồn còn thiếu ưu tiên Việt Nam.
- Xây fetch/extract cho HTML và PDF, raw store, hash và manifest.
- Ingest thử 5–8 nguồn P0, chưa public.

**Hoàn thành khi:** mọi chunk truy ngược được tới nguồn/trang/đoạn và pipeline chạy idempotent.

### Phase 2 — Qdrant baseline (3–5 ngày)

- Dựng Qdrant dev/staging, auth/TLS/network policy, backup/snapshot.
- Tạo named dense/sparse vectors, payload indexes và strict filtering.
- Tạo candidate collection + alias, batch upsert và health metrics.
- Benchmark hai embedding model trên tập Việt ngữ.

**Hoàn thành khi:** có báo cáo lựa chọn model và restore test thành công.

### Phase 3 — Retrieval service (5–8 ngày)

- Intent router, geo normalization và policy engine.
- Hybrid retrieval, fusion, rerank, citation builder.
- Filter bắt buộc cho approval/license/location/version/expiry.
- Cơ chế no-answer, conflict và stale-data handling.

**Hoàn thành khi:** đạt retrieval baseline trên bộ câu hỏi vàng và không lọt chunk chưa duyệt.

### Phase 4 — Live data và safety (5–10 ngày)

- Tích hợp NCHMF/nguồn cảnh báo hợp lệ bằng adapter riêng.
- Chuẩn hóa alert theo CAP-like schema và cache ngắn hạn.
- Thêm emergency flow, nguồn 112, timestamp và fallback khi upstream lỗi.
- Threat model: prompt injection trong tài liệu, poisoned source, SSRF fetcher, quyền admin và rò rỉ dữ liệu.

**Hoàn thành khi:** toàn bộ critical-safety tests đạt và diễn tập nguồn live lỗi/quá hạn thành công.

### Phase 5 — Content review và app docs (song song, 1–2 tuần)

- Phê duyệt corpus P0, khóa nội dung y tế chưa duyệt.
- Viết A01–A08 đúng với phiên bản app thực tế.
- Bổ sung nội dung cho địa phương thí điểm và khả năng tiếp cận.

**Hoàn thành khi:** mọi nội dung public có owner, reviewer, version và lịch refresh.

### Phase 6 — Pilot và production readiness (1 tuần)

- UAT với người dùng Việt Nam và chuyên gia thiên tai/y tế.
- Load test, chaos/failover, backup restore và rollback alias.
- Dashboard cho freshness, retrieval quality, no-answer, latency và lỗi nguồn.
- Canary release, audit log và quy trình gỡ khẩn cấp một nguồn/chunk.

**Hoàn thành khi:** sign-off nghiệp vụ, an toàn, vận hành và pháp lý đều có bằng chứng.

## 9. Thông tin còn cần từ nhóm dự án

Các câu trả lời này quyết định sizing và thiết kế cuối cùng:

1. Tỉnh/thành nào là phạm vi MVP?
2. App/web/backend đang dùng stack gì; chatbot gọi qua service nào?
3. Qdrant self-hosted hay Cloud; vùng lưu trữ dữ liệu và yêu cầu HA/DR?
4. Số tài liệu, người dùng đồng thời, truy vấn/ngày và latency mục tiêu?
5. Dùng LLM/embedding local hay API; ngân sách và yêu cầu dữ liệu không rời Việt Nam?
6. Có cần chạy khi mạng yếu/offline không?
7. Ai có quyền duyệt y tế, WASH, pháp lý và nội dung địa phương?
8. Nhóm đã có thỏa thuận/API chính thức cho cảnh báo, mực nước, điểm trú ẩn và tình trạng đường chưa?
9. Chatbot chỉ cung cấp kiến thức hay còn thao tác gửi/tra cứu yêu cầu cứu hộ?
10. Chính sách lưu prompt, vị trí GPS, số điện thoại và dữ liệu nhạy cảm là gì?

## 10. Việc nên làm ngay trong tuần đầu

1. Chọn địa bàn MVP và 8–12 intent quan trọng nhất.
2. Bổ sung nguồn 112 và tài liệu Bộ Y tế 2026 vào catalog.
3. Tạo `sources.yaml` hoặc bảng registry có owner/license/review/refresh.
4. Lấy 5–8 nguồn P0, tạo corpus mẫu và 50 câu hỏi vàng.
5. Benchmark dense-only với hybrid trên hai embedding candidate.
6. Chỉ sau khi retrieval đạt baseline mới nối LLM và mở rộng toàn bộ P0.

