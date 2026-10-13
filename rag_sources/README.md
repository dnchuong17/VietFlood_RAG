# Bộ nguồn Markdown cho RAG lũ lụt

Ngày thu thập và đối chiếu: **2026-09-29**.

## Phạm vi

- Bỏ qua F01, F02, F03 theo yêu cầu.
- Các bản ghi S01/V01 trùng URL F01 và V04/W02 trùng URL F02 cũng không được thu thập.
- Mỗi URL duy nhất dùng một file Markdown; các ID dùng chung URL được ghi chung trong `source_ids`.
- Tổng cộng: **41 file Markdown**, **2 PDF hợp lệ đã tải**.
- Nội dung Markdown là bài kiến thức tiếng Việt chi tiết, được viết lại độc lập từ nguồn; không phải bản sao hoặc bản đổi chữ tuần tự của toàn văn.
- Các hồ sơ có nội dung truy cập được bao gồm bối cảnh, hành động, điều kiện áp dụng, ngoại lệ và cảnh báo an toàn. Tổng dung lượng văn bản sau lần mở rộng là trên 21.000 từ.

## Cấu trúc

- `markdown/`: văn bản và metadata theo nguồn.
- `pdfs/`: PDF tải được và đã kiểm tra chữ ký `%PDF`.
- Đường dẫn PDF trong front matter của Markdown là đường dẫn tương đối từ file Markdown.

## Kết quả truy cập

| Trạng thái | Nguồn | Ý nghĩa |
|---|---|---|
| Đã đối chiếu với trang/PDF | Phần lớn hồ sơ | Nội dung đã được đọc và rà lại với nguồn trong ngày thu thập. |
| Chỉ mục, chưa có tài liệu con | S02, S06/W03, M07, H07, P03 | Trang chỉ liệt kê hoặc dẫn tài liệu khác; không suy đoán nội dung con. |
| Link hỏng/chuyển sai | P01 | URL chuyển về trang chủ, không dùng làm tri thức. |
| PDF tải bị máy chủ chặn | H03, P06 | Nội dung đọc được qua trình hiển thị web; không có PDF cục bộ. |
| Máy chủ trả HTML thay PDF | V03 | Bản giả 755 byte đã bị xóa; không giữ file sai định dạng. |
| Nguồn động | L01, L02 | Không phù hợp ingest tĩnh; cần tích hợp truy vấn thời gian thực. |

Các hồ sơ ngắn thuộc nhóm chỉ mục, link hỏng hoặc dữ liệu động được cố ý giữ ngắn. Chúng không có đủ nội dung nguồn để mở rộng một cách trung thực và không nên được dùng làm chunk kiến thức.

## PDF cục bộ

| Nguồn | File | Kích thước | SHA-256 |
|---|---|---:|---|
| P04 | `pdfs/P04_flood_cleanup_air_home_vietnamese.pdf` | 3.508.602 byte | `767ba9d573a742a0e9b58958362b03b56ad6902d59f10ec7f0ea0b8392ff4c68` |
| W04 | `pdfs/W04_drr_key_messages_second_edition.pdf` | 4.105.649 byte | `8b90348da213787dbefeaf328944fd9448700c482ac42ed3b742e9d373e25a1f` |

## Lưu ý trước khi ingest

1. Loại khỏi collection chính các file có `representation: access_record`, `dynamic_source_record` hoặc trạng thái chỉ mục nếu chưa thu thập được tài liệu con.
2. Nội dung có `medical_review_required: true` hoặc `chemical_dosing_review_required: true` phải được chuyên gia phê duyệt.
3. Chunk theo đề mục, giữ nguyên `source_ids`, `source_url`, ngày đối chiếu và các cảnh báo trong metadata.
4. Không trộn liều hóa chất giữa các nguồn hoặc các nồng độ sản phẩm khác nhau.
5. Không thay dữ liệu cảnh báo thời gian thực bằng nội dung vector DB tĩnh.
6. Các bài chi tiết không thay thế PDF hoặc trang gốc. Khi câu trả lời liên quan cấp cứu, y tế hay hóa chất, ứng dụng cần trích URL nguồn và áp dụng cơ chế từ chối/khuyến cáo phù hợp.

