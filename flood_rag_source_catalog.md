# DANH MỤC NGUỒN DỮ LIỆU CHO RAG CHATBOT PHÒNG CHỐNG LŨ LỤT

**Phiên bản:** 1.0  
**Ngày lập danh mục:** 22/09/2026  
**Mục đích:** Danh sách đường dẫn nguồn để thu thập, kiểm duyệt và xây dựng knowledge base cho chatbot tiếng Việt hỗ trợ kiến thức phòng tránh lũ, sinh tồn, sơ cứu và hướng dẫn sử dụng ứng dụng.

> **Phạm vi kiểm chứng:** Các trang đích dưới đây được tìm thấy trên website của tổ chức phát hành qua tìm kiếm web tại thời điểm lập danh mục. Đây là **source catalog**, không phải toàn bộ nội dung đã được thu thập, kiểm chứng y khoa, rà soát bản quyền hoặc đưa vào RAG. URL, tài liệu và quy trình có thể thay đổi; cần kiểm tra lại khi ingest.
>
> **An toàn:** Không trộn hướng dẫn y tế, hóa chất xử lý nước hay số điện thoại cấp cứu từ các nước thành một quy trình cho Việt Nam. Nội dung sơ cứu phải có người chuyên môn phê duyệt. Thông tin cảnh báo, đường đi và điểm sơ tán phải lấy từ nguồn hiện hành đã xác minh; không trả lời bằng dữ liệu RAG tĩnh.

## Quy ước sử dụng

- **P0:** nguồn ưu tiên để xây dựng MVP; **P1:** bổ sung độ bao phủ.
- **VI:** tiếng Việt; **EN:** tiếng Anh; **VI available:** trang có bản tải tiếng Việt.
- **STATIC:** tài liệu kiến thức có thể ingest sau kiểm duyệt; **DYNAMIC:** nguồn thay đổi theo thời gian, cần service truy vấn riêng.
- Các mô tả “nội dung nên lấy” là hướng dẫn tạo dữ liệu, **không phải văn bản gốc** để đưa trực tiếp vào vector DB.
- `source_id` là định danh duy nhất; một nguồn có thể phục vụ nhiều topic, không tải thành nhiều bản sao khác nhau.

---

## 1. 🌊 Kiến thức nền tảng về lũ lụt — `FLOOD_KNOWLEDGE`

| ID | Ưu tiên | Nguồn / tài liệu | Ngôn ngữ | Nội dung nên thu thập | URL chính thức |
|---|---|---|---|---|---|
| F01 | P0 | UNICEF Việt Nam — Hướng dẫn an toàn trước lũ lụt dành cho cha mẹ | VI | Khái niệm, nguyên nhân, các dạng lũ, tác động và kiến thức cho hộ gia đình | https://www.unicef.org/vietnam/vi/an-toan-lu-lut-cha-me |
| F02 | P0 | UNICEF Việt Nam — An toàn trước lũ quét và sạt lở đất | VI | Định nghĩa lũ quét/sạt lở, dấu hiệu và nguy cơ vùng núi | https://www.unicef.org/vietnam/vi/an-toan-lu-quet-sat-lo-dat |
| F03 | P1 | USGS — Floods: Things to Know | EN | Nguyên nhân lũ, thủy văn, khái niệm tần suất và lưu lượng đỉnh | https://www.usgs.gov/water-science-school/science/floods-things-know |
| F04 | P1 | WHO — Drowning | EN | Nguy cơ đuối nước, phòng ngừa và bối cảnh sức khỏe cộng đồng | https://www.who.int/news-room/fact-sheets/detail/drowning |

**Câu hỏi kiểm thử gợi ý:** “Lũ quét khác lũ sông ra sao?”, “Vì sao ngập đô thị xuất hiện sau mưa lớn?”, “Tại sao nước lũ nguy hiểm dù tôi biết bơi?”. **Gap:** muốn giải thích sâu *ngập đô thị* cần bổ sung tài liệu chuyên ngành về hệ thống thoát nước và quy hoạch tại địa phương; không suy diễn chi tiết chưa có nguồn.

## 2. ⚠️ An toàn trước – trong – sau lũ — `FLOOD_SAFETY`

