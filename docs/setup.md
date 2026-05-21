# Client Setup — Odoo Semantic MCP

Hướng dẫn này dành cho **end user** muốn kết nối AI tool của mình vào một MCP server đã được admin deploy sẵn.

> **Bạn không cần cài gì** — chỉ cần URL + API key từ admin, rồi làm theo section tương ứng với AI tool đang dùng.

> **Quy ước trong các snippet:** thay `<MCP_URL>` bằng URL admin gửi (production:
> `https://odoo-semantic.viindoo.com/mcp`; local self-host: `http://127.0.0.1:8002/mcp`),
> và `<API_KEY>` bằng raw key (`osm_xxxxxxxx...`) admin cấp cho bạn (qua trang `/install/` hoặc Web UI).

> **Sai lầm chung 80% người mắc:** mỗi client lưu MCP config ở **file khác nhau**
> với **schema khác nhau**. Copy-paste snippet sai client → MCP **không load
> nhưng client cũng không báo lỗi** (chỉ "tool not found" khi gọi). Mỗi section
> dưới đây có canonical add command + JSON fallback + verify command + 1 pitfall
> đặc trưng của client đó.

> 💡 **Nhanh nhất:** truy cập **https://odoo-semantic.viindoo.com/install/** và dán API key — trang tự sinh snippet đúng cho từng client. Các section dưới đây là tài liệu tham khảo chính thức để setup nâng cao, troubleshooting, và auto-trust patterns.

---

## Claude Code

### Plugin install (recommended)

For Claude Code users, the plugin is the fastest path: it bundles the MCP server config, all 15 persona skills, and the setup command in one install.

#### 1. Add the Viindoo marketplace (one-time)

```bash
claude plugin marketplace add Viindoo/claude-plugins --scope user
```

Or inside Claude Code:
```
/plugin marketplace add Viindoo/claude-plugins
```

#### 2. Install the plugin

```bash
claude plugin install odoo-semantic@viindoo-plugins --scope user
```

Or:
```
/plugin install odoo-semantic@viindoo-plugins
```

#### 3. Configure API key and server URL

