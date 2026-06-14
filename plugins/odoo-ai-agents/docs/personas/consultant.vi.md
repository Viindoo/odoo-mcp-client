# Odoo Semantic - Hướng dẫn cho Tư vấn viên

> **Bắt đầu (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` -> `claude plugin install odoo-ai-agents@viindoo-plugins` (tự động kéo theo `odoo-semantic-mcp`) -> `/odoo-semantic-mcp:connect`. Với các công cụ AI khác, xem [hướng dẫn cài đặt client](../setup.md).

Dành cho tư vấn viên nghiệp vụ và kiến trúc sư giải pháp: nhanh chóng kiểm tra tính năng có sẵn hay không, hoàn tất phân tích khoảng cách (gap analysis), và xác định phạm vi tùy chỉnh trước khi cam kết báo giá.

---

## Công Cụ Này Giải Quyết Gì Cho Tư Vấn Viên

Những nỗi đau phổ biến nhất của tư vấn viên:

- **"Odoo có làm được X một cách nguyên bản không?"** - kiểm tra trước khi hứa với khách hàng
- **"Cái này là CE hay EE?"** - tránh tình huống phát hiện ngượng ngùng giữa dự án
- **"Tùy chỉnh này khó tới mức nào?"** - hiểu chuỗi kế thừa trước khi ước lượng
- **"Cho tôi xem một ví dụ có sẵn"** - chứng minh năng lực mà không cần dựng demo từ đầu

---

## Các Công Cụ Hữu Ích Nhất Cho Tư Vấn Viên

| Công cụ | Trả lời điều gì |
|------|----------------|
| `check_module_exists` | Tính năng này có nguyên bản không? CE hay EE? Phiên bản nào thêm vào? |
| `find_examples` | Cho tôi xem code Odoo thật làm điều gì đó tương tự |
| `lookup_core_api` | API này có tồn tại và có ổn định không? |
| `model_inspect` | Model này phức tạp đến đâu? Đã có bao nhiêu module mở rộng nó? |
| `impact_analysis` | Tùy chỉnh mà khách hàng muốn rủi ro tới mức nào? |
| `api_version_diff` | Có gì thay đổi giữa phiên bản hiện tại của khách và phiên bản nâng cấp mục tiêu? |

---

## Quy Trình Phân Tích Khoảng Cách Tính Năng

### 1. Kiểm tra tính sẵn có nguyên bản trước tiên

```
check_module_exists("account_budget", "17.0")
```

Lệnh này cho bạn biết: module có tồn tại không (có/không), CE hay EE, và liệu có rủi ro nhầm lẫn EE hay không (một addon miễn phí có tên tương tự dễ gây hiểu lầm).

### 2. Tìm các ví dụ tương đương

```
find_examples("kiểm soát ngân sách với quy trình phê duyệt và giới hạn theo cấp phòng ban", odoo_version='<version>')
```

Tìm kiếm ngữ nghĩa trên các repo đã được lập chỉ mục - trả về các đoạn code thật từ codebase khớp với điều bạn đang mô tả.

### 3. Hiểu độ phức tạp của model

```
model_inspect(model="account.budget", method="summary", odoo_version="17.0")
```

Số lượng trường, các module mở rộng, danh sách method. Nếu model có hơn 15 module mở rộng, rủi ro tùy chỉnh cao hơn - hãy tính điều đó vào ước lượng của bạn.

### 4. Kiểm tra lộ trình nâng cấp nếu cần

```
api_version_diff("account.move", "16.0", "17.0")
```

Nhanh chóng phát hiện các thay đổi gây phá vỡ (breaking changes) trước khi nói với khách hàng rằng việc nâng cấp sẽ suôn sẻ đến mức nào.

---

## Các Câu Hỏi Mẫu Cho Tư Vấn Viên

Các ví dụ gọi lệnh (một AI agent có thể chạy trực tiếp dưới dạng điều phối NL; người đọc có thể sao chép vào công cụ AI của mình):

1. **Kiểm tra tính sẵn có của tính năng:**
   > "Using odoo-semantic, Odoo 17.0 có module quản lý dịch vụ hiện trường (field service management) nguyên bản không? Là Community hay Enterprise?"

2. **Phân tích khoảng cách cho một khách hàng tiềm năng:**
   > "Using odoo-semantic, kiểm tra xem Odoo 17.0 Community có module đăng ký thuê bao / hóa đơn định kỳ (subscription / recurring invoice) không. Nếu chỉ có ở EE, những tính năng chính nào CE thiếu?"

3. **Phạm vi tùy chỉnh:**
   > "Using odoo-semantic, model_inspect account.move trong Odoo 17.0. Có bao nhiêu module mở rộng nó? Việc mở rộng nó cho phê duyệt hóa đơn có rủi ro HIGH không?"

4. **Chuẩn bị demo dựa trên ví dụ:**
   > "Using odoo-semantic, find_examples cho quy trình phê duyệt trên sale.order với xác nhận nhiều cấp. Cho tôi xem code thật từ các repo đã được lập chỉ mục."

5. **Tóm tắt rủi ro nâng cấp:**
   > "Using odoo-semantic, find_deprecated_usage cho Odoo 17.0. Khách của tôi đang ở 16.0. Top 3 rủi ro nào họ nên dự trù ngân sách?"

---

## Các Skill Plugin (Claude Code)

Nếu bạn dùng **Claude Code** với plugin Odoo AI Agent Team:

| Skill | Làm gì |
|-------|-------------|
| `/odoo-feature-check` | Báo cáo đầy đủ về tính sẵn có của tính năng: nguyên bản vs EE vs addon; bao gồm cờ CE/EE |
| `/odoo-gap-analysis` | Phân tích khoảng cách giữa yêu cầu của khách hàng và tính năng nguyên bản của Odoo; gắn cờ các năng lực CE còn thiếu |

---

## Đọc Hiểu Kết Quả

- **`is_ee_confusion: true`** - Có một module CE đã biết với tên tương tự; khách hàng thường nhầm lẫn giữa CE và EE. Hãy gắn cờ điều này trong đề xuất của bạn.
- **`Fields: N`** - Model có N trường trên tất cả các module mở rộng. Càng nhiều trường = càng phức tạp.
- **`Extends: N modules`** - N module tác động lên model này. Rủi ro mở rộng tùy chỉnh tăng theo N.
- **`status: deprecated`** từ `lookup_core_api` - API mà tùy chỉnh của bạn dựa vào đang bị loại bỏ. Đây là một rủi ro dự án.

---

## Ước Lượng Từ Kết Quả

| Tín hiệu | Hàm ý |
|--------|-------------|
| Model được hơn 10 module mở rộng | Tùy chỉnh có rủi ro trung bình đến cao - lên kế hoạch kiểm thử thêm |
| impact_analysis: Risk HIGH | Dự trù ngân sách gấp 2-3 lần ước lượng dev; việc này sẽ làm hỏng nhiều thứ |
| check_module_exists: EE only | Thêm chi phí license vào đề xuất |
| find_deprecated_usage: 3+ items | Dự án nâng cấp cần một giai đoạn khắc phục (remediation) |