| ID | Ưu tiên | Nguồn / tài liệu | Ngôn ngữ | Nội dung nên thu thập | URL chính thức |
|---|---|---|---|---|---|
| S01 | P0 | UNICEF Việt Nam — Hướng dẫn an toàn lũ lụt | VI | Chuẩn bị, ứng phó khi ngập, sau lũ, chăm sóc trẻ | https://www.unicef.org/vietnam/vi/an-toan-lu-lut-cha-me |
| S02 | P0 | IFRC — Floods: Key Messages | EN | Thông điệp an toàn cộng đồng; trang có tệp tài liệu tải về | https://www.ifrc.org/media/13379 |
| S03 | P0 | WHO — Public health advice before, during and after floods | EN | An toàn khi mắc kẹt/sơ tán, quay về nhà và sức khỏe | https://www.who.int/europe/emergencies/situations/climate-crisis-extreme-weather/public-health-advice-on-protecting-your-health-before-during-and-after-floods |
| S04 | P0 | American Red Cross — Flood Safety / Preparedness | EN | Kế hoạch trước lũ, hành động trong lũ và phục hồi | https://www.redcross.org/get-help/how-to-prepare-for-emergencies/types-of-emergencies/flood.html |
| S05 | P1 | IFRC — Floods | EN | Hành động an toàn cốt lõi, nguy cơ nước xiết và nước ô nhiễm | https://www.ifrc.org/our-work/disasters-climate-and-crises/what-disaster/floods |
| S06 | P0 | Cổng phòng chống thiên tai Việt Nam — Tài liệu hướng dẫn lũ, lũ quét, sạt lở đất | VI | Tờ rơi, video và tài liệu chuyên đề Việt Nam; mở trang để truy cập thư mục tệp | https://phongchongthientai.mard.gov.vn/Pages/tai-lieu-huong-dan-phong-chong-cac-loai-hinh-thien-tai-lu-lu-quet-sat-lo-dat.aspx |
| S07 | P1 | WHO — Floods: How to protect your health | EN | Vệ sinh, phòng bệnh, tránh vùng ngập và chăm sóc sau lũ | https://www.who.int/news-room/questions-and-answers/item/how-do-i-protect-my-health-in-a-flood |
| S08 | P1 | CDC — Preparing for Floods | EN | Kiểm tra rủi ro, chuẩn bị và thông tin sơ tán | https://www.cdc.gov/floods/safety/index.html |

**Topic đề xuất:** `BEFORE_FLOOD`, `DURING_FLOOD`, `TRAPPED`, `FLOODED_ROAD`, `EVACUATION`, `AFTER_FLOOD`, `HOME_REENTRY`.

## 3. 🩹 Sơ cứu và cấp cứu liên quan lũ — `FIRST_AID`

**Bắt buộc review y tế trước khi kích hoạt trả lời theo từng bước.** Tài liệu nước ngoài có thể ghi **911** hoặc hệ thống ứng cứu Mỹ; không được đưa nguyên vào ứng dụng Việt Nam.

| ID | Ưu tiên | Nguồn / tài liệu | Ngôn ngữ | Nội dung nên thu thập | URL chính thức |
|---|---|---|---|---|---|
| M01 | P0 | AHA/AAP — 2024 Focused Update: Resuscitation Following Drowning | EN | Hồi sức sau đuối nước; phân biệt hướng dẫn đuối nước với CPR chung | https://professional.heart.org/en/science-news/2024-aha-and-aap-focused-update-on-special-circumstances-resuscitation-following-drowning |
| M02 | P0 | AHA/AAP — Top Things to Know: Drowning Resuscitation | EN | Tóm lược chuyên môn, cứu hộ an toàn và vai trò hô hấp | https://professional.heart.org/en/science-news/2024-aha-and-aap-focused-update-on-special-circumstances-resuscitation-following-drowning/top-things-to-know |
| M03 | P0 | American Red Cross — Life-Threatening External Bleeding | EN | Nhận biết và sơ cứu chảy máu nặng; kỹ thuật cần đào tạo | https://www.redcross.org/take-a-class/resources/learn-first-aid/bleeding-life-threatening-external |
| M04 | P0 | American Red Cross — Hypothermia | EN | Dấu hiệu hạ thân nhiệt, chăm sóc, tình huống cần cấp cứu | https://www.redcross.org/take-a-class/resources/learn-first-aid/hypothermia |
| M05 | P1 | American Red Cross — Adult Cardiac Arrest | EN | Nhận biết ngừng tuần hoàn, kích hoạt cấp cứu, CPR/AED theo đào tạo | https://www.redcross.org/take-a-class/resources/learn-first-aid/adult-cardiac-arrest |
| M06 | P1 | American Red Cross — Wounds | EN | Vết thương, nguy cơ nhiễm bẩn, nhận biết loại thương tích | https://www.redcross.org/take-a-class/resources/learn-first-aid/wounds |
| M07 | P1 | American Red Cross — First Aid Resource Hub | EN | Đầu mối để tìm các tình huống sơ cứu bổ sung | https://www.redcross.org/take-a-class/resources/learn-first-aid |
| M08 | P1 | WHO — Public health advice after flooding (Q&A) | EN | Hạ thân nhiệt, thương tích, nước sạch, sức khỏe sau lũ | https://www.who.int/europe/news-room/questions-and-answers/item/public-health-advice-in-the-aftermath-of-flooding---how-to-protect-your-health-and-keep-safe |