On first use, Claude Code will prompt for:
- **API Key** — starts with `osm_`, get it from your admin or the [install page](https://odoo-semantic.viindoo.com/install/)
- **MCP Server URL** — default `https://odoo-semantic.viindoo.com/mcp` (change for self-hosted)

Or run the interactive setup command:
```
/odoo-semantic:connect
```

#### 4. Verify

```
Using odoo-semantic tools, show the full inheritance chain of sale.order in Odoo 17.0
```

Expected: tree output with module names, `Defined in:`, field counts.

#### Available persona skills

After install, 15 skills activate automatically:

| Skill | Persona | Trigger |
|-------|---------|---------|
| `odoo-risk-overview` | CEO | "upgrade risk for our codebase" |
| `odoo-customization-inventory` | CEO | "list all our customizations" |
| `odoo-override-finder` | Developer | "where to override method X" |
| `odoo-deprecation-audit` | Developer | "audit deprecated API usage" |
| `odoo-version-diff` | Developer | "what changed between v16 and v17" |
| `odoo-coder` | Developer | "viết model/computed field/onchange" |
| `odoo-owl-coder` | Developer | "viết OWL component cho Odoo v15+" |
| `odoo-js-coder` | Developer | "viết JS widget cho Odoo v8-14" |
| `odoo-code-reviewer` | Developer | "review code Odoo (Python/JS/XML)" |
| `odoo-feature-check` | Consultant | "does Odoo have module X" |
| `odoo-gap-analysis` | Consultant | "gap analysis for client requirements" |
| `odoo-feature-highlights` | Marketer | "new features in Odoo 17" |
| `odoo-addon-diff` | Marketer | "CE vs EE comparison" |
| `odoo-capability-proof` | Sales | "prove Odoo can do X" |
| `odoo-objection-handler` | Sales | "handle objection about feature Y" |

---

> **Other AI tools (Codex, Gemini, VS Code, Antigravity):** The plugin is Claude Code only. For other tools, follow the per-client MCP config sections below.

---

### Manual MCP setup (advanced / self-hosted)
<a id="manual-mcp-setup-advanced--self-hosted"></a>

Docs: <https://code.claude.com/docs/en/mcp>

Cách 1 — CLI (recommended, official):
```bash
claude mcp add --scope user --transport http odoo-semantic <MCP_URL> \
    --header "X-API-Key: <API_KEY>"
```

Cách 2 — JSON fallback (file `~/.claude.json`, **không phải** `~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "type": "http",
      "url": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" }
    }
  }
}
```

Verify: `/mcp` trong session đang chạy, hoặc `claude mcp list` ngoài shell. Phải thấy `odoo-semantic … ✓ Connected`.

⚠️ **Pitfall 1 (rất phổ biến):** `~/.claude/settings.json` (cho permissions/hooks) **≠** `~/.claude.json` (cho MCP servers). README cũ ghi nhầm sang `settings.json` → MCP không bao giờ load. Nếu bạn từng làm theo README cũ: xoá entry `mcpServers.odoo-semantic` khỏi `~/.claude/settings.json`, rồi chạy lại `claude mcp add` ở Cách 1.

⚠️ **Pitfall 2:** Sau khi add phải **restart Claude Code** — entry mới không load runtime.

### Auto-trust: skip permission prompts
<a id="claude-code-auto-trust"></a>

> ✅ **Nếu bạn cài qua plugin Viindoo marketplace:** `/odoo-semantic:connect`
> hiện đã **tự động** thêm entry này vào `~/.claude/settings.json` (idempotent,
> có backup, không đụng tới các key khác). Trả `Y` ở prompt cuối — không cần
> đọc tiếp section này. Trả `n` → quay lại làm thủ công theo snippet dưới.

Snippet manual (cho ai cài qua `claude mcp add` raw, không qua plugin):

```json
{
  "permissions": {
    "allow": ["mcp__odoo-semantic"]
  }
}
```

> Nếu file đã có `permissions.allow`, chỉ thêm chuỗi `"mcp__odoo-semantic"` vào array.
> Wildcard không có tool name = pre-approve TẤT CẢ tool của server này.

---

## OpenAI Codex CLI

Docs: <https://developers.openai.com/codex/mcp>

Edit `~/.codex/config.toml` (CLI `codex mcp add` không có `--header` flag — phải edit TOML trực tiếp):
```toml
[mcp_servers.odoo-semantic]
url = "<MCP_URL>"
http_headers = { "X-API-Key" = "<API_KEY>" }
```

Restart Codex. Verify: `codex mcp list`.

⚠️ **Pitfall:** Phải dùng key `http_headers` (snake_case + plural). Viết `headers = ...` Codex sẽ silently ignore và server không gửi auth header → 401 từ MCP.

### auto-trust: skip permission prompts
<a id="codex-cli-auto-trust"></a>

> ⚠️ **Trade-off**: Codex CLI không có cơ chế pre-approve per-server. Mỗi tool sẽ
> bị hỏi xác nhận lần đầu sử dụng. Đây là giới hạn của OpenAI Codex, không phải
> server. Workaround duy nhất: set `approval_policy = "never"` trong config —
> nhưng ảnh hưởng tất cả tool khác, không khuyến nghị.

API key qua envvar (sạch hơn hardcode trong toml):

```bash
echo 'export ODOO_SEMANTIC_KEY="YOUR_API_KEY"' >> ~/.bashrc
```

Trong `~/.codex/config.toml`:
```toml
[mcp_servers.odoo-semantic]
url = "https://odoo-semantic.viindoo.com/mcp"
env_http_headers = { "X-API-Key" = "ODOO_SEMANTIC_KEY" }
```

---

## Google Gemini CLI

Docs: <https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md>

Edit `~/.gemini/settings.json` (user-global) hoặc `.gemini/settings.json` (project):
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "httpUrl": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" },
      "timeout": 10000
    }
  }
}
```

Restart `gemini`. Verify: `/mcp` trong CLI.

⚠️ **Pitfall:** Property phải là `httpUrl` (không phải `url`). Viết `url` thì Gemini coi là SSE deprecated transport → handshake hang/fail.

### auto-trust: skip permission prompts
<a id="gemini-cli-auto-trust"></a>

Thêm `"trust": true` vào server entry trong `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "odoo-semantic": {
      "httpUrl": "https://odoo-semantic.viindoo.com/mcp",
      "headers": { "X-API-Key": "YOUR_API_KEY" },
      "trust": true
    }
  }
}
```

> `"trust": true` = bypass mọi confirmation prompt cho server này.

---

## VS Code (built-in MCP, v1.99+)

Docs: <https://code.visualstudio.com/docs/copilot/reference/mcp-configuration>

Command Palette (`Ctrl/Cmd+Shift+P`) → **`MCP: Open User Configuration`** — file `mcp.json` mở ra:
```json
{
  "servers": {
    "odoo-semantic": {
      "type": "http",
      "url": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" }
    }
  }
}
```

Click **Start** codelens xuất hiện trên server block, hoặc reload window.

⚠️ **Pitfall:** Top-level key là `servers` (KHÔNG phải `mcpServers` như Claude/Gemini/Antigravity). `type` phải đúng `"http"` (KHÔNG phải `"streamable-http"`). KHÔNG đặt MCP servers vào `settings.json` — phải file `mcp.json` riêng.

### auto-trust: skip permission prompts
<a id="vs-code-auto-trust"></a>

VS Code không có config flag để pre-trust. Phải click **"Always allow for this
server"** trong Chat UI lần đầu gọi tool.

**One-click install URL** (paste vào browser, VS Code tự xử lý):

```
vscode:mcp/install?%7B%22name%22%3A%22odoo-semantic%22%2C%22type%22%3A%22http%22%2C%22url%22%3A%22https%3A%2F%2Fodoo-semantic.viindoo.com%2Fmcp%22%2C%22headers%22%3A%7B%22X-API-Key%22%3A%22YOUR_API_KEY%22%7D%7D
```

JSON pre-encode (replace `YOUR_API_KEY`):
```json
{"name":"odoo-semantic","type":"http","url":"https://odoo-semantic.viindoo.com/mcp","headers":{"X-API-Key":"YOUR_API_KEY"}}
```

> ⚠️ VS Code hiện chưa rõ có honor `headers` field trong URL handler không. Nếu
> install xong mà tool 401, thêm `headers` thủ công vào `.vscode/mcp.json`.

---

## Google Antigravity

Docs: <https://antigravity.google/docs/mcp>

IDE → **Manage MCP Servers → View raw config** — hoặc edit thẳng `~/.gemini/antigravity/mcp_config.json`:
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "serverUrl": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" }
    }
  }
}
```

