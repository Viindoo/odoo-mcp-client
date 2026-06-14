# Odoo Semantic - Hướng dẫn cho Quản lý / Người ra quyết định

> **Bắt đầu (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` -> `claude plugin install odoo-ai-agents@viindoo-plugins` (tự động kéo theo `odoo-semantic-mcp`) -> `/odoo-semantic-mcp:connect`. Với các công cụ AI khác, xem [client setup](../setup.md).

Bạn không cần hiểu mã nguồn của Odoo để khai thác giá trị từ công cụ này. Hãy đặt những câu hỏi bằng ngôn ngữ thông thường về rủi ro, chi phí nâng cấp và phạm vi tùy biến - và nhận lại những câu trả lời có cấu trúc rõ ràng mà đội ngũ của bạn có thể hành động ngay.

---

## Công Cụ Này Làm Gì Cho Bạn

Máy chủ Odoo Semantic MCP đã lập chỉ mục toàn bộ mã nguồn Odoo của bạn. Trợ lý AI của bạn (Claude Code, ChatGPT, Gemini) có thể truy vấn nó để trả lời các câu hỏi như:

- "Nếu nâng cấp từ Odoo 16 lên 17 thì sẽ ảnh hưởng đến bao nhiêu module tùy biến?"
- "Tính năng subscription thuộc bản Community hay Enterprise?"
- "Mức độ rủi ro của việc gỡ bỏ override `amount_total` tùy biến là bao nhiêu?"

Các câu trả lời này đến từ phân tích mã nguồn trực tiếp - không phải phỏng đoán.

---

## Các Công Cụ Hữu Ích Nhất Cho Quản Lý

| Công cụ | Trả lời điều gì |
|------|----------------|
| `impact_analysis` | Mức độ rủi ro (HIGH/MEDIUM/LOW) + những gì sẽ hỏng nếu thay đổi một field hoặc method |
| `find_deprecated_usage` | Những phần nào trong mã nguồn của bạn đang dùng các API mà Odoo sẽ gỡ bỏ ở phiên bản kế tiếp |
| `check_module_exists` | Một tính năng có sẵn trong bản Community Edition hay phải dùng Enterprise |
| `model_inspect` | Có bao nhiêu module đang tác động tới một đối tượng nghiệp vụ cho trước (ví dụ `sale.order`) |

---

## Những Câu Hỏi Bạn Có Thể Hỏi Trợ Lý AI

Ví dụ các câu lệnh (một AI agent có thể chạy trực tiếp dạng NL dispatch; người đọc cũng có thể sao chép):

1. **Quét rủi ro nâng cấp:**
   > "Using odoo-semantic, chạy find_deprecated_usage cho Odoo 17.0 trên codebase của chúng tôi. Tóm tắt các mục rủi ro HIGH bằng ngôn ngữ dễ hiểu."

2. **Kiểm kê tùy biến:**
   > "Using odoo-semantic, model_inspect sale.order trong Odoo 17.0 và cho tôi biết có bao nhiêu module mở rộng nó. Cái nào là tùy biến và cái nào là tiêu chuẩn?"

3. **Kiểm tra tính năng có sẵn:**
   > "Using odoo-semantic, Odoo 17.0 Community có module thanh toán theo thuê bao (subscription billing) không? Hay chỉ có ở bản Enterprise?"

4. **Đánh giá tác động của thay đổi:**
   > "Using odoo-semantic, chạy impact_analysis trên trường sale.order.amount_total trong Odoo 17.0. Mức rủi ro là gì và những gì sẽ hỏng?"

5. **So sánh giữa các phiên bản:**
   > "Using odoo-semantic, có gì thay đổi trong model account.move giữa Odoo 16.0 và 17.0? Tập trung vào các thay đổi gây phá vỡ (breaking changes)."

---

## Plugin Skills (Claude Code)

Nếu bạn dùng **Claude Code** với plugin Odoo AI Agent Team đã cài đặt, các slash command sau sẽ có sẵn:

| Skill | Làm gì |
|-------|-------------|
| `/odoo-risk-overview` | Chạy quét rủi ro nâng cấp - các API deprecated + tóm tắt tác động cho phiên bản của bạn |
| `/odoo-customization-inventory` | Liệt kê tất cả module tùy biến và các model Odoo chuẩn mà chúng mở rộng |

---

## Cách Đọc Kết Quả

Khi AI của bạn trả về kết quả từ các công cụ này, hãy lưu ý:

- **Risk: HIGH** - Việc này sẽ cần thời gian của lập trình viên để sửa trước khi nâng cấp. Hãy dự trù ngân sách tương ứng.
- **Risk: MEDIUM** - Nên được rà soát; có thể vẫn chạy tốt nhưng tiềm ẩn khả năng gây lỗi.
- **Risk: LOW** - An toàn để tiến hành với một ít rà soát.
- **EE Warning** - Tính năng yêu cầu giấy phép Odoo Enterprise, không có sẵn trong bản Community.
- **Defined in: [repo] module** - Đây là nơi chứa logic nghiệp vụ gốc.

---

## Bắt Đầu

1. Hỏi quản trị viên của bạn để lấy API key và URL máy chủ MCP
2. Thêm máy chủ MCP vào công cụ AI bạn chọn (xem trang cài đặt tại URL máy chủ của bạn)
3. Bắt đầu với: *"Using odoo-semantic, check_module_exists cho 'account_accountant' trong Odoo 17.0"*