**Quy định dữ liệu:** Với mỗi quy trình sơ cứu lưu `symptoms`, `safe_actions`, `actions_to_avoid`, `call_emergency_when`, `training_required`, `source_id`, `medical_reviewer`, `reviewed_at`, `version`. Không tự ghép hai phác đồ từ các tổ chức khác nhau.

## 4. 🎒 Chuẩn bị khẩn cấp — `EMERGENCY_PREPAREDNESS`

| ID | Ưu tiên | Nguồn / tài liệu | Ngôn ngữ | Nội dung nên thu thập | URL chính thức |
|---|---|---|---|---|---|
| E01 | P0 | American Red Cross — Survival Kit Supplies | EN | Danh sách túi khẩn cấp, nước/thực phẩm, giấy tờ, thuốc, trẻ em | https://www.redcross.org/get-help/how-to-prepare-for-emergencies/survival-kit-supplies.html |
| E02 | P0 | UNICEF Việt Nam — An toàn trước bão | VI | Túi khẩn cấp, bảo quản giấy tờ, kế hoạch gia đình và sơ tán | https://www.unicef.org/vietnam/vi/huong-dan-an-toan-truoc-bao |
| E03 | P0 | CDC — How to Create an Emergency Water Supply | EN | Lượng nước dự trữ tham khảo, dụng cụ chứa, thời gian bảo quản | https://www.cdc.gov/water-emergency/about/how-to-create-and-store-an-emergency-water-supply.html |
| E04 | P1 | American Red Cross — Anatomy of a First Aid Kit | EN | Chuẩn bị bộ sơ cứu và vật dụng cá nhân | https://www.redcross.org/get-help/how-to-prepare-for-emergencies/anatomy-of-a-first-aid-kit.html |
| E05 | P1 | American Red Cross — How to Prepare for Emergencies | EN | Kế hoạch gia đình, thông tin liên lạc, chuẩn bị theo loại thiên tai | https://www.redcross.org/get-help/how-to-prepare-for-emergencies.html |

**Chú ý bản địa hóa:** Không coi định mức dự trữ nước nước ngoài là định mức bắt buộc cho mọi hộ gia đình Việt Nam; điều chỉnh theo nhu cầu y tế, trẻ nhỏ và khuyến cáo địa phương.

## 5. 💧 Nước uống, thực phẩm, vệ sinh sau lũ — `HEALTH_WASH`

