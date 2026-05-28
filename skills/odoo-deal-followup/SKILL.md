---
name: odoo-deal-followup
description: >
  Phân tích tình trạng deal Odoo/Viindoo và tạo hành động tiếp theo cho Sales AE hoặc CEO một-người
  vận hành go-to-market. Nhận context deal (tên khách, ngày liên hệ cuối, giai đoạn pipeline, cam
  kết trước đó) cộng với email/note thread tùy chọn, rồi xuất: (a) risk score (red/yellow/green),
  (b) next-best action recommendation, (c) draft email follow-up tiếng Việt (mặc định) hoặc tiếng
  Anh. Optionally gắn tag lý do deal bị blocked/at-risk nếu phát hiện tín hiệu. Kích hoạt ngay
  khi: "deal stalled", "khách lâu rồi chưa phản hồi", "follow up khách X", "viết email follow up",
  "phải làm gì với deal này", "khách trễ deadline phản hồi", "follow up on deal",
  "draft follow-up email", "customer hasn't replied", "what should I do with this stale
  opportunity", "đã hứa gửi báo giá mà chưa thấy phản hồi", "deal im lặng mấy tuần rồi",
  "mình nên gọi hay email khách này". Đặc biệt kích hoạt khi có tín hiệu thời gian ("đã 3 tuần",
  "2 tháng không liên hệ", "deadline tháng này") hoặc trạng thái mơ hồ ("không biết khách nghĩ
  gì", "không dám gọi vì sợ quấy rầy").
  DO NOT trigger for: (1) Tóm tắt buổi discovery/demo → dùng odoo-discovery-summarize.
  (2) Phản bác objection kỹ thuật từ khách → dùng odoo-objection-handler.
  (3) Tra cứu/chứng minh tính năng Odoo → dùng odoo-capability-proof hoặc odoo-feature-check.
  (4) Phân tích gap/scope đề xuất → dùng odoo-gap-analysis.
---

## Persona

Sales AE / CEO một-người-công-ty đang tự làm go-to-market Odoo hoặc Viindoo. Không có SDR hay
team sales hỗ trợ. Mỗi deal đều quan trọng. Skill này giúp tránh để deal nguội vì quên follow-up
hoặc không biết bước tiếp theo.

## Out of Scope

- Tóm tắt buổi discovery / ghi chú demo → dùng `odoo-discovery-summarize`
- Phản bác objection kỹ thuật của khách ("Odoo không làm được X") → dùng `odoo-objection-handler`
- Chứng minh tính năng bằng code evidence → dùng `odoo-capability-proof`
- Tra cứu feature đơn giản → dùng `odoo-feature-check`
- Phân tích gap / ước tính effort implementation → dùng `odoo-gap-analysis`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Skill này là standalone-first — OSM/MCP là OPTIONAL. Đa số lần gọi không cần MCP._

**OSM usage rule:** Chỉ invoke MCP tool khi user tường minh yêu cầu fact-check một claim kỹ
thuật về tính năng Odoo được nhắc đến trong email/deal context (ví dụ: "khách hỏi Odoo có làm
được multi-warehouse không — kiểm tra giúp"). Không tự động gọi MCP chỉ vì deal có liên quan
đến Odoo.

**Optional tool (on-demand only):**
- `check_module_exists` — Verify whether a specific Odoo module/feature exists and in which
  edition (CE/EE/Viindoo). Call only when user asks to fact-check a feature claim present in
  the deal thread or email. Do NOT call speculatively.

**Ollama delegation:** None. This skill performs text analysis and email composition — tasks
best handled by Claude directly. Do not delegate to ollama-delegate tools.
<!-- END GENERATED TOOLS -->

## Standalone-first workflow

Skill **luôn hoạt động không cần OSM**. Toàn bộ logic dưới đây chạy trên user-provided text.

### Round 0 — Parse deal context

Thu thập input từ user. Hỏi nếu thiếu.

**Required inputs:**
- Tên/nhãn khách (có thể abstract: "Khách A", "Công ty B") — KHÔNG cần tên thật nếu user muốn
  giữ bí mật
- Ngày liên hệ cuối cùng (hoặc "khoảng X ngày/tuần trước")
- Giai đoạn pipeline hiện tại (ví dụ: Qualified, Proposal sent, Negotiation, Demo done,
  Contract review)
- Cam kết / hứa hẹn đã đưa ra (ví dụ: "hứa gửi báo giá", "hẹn call thứ Sáu", "chờ họ xem demo")

**Optional inputs:**
- Email / note thread dán vào (bất kỳ ngôn ngữ nào)
- Expected close date
- Deal size category: Small (<50tr VND hoặc <$2K), Medium (50-500tr VND hoặc $2K-$20K),
  Large (>500tr VND hoặc >$20K) — KHÔNG cần số thực

Nếu user chỉ paste email thread mà không cung cấp context, extract thông tin từ thread trước
khi tiếp tục. Xác nhận lại nếu không chắc.

### Round 1 — Compute risk score

Dùng heuristic sau để phân loại:

| Signal | Điểm rủi ro |
|---|---|
| >30 ngày không phản hồi từ warm lead (đã có engagement) | +3 (Red trigger) |
| 14-30 ngày không phản hồi | +2 (Yellow trigger) |
| <14 ngày không phản hồi | +0 (Green, bình thường) |
| Deadline cam kết đã qua mà chưa deliver | +2 |
| Deal xuống stage thấp hơn (back-tracking) | +2 |
| Khách thay đổi điểm liên hệ (đổi người) | +1 |
| Khách đang trong giai đoạn procurement/tender (nhiều bên) | +1 |
| Có tín hiệu tích cực gần đây (khách chủ động hỏi) | -2 |
| Expected close date còn >60 ngày | -1 |

**Kết quả:**
- **Green** (tổng ≤1): Đang đi đúng hướng, follow-up thường.
- **Yellow** (tổng 2-3): Cần chủ động, có rủi ro nguội.
- **Red** (tổng ≥4): Deal có thể mất, cần hành động ngay.

Nếu thread email có tín hiệu "ghosting" (khách bỏ qua nhiều lần) hoặc "competitor mention"
→ bump thêm +1 Red.

### Round 2 — Identify next-best action

Dựa trên risk score + stage:

| Tình huống | Next-best action |
|---|---|
| Green — stage Proposal sent | Gentle check-in email, hỏi thêm câu hỏi |
| Yellow — stage Demo done | Re-engage with proof: gửi case study hoặc ROI mini |
| Yellow — stage Negotiation | Schedule call: đặt lịch cụ thể, không hỏi "bao giờ rảnh" |
| Red — stage bất kỳ, >30 ngày | Break-up email: trực tiếp, tôn trọng, để door open |
| Red — cam kết quá hạn | Apologize + deliver ngay + đặt lịch call |
| Red — tín hiệu đang so sánh đối thủ | Escalate with incentive: proof of value + ưu đãi giới hạn |
| Bất kỳ — không còn champion | Tìm lại stakeholder, hand-off nếu cần |

Kết quả Round 2 là **một dòng hành động ưu tiên cao nhất**.

### Round 3 — Draft follow-up email

Viết email theo ngôn ngữ mặc định **tiếng Việt** (chuyển sang tiếng Anh nếu user yêu cầu hoặc
nếu khách là công ty nước ngoài).

**Template 4 đoạn:**

1. **Warm reopener** — Mở đầu thân thiện, nhắc lại điểm liên hệ / buổi trao đổi cuối, KHÔNG
   mở bằng "Tôi chưa nhận được phản hồi từ bạn" (dễ gây áp lực tiêu cực).
2. **Value reinforcement** — Nhắc lại 1-2 giá trị cụ thể liên quan đến nhu cầu khách đã chia
   sẻ. Personalised — không dùng generic pitch.
3. **Clear ask** — Một hành động duy nhất, rõ ràng: đặt lịch call, xác nhận quyết định,
   review báo giá. Không hỏi nhiều câu hỏi cùng lúc.
4. **Low-friction CTA** — Đề xuất 2-3 khung giờ cụ thể HOẶC link đặt lịch. Kết bằng câu mở
   (leave door open) nếu đây là break-up email.

**Giọng văn:** Tự tin, tôn trọng, không năn nỉ. Phù hợp cho B2B Việt Nam.

### Round 4 — Output assembly

Tổng hợp kết quả từ Round 1-3 theo Output format bên dưới. Nếu thread email chứa claim kỹ
thuật về tính năng Odoo mà user có thể muốn fact-check, liệt kê vào mục "Optional: feature
claims to verify" — KHÔNG tự gọi MCP trừ khi user xác nhận muốn verify.

## Output format

```
## Deal status
- Risk: <red|yellow|green> — <lý do 1 câu>
- Last touch: <N> ngày trước
- Stage health: <on-track|slipping|stalled>
- Deal size category: <Small|Medium|Large|Unknown>

## Tags (nếu có tín hiệu)
<danh sách: blocked-by-procurement | ghosting | competitor-present | champion-changed |
commitment-overdue | budget-freeze | none>

## Next-best action
<Một dòng hành động ưu tiên — cụ thể, có thể thực hiện ngay>

## Draft email (tiếng Việt)

**Subject:** <subject line gợi ý>

<Đoạn 1 — Warm reopener>

<Đoạn 2 — Value reinforcement>

<Đoạn 3 — Clear ask>

<Đoạn 4 — CTA + close>

---
_Chuyển sang tiếng Anh: thêm yêu cầu "viết tiếng Anh" hoặc "in English" vào prompt._

## Optional: feature claims to verify
<Danh sách các claim kỹ thuật về Odoo/Viindoo trong thread — nếu có.
Ví dụ: "khách hỏi multi-warehouse → có thể fact-check bằng odoo-feature-check".
Nếu không có claim → ghi "None detected.">

## Suggest next skill
<Nếu cần: "Suggest: run odoo-objection-handler nếu khách đang phản đối tính năng cụ thể"
hoặc "Suggest: run odoo-capability-proof nếu cần gửi evidence package cho khách">
```

## Examples

### Example 1 — Yellow deal, manufacturing SME

**Context user cung cấp:**
- Khách: Khách A — SME sản xuất, ~200 nhân viên
- Liên hệ cuối: 18 ngày trước (sau buổi demo)
- Stage: Proposal sent
- Cam kết: đã gửi báo giá 3 tuần trước, hứa follow-up sau 1 tuần nhưng quên
- Thread: khách trả lời 1 lần sau demo nói "cần thời gian xem xét nội bộ"

**Output:**
- Risk: **yellow** — 18 ngày không phản hồi sau proposal, đã quá deadline follow-up tự cam kết
- Stage health: slipping
- Tags: commitment-overdue
- Next-best action: Gửi email check-in nhẹ nhàng, thừa nhận delay follow-up, đặt lịch call
  15 phút để giải đáp câu hỏi nội bộ (nếu có)
- Draft email: Mở bằng "Chào anh/chị [tên], hy vọng quá trình đánh giá nội bộ đang thuận
  lợi..." → nhắc lại 2 điểm mạnh phù hợp với sản xuất đã thảo luận trong demo → hỏi "Anh/chị
  có cần thêm thông tin gì để hoàn thiện đánh giá?" → đề xuất call 15 phút vào thứ Tư hoặc
  thứ Năm tuần này.

---

### Example 2 — Red deal, F&B chain, ghosting

**Context user cung cấp:**
- Khách: Khách B — chuỗi F&B, 5 cửa hàng
- Liên hệ cuối: 35 ngày trước
- Stage: Negotiation (đã qua demo + báo giá + 1 buổi negotiate)
- Cam kết: khách hứa "tuần sau trả lời" — đã 5 tuần trôi qua
- Thread paste vào: 3 email follow-up không có phản hồi

**Output:**
- Risk: **red** — 35 ngày không phản hồi sau negotiate, ghosting sau 3 follow-up
- Stage health: stalled
- Tags: ghosting, commitment-overdue
- Next-best action: Gửi break-up email — trực tiếp, tôn trọng, để door open. Không gửi thêm
  follow-up nếu không nhận phản hồi sau email này.
- Draft email:
  - Subject: "Kết thúc hành trình — và để ngỏ nếu timing thay đổi"
  - Đoạn 1: Nhắc lại cuộc trao đổi negotiate, thừa nhận mình đã follow-up nhiều lần.
  - Đoạn 2: Tóm gọn 1 câu giá trị: "Nếu bài toán quản lý chuỗi F&B vẫn còn — giải pháp
    vẫn phù hợp."
  - Đoạn 3: "Tôi sẽ đóng cơ hội này từ phía mình để không tiếp tục làm phiền anh/chị."
  - Đoạn 4: "Khi timing phù hợp hơn, anh/chị có thể liên hệ lại bất cứ lúc nào."
- Optional: feature claims to verify: None detected.

---

### Example 3 — Green deal, SaaS startup, proactive check-in

**Context user cung cấp:**
- Khách: Khách C — startup SaaS, 30 nhân viên
- Liên hệ cuối: 8 ngày trước (khách chủ động email hỏi thêm về module HR)
- Stage: Qualified (mới vào pipeline)
- Cam kết: chưa có cam kết cụ thể, đang nurture
- Deal size: Small

**Output:**
- Risk: **green** — 8 ngày, khách chủ động hỏi gần đây, stage mới vào pipeline
- Stage health: on-track
- Tags: none
- Next-best action: Trả lời câu hỏi về module HR + đề xuất buổi discovery call ngắn
- Draft email: Trả lời câu hỏi HR cụ thể → giới thiệu 1-2 tính năng liên quan khách chưa
  hỏi nhưng phù hợp startup → đề xuất "30-phút discovery call để mình hiểu thêm bài toán
  của team" → đề xuất 2 khung giờ tuần tới.
- Optional: feature claims to verify: "Khách hỏi Odoo HR có tích hợp chấm công qua app
  không → có thể fact-check bằng odoo-feature-check nếu muốn trả lời chính xác."
- Suggest next skill: Nếu khách bắt đầu đặt câu hỏi kỹ thuật sâu hơn → Suggest: run
  `odoo-feature-check`.

## Notes

- **Odoo version context:** Nếu user hoặc khách đề cập "Odoo X.0 có thể làm Y" trong email,
  skill sẽ flag claim đó vào mục "Optional: feature claims to verify". Nếu project có file
  `.odoo-ai/context.md`, main agent có thể đọc file đó để lấy Odoo version đang triển khai
  trước khi fact-check. (Phase B wiring — forward reference.)
- **Ngôn ngữ email:** Mặc định tiếng Việt. Chuyển tiếng Anh khi: (1) user yêu cầu, (2) khách
  là công ty nước ngoài rõ ràng từ context/thread, (3) thread email gốc viết tiếng Anh.
- **Không bịa thông tin:** Nếu user không cung cấp ngày liên hệ cuối hoặc stage, hỏi trước
  khi tính risk score. Không giả định.
- **Depth rule:** Skill này KHÔNG spawn subagent, KHÔNG invoke Skill tool. Mọi tham chiếu
  đến skill khác chỉ là gợi ý text ("Suggest: run X") — user tự quyết định có chạy không.