Save → click **Refresh** ở MCP panel.

⚠️ **Pitfall:** Property phải là `serverUrl` (camelCase, không phải `url` hay `httpUrl`). File ở `~/.gemini/antigravity/` (chia sẻ prefix với Gemini CLI nhưng schema khác).

### auto-trust: skip permission prompts
<a id="antigravity-auto-trust"></a>

Sau khi add server: vào **...** → **MCP Servers** → tìm `odoo-semantic` →
add allow-list pattern `mcp(odoo-semantic.*)` để pre-approve tất cả tool.

> ⚠️ Antigravity chỉ có global config, không có project-level. API key lưu
> plaintext trong `~/.gemini/antigravity/mcp_config.json` — đảm bảo file
> permission 600.

---

## Session Context Setup (v0.5+) — `set_active_version` / `set_active_profile`

Starting in v0.5.0 the MCP server supports **sticky session context** so you stop repeating `odoo_version="17.0"` on every call. Run `set_active_version` once and the value is remembered for 24h per API key. Similarly `set_active_profile` pins the tenant profile.

**Recommended startup flow** for any AI client (Claude Code, Codex, Gemini, VS Code, Antigravity):

```
1. list_available_versions()    # see which Odoo versions the server has data for
2. set_active_version("17.0")   # pin the version for this session (24h TTL)
3. list_available_profiles()    # see which tenant profiles exist (optional)
4. set_active_profile("viindoo-internal")   # pin tenant profile (optional)
5. <any tool call with odoo_version omitted>   # falls back to the pinned value
```

After step 2, calling `model_inspect(model="sale.order", method="summary")` (no `odoo_version=` arg) returns results for `17.0`. Override at any time by passing `odoo_version=` explicitly on a single call (one-off; does **not** clear the sticky value).