| ID | Ưu tiên | Nguồn / tài liệu | Ngôn ngữ | Nội dung nên thu thập | URL chính thức |
|---|---|---|---|---|---|
| H01 | P0 | Báo Điện tử Chính phủ dẫn hướng dẫn Bộ Y tế — Xử lý nước sinh hoạt mùa mưa bão | VI | Quy trình Việt Nam; phải kiểm tra lại hướng dẫn và liều lượng với cơ quan y tế khi dùng thực tế | https://baochinhphu.vn/bo-y-te-huong-dan-xu-ly-nuoc-sinh-hoat-mua-mua-bao-102281308.htm |
| H02 | P0 | CDC — How to Make Water Safe in an Emergency | EN | Nước uống khẩn cấp, phân biệt nhiễm vi sinh và hóa chất | https://www.cdc.gov/water-emergency/about/index.html |
| H03 | P0 | CDC — Make Water Safe Fact Sheet | EN; **VI available** | Tài liệu ngắn, có liên kết tải phiên bản tiếng Việt trên trang | https://www.cdc.gov/water-emergency/communication-resources/fact-sheet-making-water-safe-during-an-emergency.html |
| H04 | P0 | CDC — Keep Food Safe After a Disaster or Emergency | EN | Loại bỏ thực phẩm sau ngập/mất điện, vệ sinh bề mặt tiếp xúc đồ ăn | https://www.cdc.gov/food-safety/foods/keep-food-safe-after-emergency.html |
| H05 | P1 | CDC — Find Clean Water in an Emergency | EN | Nguồn nước thay thế, các giới hạn an toàn | https://www.cdc.gov/water-emergency/about/how-to-find-clean-water-in-an-emergency.html |
| H06 | P1 | CDC — Drinking Water Advisories: An Overview | EN | Phân biệt cảnh báo đun sôi, không uống, không sử dụng | https://www.cdc.gov/water-emergency/about/drinking-water-advisories-an-overview.html |
| H07 | P1 | CDC — Water Emergency Communication Resources | EN; có một số bản VI | Tờ rơi truyền thông về nước sạch, vệ sinh, phòng tiêu chảy | https://www.cdc.gov/water-emergency/communication-resources/index.html |
| H08 | P1 | WHO — Floods: How to protect your health | EN | Tổng quan nguy cơ bệnh đường nước và vệ sinh | https://www.who.int/news-room/questions-and-answers/item/how-do-i-protect-my-health-in-a-flood |

**Bảo vệ bắt buộc:** Không để chatbot tự nội suy nồng độ hóa chất/ liều xử lý nước khi không đủ loại sản phẩm và điều kiện. Nước nghi nhiễm nhiên liệu hay hóa chất độc không được coi là an toàn chỉ vì đã đun sôi.

## 6. 🏠 An toàn điện, quay lại nhà và vệ sinh sau lũ — `SECONDARY_HAZARDS`

| ID | Ưu tiên | Nguồn / tài liệu | Ngôn ngữ | Nội dung nên thu thập | URL chính thức |
|---|---|---|---|---|---|
| P01 | P0 | CDC — Electrical Hazards After a Disaster | EN | Dây điện đứt, thiết bị ngập, tránh điện giật | https://cdc.gov/natural-disasters/response/what-to-do-protect-yourself-from-electrical-hazards.html |
| P02 | P0 | CDC — Safety Guidelines: Reentering Your Flooded Home | EN | Điều kiện quay về nhà, kết cấu, điện, nước, thực phẩm | https://www.cdc.gov/floods/safety/reentering-your-flooded-home-safety.html |
| P03 | P0 | US EPA — Flooded Homes Cleanup Guidance | EN | Thư viện hướng dẫn dọn nhà, mốc, vật liệu, khí độc | https://www.epa.gov/flooded-homes |
| P04 | P0 | US EPA — Sổ tay dọn dẹp sau lũ (bản tiếng Việt) | VI | Tài liệu tiếng Việt về dọn nhà và chất lượng không khí sau lũ; có bản tải | https://www.epa.gov/mold/vietnamese-version-flood-cleanup-and-air-your-home-booklet |
| P05 | P1 | CDC — Mold Clean Up Guidelines | EN | Nguy cơ nấm mốc, ai không nên tham gia dọn dẹp, đồ bảo hộ | https://www.cdc.gov/mold-health/about/clean-up.html |
| P06 | P1 | CDC — Homeowners and Renters Guide to Mold Cleanup | EN; **VI available** | Tài liệu ngắn về dọn mốc, có bản tiếng Việt trên trang | https://www.cdc.gov/mold-health/communication-resources/guide-to-mold-cleanup.html |
| P07 | P1 | CDC — Guidelines for Cleaning Safely After a Disaster | EN | Thiết bị bảo hộ, làm sạch, điện giật, máy phát điện | https://www.cdc.gov/natural-disasters/safety/index.html |
| P08 | P1 | US EPA — Flood Cleanup to Protect Indoor Air and Your Health | EN | Không khí trong nhà, mốc và nguy cơ khi dọn dẹp | https://www.epa.gov/emergencies-iaq/flood-cleanup-protect-indoor-air-and-your-health |

**Chú ý:** Quy trình ngắt điện luôn phải giữ điều kiện “nếu thực hiện được một cách an toàn”; không khuyên người dân đi vào vùng nước ngập để tiếp cận cầu dao.

## 7. 👨‍👩‍👧 Trẻ em, người khuyết tật và hỗ trợ tâm lý — `VULNERABLE_GROUPS`

