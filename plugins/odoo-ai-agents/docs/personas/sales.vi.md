# Odoo Semantic - Hướng dẫn cho Sales

> **Bắt đầu (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` -> `claude plugin install odoo-ai-agents@viindoo-plugins` (tự động kéo theo `odoo-semantic-mcp`) -> `/odoo-semantic-mcp:connect`. Với các công cụ AI khác, xem [client setup](../setup.md).

Biến mọi phản đối thành câu hỏi đã có lời giải trong vài giây. Kiểm chứng năng lực của Odoo ngay tại chỗ, lấy ví dụ code thật làm bằng chứng, và không bao giờ bị bất ngờ trước câu hỏi "Odoo có làm được X không?" giữa buổi demo.

---

## Công cụ này làm gì cho Sales

Khi khách hàng tiềm năng hỏi "Odoo có làm được X không?", bạn có hai lựa chọn: đoán, hoặc biết chắc. Odoo Semantic MCP server cho phép bạn truy vấn trực tiếp mã nguồn Odoo đã được lập chỉ mục để đưa ra câu trả lời xác thực, tự tin.

Các kịch bản chính:
- **Kiểm chứng tính năng:** "Odoo Community có [tính năng] không, hay phải dùng bản Enterprise?"
- **Chứng minh năng lực:** "Cho tôi thấy Odoo thực sự xử lý được [kịch bản nghiệp vụ]"
- **Xử lý phản đối:** "Khách hàng nói Odoo không làm được X - chứng minh họ sai (hoặc đúng)"
- **Định vị cạnh tranh:** "Odoo có gì mà đối thủ không có?"

---

## Các công cụ hữu ích nhất cho Sales

| Công cụ | Trả lời câu hỏi gì |
|------|----------------|
| `check_module_exists` | Tính năng này có sẵn không? CE hay EE? Phiên bản nào hỗ trợ? |
| `find_examples` | Code thật từ codebase cho thấy tính năng đang hoạt động |
| `model_inspect` | Phần triển khai của Odoo cho đối tượng nghiệp vụ này hoàn chỉnh đến đâu? |
| `impact_analysis` | (Cho phản đối kỹ thuật) Tính năng này trưởng thành/ổn định đến mức nào? |

---

## Quy trình chứng minh năng lực nhanh

### Xử lý "Odoo có X không?" tức thì

```
check_module_exists("sign", "17.0")
```

Trả về: module có tồn tại hay không, CE hay EE, cảnh báo nhầm lẫn EE nếu cần. Trả lời câu hỏi của khách hàng với sự chắc chắn.

### Trình diễn chức năng thật

```
find_examples("chữ ký số trên quy trình phê duyệt đơn mua hàng", odoo_version='<version>')
```

Trả về code thật từ các repo Odoo đã lập chỉ mục - không phải kịch bản demo, mà là bằng chứng triển khai thật. Dùng cái này khi khách hàng muốn bằng chứng rằng tính năng của Odoo đã sẵn sàng cho production, chứ không chỉ là một dấu tick đánh dấu.

### Khảo sát instance Odoo hiện có của khách hàng

```
model_inspect(model="sale.order", method="summary", odoo_version="16.0")
```

Xem có bao nhiêu module mở rộng các model lõi của họ. Nếu khách hàng đang dùng phiên bản cũ với nhiều tùy chỉnh nặng, điều này cho bạn biết độ phức tạp của việc nâng cấp trước cả đối thủ.

---

## Câu hỏi Sales mẫu

Các ví dụ gọi lệnh (một AI agent có thể chạy trực tiếp dưới dạng NL dispatch; người đọc có thể sao chép vào công cụ AI của mình):

1. **Kiểm tra năng lực nhanh:**
   > "Using odoo-semantic, Odoo 17.0 Community có module eSignature không? Hay chỉ có ở bản Enterprise? Khách hàng tiềm năng đang ở ngân sách CE."

2. **Bằng chứng tính năng cho khách hàng còn hoài nghi:**
   > "Using odoo-semantic, find_examples cho luồng mua-bán liên công ty đa công ty (multi-company intercompany purchase-to-sale) trong Odoo 17. Tôi cần cho khách hàng tiềm năng thấy đây là một tính năng nguyên bản thật sự."

3. **Xử lý phản đối 'Odoo không làm được X':**
   > "Using odoo-semantic, check_module_exists cho 'project_forecast' trong Odoo 17.0. Khách hàng tiềm năng nói Odoo không có lập kế hoạch nguồn lực. Điều đó có đúng không?"

4. **Đánh giá mức độ sẵn sàng nâng cấp của khách hàng:**
   > "Using odoo-semantic, api_version_diff cho sale.order giữa Odoo 14.0 và 17.0. Khách hàng tiềm năng đang ở v14. Cho tôi 3 cải tiến giá trị cao để nhắc tới."

5. **Câu chuyện thắng cạnh tranh:**
   > "Using odoo-semantic, model_inspect account.move trong Odoo 17.0 và cho tôi xem đầy đủ số lượng trường và các module mở rộng nó. Tôi muốn chứng minh chiều sâu kế toán của Odoo so với một nền tảng cạnh tranh."

---

## Plugin Skills (Claude Code)

Nếu bạn dùng **Claude Code** với plugin Odoo AI Agent Team:

| Skill | Làm gì |
|-------|-------------|
| `/odoo-capability-proof` | Cho một yêu cầu nghiệp vụ, trả về tính khả dụng CE/EE + ví dụ code thật từ các repo đã lập chỉ mục |
| `/odoo-objection-handling` | Cho một phản đối ("Odoo không làm được X"), kiểm tra codebase và trả về phản hồi dựa trên sự thật |
| `odoo-rfp-response` | Chấm điểm RFP theo từng yêu cầu thành ma trận tuân thủ (Yes / Partial / Roadmap / No + bằng chứng) + tóm tắt độ phù hợp |
| `odoo-pricing-proposal` | Soạn đề xuất báo giá hướng tới khách hàng - gói + các mức triển khai + SLA + điều khoản (bạn điền con số đơn giá) |
| `odoo-customer-health` | Chấm điểm sức khỏe của khách hàng hiện có - tín hiệu rủi ro rời bỏ + cơ hội upsell + đề xuất lần tiếp xúc tiếp theo |

---

## Đọc kết quả

- **`is_ee: false`** - Tính năng có trong Community Edition. Miễn phí cho khách hàng.
- **`is_ee: true`** - Cần giấy phép Enterprise. Tính vào thảo luận giá cả.
- **`is_ee_confusion: true`** - Có một module CE VÀ một module EE với tên tương tự. Cẩn thận - làm rõ khách hàng kỳ vọng gói nào.
- **`Fields: 148`** - Model có 148 trường qua tất cả phiên bản. Đây là bằng chứng cho một triển khai trưởng thành, giàu tính năng.
- **Code thật từ `find_examples`** - Đây không phải demo - đây là code production thật từ codebase của Odoo. Đó là lợi thế về độ tin cậy của bạn.

---

## Chuẩn bị cho buổi demo

Trước một buổi demo lớn, chạy các kiểm tra sau:

1. `check_module_exists` cho mọi tính năng bạn dự định trình diễn - kiểm chứng CE hay EE
2. `find_examples` cho 2-3 kịch bản then chốt - có sẵn các điểm chứng minh
3. `api_version_diff` nếu khách hàng đang nâng cấp - nắm rõ câu chuyện nâng cấp
4. `model_inspect` cho model lõi bạn đang demo - biết số lượng trường và độ sâu module