> See [ADR-0029](https://github.com/Viindoo/odoo-semantic-server/blob/master/docs/adr/0029-implicit-session-context.md) for the TTL design and per-key keying rationale.

---

## MCP Resources (`odoo://` URI scheme, v0.5+)

In addition to the tool calls, the server exposes **7 MCP Resources** addressable via stable URIs — preferred when the caller already knows the entity ID and just wants the canonical record (read-only, bookmark-friendly, no parameters):

| URI template | Returns |
|--------------|---------|
| `odoo://{version}/model/{name}` | Model record (inheritance, field/method counts, modules) |
| `odoo://{version}/field/{model}/{field}` | Field record (type, compute, definition module) |
| `odoo://{version}/method/{model}/{method}` | Method record (override chain, super_ratio) |
| `odoo://{version}/module/{name}` | Module record (manifest, defines/extends counts) |
| `odoo://{version}/view/{xmlid}` | View record (xpath chain, inherit_id) |
| `odoo://{version}/pattern/{name}` | Pattern catalogue entry (code snippet + gotchas) |
| `odoo://{version}/stylesheet/{file_path}` | Stylesheet record (selectors, imports, variables) |

**Example:**

```
odoo://17.0/model/sale.order
odoo://17.0/field/sale.order/amount_total
odoo://17.0/view/sale.view_order_form
```

Clients that implement the MCP `resources/list` and `resources/read` flows surface these as bookmark-style references. See [ADR-0030](https://github.com/Viindoo/odoo-semantic-server/blob/master/docs/adr/0030-mcp-resources-uri-scheme.md) for the URI grammar and authorization model (same `X-API-Key` header as tool calls).

---

## Superset Tools — v0.6 Reference

v0.6 ships **18 tools**. The 10 flat `resolve_*` / `list_*` tools that existed in v0.4–v0.5 were deprecated in v0.5 and **removed in v0.6** — they no longer exist on the server. If you encounter prompts or snippets that reference the old names, replace them with the supersets below.

> The old `resolve_*` / `list_*` tools are gone. Use these supersets instead:

| Superset tool | Use case | Valid `method` values |
|---------------|----------|-----------------------|
| `model_inspect(model, method, ...)` | Model-level inspection: summary, field/method/view inventory | `summary` · `fields` · `methods` · `views` · `field` · `method` |
| `module_inspect(module, method, ...)` | Module-level inventory: manifest, views, OWL, QWeb, JS patches | `summary` · `views` · `owl` · `qweb` · `js` |
| `entity_lookup(kind, ...)` | Single entity drill-down by ID | kind: `field` · `method` · `view` |

**Full side-by-side migration guide:** the server [CHANGELOG](https://github.com/Viindoo/odoo-semantic-server/blob/master/CHANGELOG.md).

---

## Verify After Install — Natural-Language Prompts

Sau khi add xong, **gõ prompt tự nhiên** dưới đây vào AI tool — agent phải tự pick MCP `odoo-semantic` và gọi `model_inspect`. Nếu agent trả lời chung chung kiểu textbook về `sale.order` thay vì cite được module name + odoo_version từ index → MCP **chưa load đúng**, quay lại section của client tương ứng.

**English:**
- *"Using the odoo-semantic tools, show me the full inheritance chain of `sale.order` in Odoo 17.0 — which modules extend it?"*
- *"Inspect the model `sale.order` for version 17.0 and list all fields added by extension modules."*

**Tiếng Việt:**
- *"Dùng odoo-semantic, liệt kê toàn bộ inheritance chain của model `sale.order` trên Odoo 17.0 và cho biết module nào extend nó."*
- *"Trên phiên bản Odoo 17.0, model `sale.order` có những field nào và được kế thừa từ đâu?"*

**Tín hiệu đúng** trong response:
- Cite concrete module name từ index (`sale`, `sale_management`, `viin_sale`, `website_sale`, …)
- Có format cây `├─ … └─` (output canonical của tool)
- Có `Defined in: [<repo>] <module>` và `Inherits from: …` block
- Counts cụ thể như `Fields: 148` / `Methods: 394` (không phải con số tròn ước lượng)

**Tín hiệu sai** — agent đang answer bằng general knowledge:
- Trả lời prose dài về "sale.order is a model in Odoo's sales module …"
- Không có module name từ codebase đã index
- Không có format cây
- Không thừa nhận đã gọi tool nào

> 💡 **Self-host test trước khi prod**: thay `<MCP_URL>` bằng `http://127.0.0.1:8002/mcp`
> và làm theo [Local E2E Quickstart](https://github.com/Viindoo/odoo-semantic-server/blob/master/CONTRIBUTING.md) để chạy MCP server local.
