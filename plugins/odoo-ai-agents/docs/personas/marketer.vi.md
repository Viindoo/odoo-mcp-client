# Odoo Semantic - Hướng dẫn cho Marketer

> **Bắt đầu (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` -> `claude plugin install odoo-ai-agents@viindoo-plugins` (tự kéo về `odoo-semantic-mcp`) -> `/odoo-semantic-mcp:connect`. Với các công cụ AI khác, xem [thiết lập client](../setup.md).

Tạo nội dung Odoo chính xác, có dữ liệu hậu thuẫn: bài so sánh phiên bản, bài làm nổi bật tính năng, hướng dẫn nâng cấp và bản tóm tắt năng lực - tất cả đều dựa trên dữ kiện thực từ codebase, không phải các tờ rơi tiếp thị.

---

## Công cụ này làm được gì cho Marketer

Nội dung tiếp thị về Odoo sống còn nhờ độ chính xác. Tuyên bố sai về tính năng, gán nhầm ranh giới CE/EE, hay số phiên bản lỗi thời đều bào mòn uy tín. Odoo Semantic MCP server cho phép bạn truy vấn chính codebase đã được lập chỉ mục để kiểm chứng các tuyên bố trước khi xuất bản.

Các trường hợp dùng:
- "Odoo 17 có gì mới so với 16?" - nhận thay đổi API thực tế, không chỉ là ghi chú phát hành
- "Odoo có [tính năng] trong bản Community không?" - kiểm chứng trước khi viết bảng so sánh
- "Cho tôi xem ví dụ code Odoo xử lý [quy trình nghiệp vụ] như thế nào" - cho các bài nội dung kỹ thuật

---

## Những công cụ hữu ích nhất cho Marketer

| Công cụ | Trả lời điều gì |
|------|----------------|
| `api_version_diff` | Thực sự đã thay đổi gì giữa hai phiên bản Odoo cho một model/API cụ thể |
| `find_examples` | Đoạn code thực minh họa cách một tính năng hoạt động - hữu ích cho bài blog kỹ thuật |
| `check_module_exists` | Tính năng này là CE hay EE? Phiên bản nào đã thêm nó? |
| `model_inspect` | Đối tượng nghiệp vụ cốt lõi này có bao nhiêu module và phần mở rộng? |

---

## Quy trình nghiên cứu nội dung

### Nội dung so sánh phiên bản

```
api_version_diff("sale.order", "16.0", "17.0")
```

Trả về thay đổi API thực tế - trường mới, phương thức bị loại bỏ, thay đổi trạng thái. Dùng cái này để viết các mục "Odoo 17 có gì mới" đúng sự thật thay vì chỉ dựa hoàn toàn vào ghi chú phát hành chính thức.

### Bảng tính năng CE và EE

```
check_module_exists("account_accountant", "17.0")
check_module_exists("sign", "17.0")
check_module_exists("website_livechat", "17.0")
```

Xây dựng bảng so sánh CE/EE chính xác. Công cụ trả về cờ `is_ee` cùng cảnh báo nhầm lẫn EE cho những tên module trông giống nhau.

### Phân tích kỹ thuật chuyên sâu

```
find_examples("quy trình đối soát hóa đơn đa tiền tệ", odoo_version='<version>')
```

Tìm kiếm code theo ngữ nghĩa trả về các ví dụ triển khai thực tế. Tuyệt vời cho việc viết nội dung kỹ thuật chính xác về cách Odoo xử lý các tình huống phức tạp.

---

## Câu hỏi mẫu của Marketer

Các lệnh gọi ví dụ (một AI agent có thể chạy trực tiếp qua NL dispatch; người đọc có thể chép vào công cụ AI của mình):

1. **Điểm nhấn phiên bản cho bài blog:**
   > "Using odoo-semantic, api_version_diff for account.move between Odoo 16.0 and 17.0. Tóm tắt các thay đổi chính bằng ngôn ngữ phi kỹ thuật cho độc giả blog."

2. **Bảng tính năng CE và EE:**
   > "Using odoo-semantic, kiểm tra xem các module này là CE hay EE trong Odoo 17.0: sign, account_accountant, project_forecast, helpdesk. Cho tôi một bảng."

3. **Nghiên cứu câu chuyện nâng cấp:**
   > "Using odoo-semantic, api_version_diff for sale.order between 15.0 and 17.0. Đâu là những thay đổi lớn nhất? Tôi đang viết hướng dẫn nâng cấp cho khách hàng."

4. **Nghiên cứu giải thích tính năng:**
   > "Using odoo-semantic, find_examples for inventory valuation with FIFO costing in Odoo 17. Cho tôi code thực để tôi mô tả cách nó hoạt động một cách chính xác."

5. **Tổng quan hệ sinh thái module:**
   > "Using odoo-semantic, model_inspect sale.order in Odoo 17.0. Có bao nhiêu module mở rộng nó? Đây là cho một bài về khả năng mở rộng của Odoo."

---

## Plugin Skills (Claude Code)

Nếu bạn dùng **Claude Code** với plugin Odoo AI Agent Team:

| Skill | Làm gì |
|-------|-------------|
| `/odoo-feature-highlights` | Tạo bản tóm tắt điểm nhấn tính năng cho một phiên bản Odoo cho trước, dựa trên dữ liệu API thực |
| `/odoo-addon-diff` | So sánh mức độ sẵn có và tính năng của module giữa hai phiên bản Odoo |

---

## Viết nội dung chính xác

**Dùng mẫu này cho các tuyên bố so sánh phiên bản:**

1. Chạy `api_version_diff` cho model hoặc API liên quan
2. Chạy `check_module_exists` cho bất kỳ module nào bạn nhắc đến
3. Ghi lại `odoo_version` trong lệnh gọi công cụ - luôn nêu rõ bạn đã kiểm chứng với phiên bản nào
4. Cho các tuyên bố CE/EE: trích dẫn cờ `is_ee` từ `check_module_exists`

**Những lỗi chính xác thường gặp cần tránh:**

| Tuyên bố sai | Cách kiểm chứng bằng MCP |
|-------------|----------------------|
| "Odoo 17 có [tính năng] miễn phí" | `check_module_exists` -> kiểm chứng `is_ee: false` |
| "Trong Odoo 17, name_get đã được thay thế bởi..." | `lookup_core_api("name_get", "17.0")` -> kiểm tra `status` |
| "Odoo đã thêm [API] ở phiên bản X" | `api_version_diff` -> trường `added_in` |