| ID | Ưu tiên | Nguồn / tài liệu | Ngôn ngữ | Nội dung nên thu thập | URL chính thức |
|---|---|---|---|---|---|
| V01 | P0 | UNICEF Việt Nam — An toàn trước lũ lụt dành cho cha mẹ | VI | Bảo vệ trẻ, đoàn tụ, an ủi trẻ sau lũ | https://www.unicef.org/vietnam/vi/an-toan-lu-lut-cha-me |
| V02 | P0 | CDC — Emergency Preparedness for People with Disabilities | EN | Kế hoạch riêng, phương tiện trợ giúp, rào cản khi sơ tán | https://www.cdc.gov/disability-emergency-preparedness/people-with-disabilities/index.html |
| V03 | P1 | WHO — Psychological First Aid: Guide for Field Workers | EN | Hỗ trợ tâm lý ban đầu, giao tiếp tôn trọng, giới hạn can thiệp | https://www.who.int/publications/i/item/9789241548205 |
| V04 | P1 | UNICEF Việt Nam — An toàn trước lũ quét và sạt lở đất | VI | Nhu cầu trẻ em, diễn tập và hỗ trợ sau thiên tai | https://www.unicef.org/vietnam/vi/an-toan-lu-quet-sat-lo-dat |

**Chú ý:** Giữ mức hỗ trợ tâm lý cơ bản; không để chatbot tự chẩn đoán, phán đoán nguy cơ cá nhân hay thay thế người có chuyên môn.

## 8. 🌧️ Nguy cơ liên quan: bão, lũ quét, sạt lở — `RELATED_HAZARDS`

| ID | Ưu tiên | Nguồn / tài liệu | Ngôn ngữ | Nội dung nên thu thập | URL chính thức |
|---|---|---|---|---|---|
| W01 | P0 | UNICEF Việt Nam — An toàn trước bão | VI | Chuẩn bị, an toàn khi bão và sau bão | https://www.unicef.org/vietnam/vi/huong-dan-an-toan-truoc-bao |
| W02 | P0 | UNICEF Việt Nam — Lũ quét và sạt lở | VI | Dấu hiệu nguy hiểm, sơ tán và hành động phòng ngừa | https://www.unicef.org/vietnam/vi/an-toan-lu-quet-sat-lo-dat |
| W03 | P0 | Cổng phòng chống thiên tai Việt Nam — Tài liệu lũ/lũ quét/sạt lở | VI | Thư mục tờ rơi, video và nguồn giáo dục cộng đồng | https://phongchongthientai.mard.gov.vn/Pages/tai-lieu-huong-dan-phong-chong-cac-loai-hinh-thien-tai-lu-lu-quet-sat-lo-dat.aspx |
| W04 | P1 | IFRC — Disaster Risk Reduction Key Messages (2nd ed.) | EN | Thông điệp cộng đồng; tài liệu hướng dẫn bản địa hóa | https://www.ifrc.org/document/public-awareness-and-public-education-disaster-risk-reduction-key-messages-2nd-edition |

## 9. 📡 Nguồn thông tin động — KHÔNG ingest thành kiến thức tĩnh

| ID | Hệ thống | Mục đích | Cách lưu / sử dụng | URL |
|---|---|---|---|---|
| L01 | Trung tâm Dự báo Khí tượng Thủy văn Quốc gia | Bản tin dự báo, cảnh báo lũ theo thời điểm | Retrieval riêng qua nguồn chính thức; lưu `issued_at`, `valid_until`, khu vực, URL, trạng thái | https://nchmf.gov.vn/ |
| L02 | Hệ thống thông tin cảnh báo lũ quét và sạt lở đất — Cục Khí tượng Thủy văn | Bản đồ/cảnh báo theo khu vực | Chỉ tích hợp khi có phương thức truy cập hợp lệ; không tự coi kết quả bản đồ là dữ liệu an toàn tuyệt đối | https://luquetsatlo.nchmf.gov.vn/ |

**Tuyệt đối không** biến bản tin cũ thành câu trả lời cho câu hỏi “Bây giờ ở xã tôi có lũ không?”. Phải hiển thị thời điểm dữ liệu, trạng thái và nguồn xác minh.

## 10. 📱 Tài liệu sử dụng app — phải tự tạo, không có URL công khai

Đây là **knowledge base riêng**: `APP_USAGE`. Nguồn chuẩn là tài liệu nội bộ do nhóm phát triển viết theo chức năng thực tế của app.

