# Odoo Semantic - Hướng dẫn cho Lập trình viên

<!-- Persona này cố ý liệt kê đầy đủ kho 25-tool arsenal (server v0.13.1) thay vì biến thể template "Most Useful Tools" - dev cần toàn bộ bề mặt công cụ, bao gồm 4 superset tools, 4 session-context tools, 11 base tools, 2 stylesheet tools, và 4 ORM-validation tools. -->

> **Bắt đầu (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` -> `claude plugin install odoo-ai-agents@viindoo-plugins` (tự kéo theo `odoo-semantic-mcp`) -> `/odoo-semantic-mcp:connect`. Với các công cụ AI khác, xem [client setup](../setup.md).

Toàn bộ **25-tool arsenal (server v0.13.1)**, tối ưu cho các quy trình phát triển. Từ việc hiểu inheritance, mở rộng an toàn các method lõi, liệt kê field/method/view và các artefact tầng UI (OWL, QWeb, JS patches), phân tích stylesheet CSS/SCSS/LESS, và nay là static ORM validation - hướng dẫn này bao quát các pattern hằng ngày. Toàn bộ **25 tools** tại server v0.13.1 được phân rã thành: bốn **supersets** định tuyến theo discriminator (`model_inspect`, `module_inspect`, `entity_lookup`, cộng thêm `profile_inspect` cấp profile cho thành phần profile / repos / kiểm kê module, v0.13+), bốn **session-context** tools cho phép bạn pin một phiên bản Odoo một lần và truyền nó dưới dạng `odoo_version='auto'` trên mọi lời gọi tiếp theo (v0.6+), mười một **base tools** mang theo từ v0.1-v0.4, hai **stylesheet tools** cho công việc theme/branding (v0.7+), và bốn **ORM-validation tools** bắt các field-path, operator, dependency, và relation target bị ảo giác (hallucinated) trước khi bạn ship một domain / `@api.depends` / relational field (v0.8+).

---

## Tất cả công cụ dành cho Lập trình viên (server v0.13.1)

### Supersets (v0.5+ - ưu tiên hơn các sibling cũ)

| Tool | Trường hợp dùng |
|------|----------|
| `model_inspect(model, method='summary'\|'fields'\|'methods'\|'views'\|'extenders'\|'field'\|'method', ...)` | Một lời gọi trả về summary của model, danh sách field, danh sách method, kiểm kê view, danh sách extender phân trang, hoặc drill-down một entity đơn lẻ. **Thay thế** `resolve_model` + `list_fields` + `list_methods` + `list_views`. |
| `module_inspect(module, method='summary'\|'views'\|'owl'\|'qweb'\|'js'\|'dependencies', ...)` | Kiểm kê cấp module qua manifest, models, views, OWL, QWeb, JS patches, dependencies. **Thay thế** `describe_module` + `list_views` (phạm vi module) + `list_owl_components` + `list_qweb_templates` + `list_js_patches`. |
| `entity_lookup(kind='field'\|'method'\|'view', ...)` | Drill-down một entity theo ID. **Thay thế** `resolve_field` + `resolve_method` + `resolve_view`. |
| `profile_inspect(profile, method='summary'\|'repos'\|'modules', ...)` | Introspection cấp profile: inheritance chain + repos + kiểm kê module (method=summary\|repos\|modules). |

### Session context (pin theo từng API-key, idle TTL 24h - racy khi concurrency)

| Tool | Trường hợp dùng |
|------|----------|
| `set_active_version(odoo_version)` | Pin phiên bản Odoo cho session này. Các lời gọi tiếp theo không có `odoo_version=` sẽ fallback về giá trị này. **Dùng một lần mỗi session debug/khám phá** để bỏ ~10 ký tự boilerplate khỏi mọi lời gọi. |
| `set_active_profile(profile_name)` | Pin tenant profile cho các deployment MCP cross-profile. |
| `list_available_versions()` | Khám phá xem server đã index những phiên bản Odoo nào. |
| `list_available_profiles()` | Khám phá xem có những profile nào tồn tại. |

### Existing tools (v0.1-v0.4, không đổi)

| Tool | Trường hợp dùng |
|------|----------|
| `find_examples` | Tìm kiếm code ngữ nghĩa trên các repo đã index |
| `impact_analysis` | Đánh giá rủi ro trước khi thay đổi một field hoặc method |
| `lookup_core_api` | Xác minh một API symbol tồn tại và chưa bị deprecated |
| `api_version_diff` | Nhận diện các breaking change giữa các phiên bản Odoo |
| `find_deprecated_usage` | Rà soát module của bạn xem có dùng API đã deprecated |
| `lint_check` | Kiểm tra module theo chuẩn coding Odoo; `# noqa: RULE_ID` inline trong code suppress các finding trên dòng đó |
| `suggest_pattern` | Tìm pattern triển khai chuẩn mực |
| `check_module_exists` | Xác minh tính sẵn có của module + cờ CE/EE |
| `find_override_point` | Định vị method an toàn nhất để override |
| `cli_help` | Tra cứu các flag và tùy chọn của `odoo-bin` |
| `describe_module` | Tổng quan kiến trúc module - manifest + các model định nghĩa/mở rộng + số lượng view/JS |

### Stylesheet tools (v0.7+)

| Tool | Trường hợp dùng |
|------|----------|
| `resolve_stylesheet(module, odoo_version="auto")` | Liệt kê các file stylesheet CSS/SCSS/LESS của module - ngôn ngữ, số lượng selector/variable/mixin/import, chuỗi `@import`. Dùng để rà soát những gì một module ship trước khi viết theme override. LESS bao phủ kỷ nguyên cũ tiền-SCSS (~v8-v12). |
| `find_style_override(selector_or_variable, odoo_version="auto", limit=5)` | Tìm nơi một CSS selector hoặc SCSS/LESS variable được định nghĩa lần đầu và những module nào override nó, kèm toàn bộ override chain. Thiết yếu cho công việc theming/branding. Bao phủ CSS, SCSS, và LESS (LESS cho kỷ nguyên cũ tiền-SCSS, ~v8-v12). |

### ORM-validation tools (server v0.8.0+)

Các kiểm tra tĩnh dựa trên graph đã index. Chạy chúng **trước khi** phát ra một domain, `@api.depends`, hoặc relational field - chúng bắt các field-path bị ảo giác, operator không hợp lệ, và comodel sai mà nếu không sẽ chỉ lộ ra lúc runtime.

| Tool | Trường hợp dùng |
|------|----------|
| `resolve_orm_chain(model, dotted_path, odoo_version="auto")` | Đi qua một dotted field path (`partner_id.country_id.code`) từng hop một; trả về kiểu của field cuối hoặc một dòng `BROKEN` nêu tên hop đầu tiên không resolve được. Dùng để xác minh một chuỗi `related=` đa hop hoặc domain path có resolve hay không. |
| `validate_domain(model, domain, odoo_version="auto")` | Validate mọi term `(field_path, operator, value)` của một search domain. Tính hợp lệ của operator là **version-aware** (`parent_of` v9+, `any`/`not any` v17+). Chạy trước khi dán một domain vào view, `ir.rule`, hoặc `search()`. |
| `validate_depends(model, method, odoo_version="auto")` | Validate các path `@api.depends('a.b', ...)` của một compute method đã index; cờ depends trên `id` (bị cấm) và gợi ý field gần nhất cho các lỗi typo - bắt trực tiếp failure mode "stale compute". |
| `validate_relation(model, field, target_model, odoo_version="auto")` | Khẳng định một field là many2one/one2many/many2many có comodel là `target_model` (hoặc một subtype qua inheritance). Dùng trước khi viết một `related=` hop qua một relation. |

> Ưu tiên những công cụ này hơn `entity_lookup(kind='field', ...)` khi bạn có một *path* (`resolve_orm_chain`), một *full domain* (`validate_domain`), một *declared depends* (`validate_depends`), hoặc một *comodel assertion* (`validate_relation`) - chúng suy luận về toàn bộ cấu trúc, không phải một field đơn lẻ.

### Removed in v0.6

10 flat tool (`resolve_model`, `resolve_field`, `resolve_method`, `resolve_view`, `list_fields`, `list_methods`, `list_views`, `list_owl_components`, `list_qweb_templates`, `list_js_patches`) đã bị deprecated ở v0.5 và **removed in v0.6**. Chúng không còn tồn tại trên server. Hãy dùng các superset ở trên.

Xem server [CHANGELOG](https://odoo-semantic.viindoo.com/changelog) để có các ví dụ migration đặt cạnh nhau.

### MCP Resources (`odoo://` URI scheme, v0.5+)

Các handle chỉ-đọc cho truy cập ổn định kiểu bookmark. Dùng những cái này khi bạn đã biết entity ID và muốn lấy bản ghi chuẩn mực mà không cần một tool call: `odoo://{version}/{kind}/{id}` trong đó `kind` là một trong `model`, `field`, `method`, `view`, `module`, `pattern`, `stylesheet`. Xem [tài liệu MCP resources URI scheme](https://odoo-semantic.viindoo.com/docs/adr/0030-mcp-resources-uri-scheme).

---

## Quy trình Phát triển Chuẩn

### 0. Pin phiên bản một lần

Trước bất kỳ session khám phá nào, đặt phiên bản để bạn có thể bỏ `odoo_version=` khỏi mọi lời gọi tiếp theo:

```
set_active_version("<version>")
```

TTL là idle 24h và pin là server state theo từng API-key - bất kỳ agent hoặc session đồng thời nào dùng chung key đều có thể ghi đè nó, vì vậy hãy truyền phiên bản cụ thể trên mọi lời gọi khi có concurrency. Chạy `list_available_versions()` trước nếu bạn không chắc những phiên bản nào đã được index.

### 1. Hiểu trước khi đụng vào

Trước khi thêm logic vào một model:

```
model_inspect(model="sale.order", method="summary", odoo_version='<version>')
```

Lấy toàn bộ inheritance chain, số lượng field, danh sách method, kiểm kê view, và những module nào đã mở rộng model này - tất cả trong một lời gọi. Hãy biết bạn đang bước vào cái gì trước khi viết một dòng nào.

> Cần một entity cụ thể? Drill-down bằng `entity_lookup(kind="field", model="sale.order", field="amount_total", odoo_version='<version>')` (hoặc `kind="method"` / `kind="view"`).

### 2. Tìm đúng extension point

Trước khi viết một `@api.onchange`, `_compute_*`, hoặc lời gọi `super()`:

```
find_override_point("sale.order", "action_confirm", "<version>")
```

Trả về điểm `super_safety` và những module nào đang override method này. Nếu `super_ratio` thấp, override của bạn có rủi ro cao hơn bị gọi sai thứ tự.

### 3. Lấy đúng pattern

Trước khi triển khai một pattern mới (computed cross-model field, wizard, report):

```
suggest_pattern("computed field that aggregates from child records with currency conversion", odoo_version='<version>')
```

Trả về các pattern entry được tuyển chọn kèm code snippet, gotcha, và cảnh báo anti-pattern từ codebase đã index.

### 4. Xác minh API

Trước khi gọi bất kỳ decorator `@api.*`, `name_get`, `_name_search`, hoặc ORM method nào:

```
lookup_core_api("name_get", "<version>")
```

Nếu kết quả hiển thị `status: deprecated` hoặc `removed_in: <version>` - hãy tìm phương án thay thế trước khi xây dựng dựa trên nó.

### 5. Kiểm tra công việc của bạn

Sau khi viết module:

```
lint_check(code=<module source>, odoo_version='<version>')
find_deprecated_usage(odoo_version='<version>')
```

---

## Câu hỏi mẫu của Lập trình viên

Các ví dụ invocation (một AI agent có thể chạy trực tiếp dưới dạng NL dispatch; người đọc có thể copy vào công cụ AI của họ):

1. **Khám phá model (superset):**
   > "Using odoo-semantic, inspect account.move với method=summary trong Odoo 17.0. Hiển thị inheritance chain và nhóm các field theo module."

2. **Mở rộng an toàn:**
   > "Using odoo-semantic, find_override_point cho account.move action_post trong Odoo 17.0. Có an toàn để override không? super_ratio là bao nhiêu?"

3. **Tra cứu pattern:**
   > "Using odoo-semantic, suggest_pattern để triển khai một onchange cập nhật một computed monetary field qua nhiều model trong Odoo 17."

4. **Rà soát tiền-nâng-cấp:**
   > "Using odoo-semantic, find_deprecated_usage cho Odoo 17.0 trong codebase của chúng tôi. Liệt kê tất cả các mục rủi ro HIGH kèm vị trí file."

5. **Override view (superset):**
   > "Using odoo-semantic, entity_lookup kind=view xmlid=sale.view_order_form trong Odoo 17.0. Hiển thị toàn bộ XPath chain để tôi biết chính xác chỗ chèn override của mình."

6. **Pin session:**
   > "Using odoo-semantic, set_active_version 17.0 cho session này. Sau đó inspect sale.order method=summary - không cần lặp lại phiên bản ở các lời gọi tiếp theo."

7. **ORM validation (trước khi ship một domain / depends):**
   > "Using odoo-semantic, validate_domain trên sale.order cho `[('partner_id.country_id.code', '=', 'US'), ('state', 'any', ...)]` trong Odoo 16 - các field-path và operator có hợp lệ cho phiên bản đó không?" (và: "validate_depends cho _compute_amount_total trên sale.order - tất cả các path @api.depends có thật không?")

---

## Plugin Skills (Claude Code)

Nếu bạn dùng **Claude Code** với plugin Odoo AI Agent Team:

| Skill | Chức năng |
|-------|-------------|
| `odoo-solution-design` | Thiết kế giải pháp kỹ thuật (approach / data model / override strategy / module structure / sequencing / test outline / risks) thành một design doc có thể gate được TRƯỚC KHI code - bước phân tích-và-thiết-kế cho công việc không tầm thường; chain tới `odoo-coding` |
| `/odoo-override-finding` | Cho một model + method, trả về safe override point + các override hiện có + suggest_pattern |
| `/odoo-deprecation-audit` | Quét đầy đủ API deprecated kèm gợi ý thay thế |
| `/odoo-version-diff` | API diff đặt cạnh nhau giữa hai phiên bản Odoo cho một symbol cho trước |
| `odoo-test-writing` | Viết `test_*.py` (hoặc JS Hoot/QUnit) thực thi được, assert hành vi nghiệp vụ, không phải code hiện trạng |
| `odoo-security-audit` | Rà soát code tìm SQLi / XSS / access-control / CSRF / unsafe deserialization, finding được phân hạng |
| `odoo-perf-audit` | Rà soát N+1, thiếu prefetch, domain không index, compute thrash, kèm các fix cụ thể |
| `odoo-data-migration` | Viết script migration pre/post + kế hoạch xác minh (không thực thi trên một instance) |
| `/odoo-ai-agents:odoo-run-wave` | Điều phối git-wave: integration branch + WI worktree + cherry-pick + Opus review cuối wave + 1 PR + squash + tree-identity gate + human-confirm merge. Dùng khi land N thay đổi WI song song một cách an toàn mà không đụng vào principal branch. |

---

## Mẹo

- Luôn truyền tham số `odoo_version` - kết quả khác nhau đáng kể giữa các phiên bản.
- `find_override_point` trả về `anti_patterns` - đọc chúng trước khi viết.
- Nếu `model_inspect` cho thấy hơn 10 module mở rộng một model, hãy cân nhắc liệu logic mở rộng của bạn có thể xung đột với những cái khác.
- Các query `suggest_pattern` là ngữ nghĩa, không phải keyword - mô tả điều bạn muốn đạt được, không phải method nào muốn dùng.