| ID | File Markdown nên tạo | Nội dung |
|---|---|---|
| A01 | `app_overview.md` | App làm được gì, giới hạn, phạm vi phục vụ |
| A02 | `rescue_request.md` | Gửi yêu cầu cứu hộ, thông tin bắt buộc, GPS, xác nhận đã gửi |
| A03 | `relief_request.md` | Đề nghị nước, đồ ăn, thuốc và các nhu yếu phẩm |
| A04 | `incident_report.md` | Báo ngập, cầu hỏng, sạt lở và trạng thái xác minh |
| A05 | `request_tracking.md` | Tra cứu, cập nhật và hủy yêu cầu nếu app hỗ trợ |
| A06 | `location_permission.md` | Bật GPS, nhập địa chỉ thủ công, xử lý thiếu quyền |
| A07 | `troubleshooting.md` | Mất mạng, gửi thất bại, upload ảnh lỗi, trạng thái pending |
| A08 | `privacy_and_scope.md` | Quyền riêng tư, dữ liệu thu thập, giới hạn chatbot |

**Metadata tối thiểu:** `app_version`, `platform`, `screen_id`, `feature`, `review_status`, `last_updated_at`. Không viết hướng dẫn hoặc đường dẫn màn hình khi tính năng chưa tồn tại.

---

## 11. Danh sách P0 để triển khai MVP nhanh

Nên lấy trước các **nguồn duy nhất**: F01, F02, S02, S03, S04, S06, M01, M03, M04, E01, E03, H01, H02, H03, H04, P01, P02, P03, P04, V02. Những mã lặp URL giữa các nhóm được dùng chung một tài liệu, không tạo bản sao.

**Trình tự:** tải/đọc nguồn → kiểm tra quyền sử dụng → extract → loại nhiễu → giữ cấu trúc và điều kiện an toàn → biên tập tiếng Việt nếu cần → review chuyên môn → chunk → gắn metadata → embedding → index → kiểm thử. Các nguồn y tế chưa qua duyệt giữ `PENDING_REVIEW` và loại khỏi retrieval của chatbot công khai.

## 12. Mẫu metadata cho một bản ghi nguồn

```json
{
  "source_id": "F01",
  "title": "Hướng dẫn an toàn trước lũ lụt dành cho cha mẹ",
  "publisher": "UNICEF Việt Nam",
  "url": "https://www.unicef.org/vietnam/vi/an-toan-lu-lut-cha-me",
  "language": "vi",
  "categories": ["FLOOD_KNOWLEDGE", "FLOOD_SAFETY", "VULNERABLE_GROUPS"],
  "source_type": "STATIC",
  "review_status": "PENDING_REVIEW",
  "license_checked": false,
  "medical_review_required": false,
  "source_catalog_checked_at": "2026-09-22",
  "content_extracted_at": null,
  "document_version": 1
}
```

**Lưu ý trạng thái:** `source_catalog_checked_at` chỉ thể hiện việc tìm thấy trang nguồn; **không đồng nghĩa** đã đọc toàn văn tệp đính kèm, kiểm tra bản quyền hoặc kiểm duyệt nội dung. Chỉ gắn `APPROVED` sau khi người có trách nhiệm duyệt nội dung thực tế.

## 13. Những nguồn còn cần nhóm dự án bổ sung trước khi phát hành

- Quy trình và số liên hệ cứu hộ/cấp cứu hiện hành theo địa bàn Việt Nam, xác nhận với cơ quan chức năng sở tại.
- Địa điểm trú ẩn, đường sơ tán, tình trạng cầu đường, mực nước: nguồn địa phương cập nhật có thời hạn.
- Hướng dẫn sơ cứu phiên bản tiếng Việt được chuyên gia y tế duyệt, đặc biệt CPR sau đuối nước và xử lý chảy máu.
- Tài liệu chuyên ngành phù hợp thành phố triển khai về ngập đô thị, triều cường, vận hành thoát nước.
- Toàn bộ hướng dẫn app theo phiên bản phát hành thực tế và các tình huống không có mạng.

---

**Ghi chú pháp lý và kiểm duyệt:** Có link công khai không có nghĩa được quyền tải, sao chép, dịch và tái phân phối toàn văn. Kiểm tra license/điều khoản từng nguồn và giữ attribution. Tài liệu này chỉ liệt kê nguồn và gợi ý phạm vi khai thác; không sao chép nguyên văn các tài liệu bên ngoài.
