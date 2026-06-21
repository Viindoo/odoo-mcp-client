# Smoke test: odoo-doc-illustration on viin_approval (post-PR-#105)

**Muc tieu:** xac nhan cap agent `odoo-doc-illustrator` + skill `odoo-doc-illustration`
chup anh live tu browser that, ghi dung dich, sinh `index.html`+`index_vi_VN.html`+`doc/index.rst`
tren module thuc `viin_approval` sau khi PR #105 merge vao.

---

## 1. Tien de / Setup

| Dieu kien | Kiem tra nhanh |
|---|---|
| Odoo 17 instance dang chay | `curl -s <base_url>/web/login | grep -q "Odoo"` |
| `viin_approval` (+ depends) da install | `mcp__odoo__search_records model=ir.module.module domain=[['name','=','viin_approval'],['state','=','installed']]` |
| Browser MCP (playwright headless) phan hoi | `mcp__plugin_odoo-ai-agents_playwright__browser_navigate url=<base_url>/web/login` |
| OSM reachable | `mcp__odoo-semantic__check_module_exists module_name=viin_approval` |
| `.odoo-ai/context.md` co `odoo_version`, `instance_base_url`, `instance_login` | `cat $HOME/git/tvtmaaddons17/.odoo-ai/context.md` |

**Neu chua co instance:** chay skill `odoo-instance` truoc:

```
/odoo-ai-agents:odoo-instance
operation: ensure-up
series: "17.0"
modules: ["viin_approval"]
```

Hoac `odoo-setup` neu can cai dat moi hoan toan.

---

## 2. Brief mau - dispatch skill

Chay qua slash command hoac subagent invoke:

```
/odoo-ai-agents:odoo-doc-illustration

MODE: module
TARGET: $HOME/git/tvtmaaddons17/viin_approval
DOC LAYER: both
BROWSER MODE: headless
USER LANGUAGE: vi
SCREENS: main list view, form view (draft), approval flow panel
```

> `DOC LAYER: both` = sinh ca `static/description/index.html` (+ `index_vi_VN.html`) va `doc/index.rst`.
> Ngon ngu resolve tu `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` key `default_languages`.
> SCREENS la goi y; agent tu quyet dua tren ket qua OSM module_inspect cho danh sach view.

---

## 3. Cac buoc chay (danh so)

1. **Kiem tra tien de** - xac nhan tat ca o Section 1 truoc khi dispatch.
2. **Dispatch brief** - paste brief mau o Section 2 vao prompt.
3. **Quan sat Step 0** - agent doc `.odoo-ai/worklog/` va `.odoo-ai/context.md`; neu `NEEDS_CONTEXT` tra lai -> bo sung truong con thieu roi dispatch lai.
4. **Quan sat Step 1** - agent resolve `$HOME/git/tvtmaaddons17/viin_approval/` va xac nhan `__manifest__.py`; neu `NEEDS_CONTEXT` -> kiem tra `addons_path` trong context.
5. **Quan sat Step 2 (OSM)** - module_inspect lay views va model_inspect lay summary chay song song; ket qua quyet dinh danh sach screen.
6. **Quan sat Step 3 (auth)** - agent navigate `/web/login`, dang nhap bang `instance_login` tu context.
7. **Quan sat Step 4 (capture)** - agent chup tung screen; moi screenshot phai dung flow 2-tier (relative filename -> tool tra `actual path` -> Bash `cp` sang `static/description/`).
8. **Quan sat Step 5 (assemble)** - agent ghi `index.html`, `index_vi_VN.html`, `doc/index.rst`.
9. **Quan sat Step 6 (manifest)** - agent doc roi Edit `__manifest__.py`, bo sung key `'images'`.
10. **Kiem tra checklist PASS/FAIL** (Section 4).

---

## 4. Ky vong quan sat duoc - PASS/FAIL checklist

### A. Hinh anh (screenshot live)

| # | Ky vong | Cach kiem | PASS | FAIL |
|---|---|---|---|---|
| A1 | Anh nam trong `viin_approval/static/description/`, KHONG phai `.playwright-mcp/` hay `/tmp/` | `ls $HOME/git/tvtmaaddons17/viin_approval/static/description/*.png` | co file | khong co / sai thu muc |
| A2 | Ten file dung naming convention module: `omniapproval_<feature>.png` hoac `main_screenshot.png` | `ls viin_approval/static/description/*.png \| grep -v omniapproval \| grep -v main_screenshot` | output rong | co file khong khop |
| A3 | Khong con file tam trong `.playwright-mcp/doc-staging/` sau khi xong | `ls $HOME/git/tvtmaaddons17/.playwright-mcp/doc-staging/ 2>/dev/null` | thu muc rong hoac khong ton tai | con file .png |
| A4 | Kich thuoc anh hop ly: screenshot chinh >= 1200x800, banner (neu co) = 1280x600, icon 128x128 | `file viin_approval/static/description/*.png \| grep -oP '\d+x\d+'` hoac Python `PIL.Image.open` | khop nguong | nho hon nguong |
| A5 | Anh la live screenshot Odoo that (co Odoo UI, KHONG phai composite/placeholder) | mo file bang image viewer hoac check pixel entropy (file >=50KB thuong la real screenshot) | nhin thay Odoo UI that | anh trang / composite / error placeholder |

### B. HTML artifact

| # | Ky vong | Cach kiem | PASS | FAIL |
|---|---|---|---|---|
| B1 | `index.html` ton tai va duoc ghi/cap nhat | `stat viin_approval/static/description/index.html` | timestamp moi | khong ton tai / timestamp cu |
| B2 | `index_vi_VN.html` ton tai (DOC LAYER: both) | `stat viin_approval/static/description/index_vi_VN.html` | ton tai | khong ton tai |
| B3 | `<img src>` trong HTML la RELATIVE (`./file.png` hoac `file.png`), KHONG phai absolute `/home/...` | `grep -oP 'src="[^"]*"' viin_approval/static/description/index.html` | `src="./...png"` | `src="/home/..."` hoac `src="http..."` |
| B4 | Alt text mang noi dung OSM (tieu de field / view name), khong blank | `grep -oP 'alt="[^"]*"' viin_approval/static/description/index.html \| grep 'alt=""'` | output rong | co `alt=""` |
| B5 | HTML valid (khong loi parse) | `python3 -c "from html.parser import HTMLParser; p=HTMLParser(); p.feed(open('viin_approval/static/description/index.html').read())"` | khong exception | SyntaxError / ParseError |

### C. RST artifact (DOC LAYER: both)

| # | Ky vong | Cach kiem | PASS | FAIL |
|---|---|---|---|---|
| C1 | `doc/index.rst` ton tai | `stat viin_approval/doc/index.rst` | ton tai | khong ton tai |
| C2 | `.. image::` directives dung relative path | `grep ".. image::" viin_approval/doc/index.rst` | `.. image:: ../static/description/file.png` hoac `.. image:: file.png` | absolute path |
| C3 | RST parse duoc (khong loi) | `python3 -m docutils viin_approval/doc/index.rst /tmp/rst-check.html && echo OK` | OK | Error |

### D. Manifest

| # | Ky vong | Cach kiem | PASS | FAIL |
|---|---|---|---|---|
| D1 | `__manifest__.py` co key `'images'` tro toi it nhat 1 file trong `static/description/` | `python3 -c "import ast; m=ast.literal_eval(open('viin_approval/__manifest__.py').read()); print(m.get('images','MISSING'))"` | list khong rong | `MISSING` hoac `[]` |
| D2 | File tro trong `'images'` thuc su ton tai | `python3 -c "import ast, os; m=ast.literal_eval(open('viin_approval/__manifest__.py').read()); [print(p, os.path.exists('viin_approval/'+p)) for p in m.get('images',[])]"` | tat ca `True` | co `False` |

### E. Ngon ngu

| # | Ky vong | Cach kiem | PASS | FAIL |
|---|---|---|---|---|
| E1 | Ngon ngu tai lieu khop `default_languages` trong `i18n.json` | `cat ${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json \| python3 -c "import sys,json; print(json.load(sys.stdin)['default_languages'])"` roi so voi file sinh ra | so luong file HTML khop so luong ngon ngu | thieu 1 ngon ngu |

---

## 5. Diem de vo - checklist debug

Khi co FAIL, soi theo thu tu nay:

| # | Diem de vo | Cach xac nhan | Fix hudong |
|---|---|---|---|
| F1 | **allowed-roots cp bo sot** - anh ghi vao `.playwright-mcp/` nhung `cp` khong chay | `ls .playwright-mcp/doc-staging/*.png` va `ls viin_approval/static/description/*.png` so sanh | agent chua chay Bash `cp` sau capture - kiem tra Step 4 log |
| F2 | **Convention-detect sai** - agent hardcode `main_screenshot` thay vi detect `omniapproval_<feature>` | Grep brief/output cho `omniapproval` vs `main_screenshot` | agent phai doc manifest/views truoc khi dat ten; check OSM `module_inspect` Step 2 co chay khong |
| F3 | **Marker hybrid `[Hinh anh:]`** - neu agent dispatch `odoo-content-draft` (MODE: cluster hoac marketing brief) ma quen replace marker | `grep "\[Hinh anh:\]" viin_approval/doc/index.rst index.html` | neu con marker -> agent bo sot replace loop; re-run Step 5 |
| F4 | **i18n.json khong ton tai** hoac `default_languages` sai key | `cat ${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` | tao/sua i18n.json truoc dispatch |
| F5 | **RST chua tung verify tren module that** - `doc/` thu muc chua co hoac RST syntax sai | `python3 -m docutils ...` FAIL | agent tao `doc/` neu chua co; fix RST syntax va re-run Step 5 |
| F6 | **Off-theme render** - browser_evaluate tra token EMPTY, agent bo qua screen | Kiem tra agent log `WARN: off-theme render detected` | dam bao Odoo load xong truoc capture (browser_wait_for `networkidle`); kiem tra Odoo theme da cai |
| F7 | **OSM unreachable** - Step 2 skip, screen list tu disk grep sai | Agent output co prefix `WARNING: OSM unreachable` | kiem tra OSM MCP server; neu OK thi re-run; neu khong -> chap nhan disk-grep nhung verify screen list tay |
| F8 | **`addons_path` khong resolve** - agent tra `NEEDS_CONTEXT` | Agent output `status: NEEDS_CONTEXT` | them `addons_path: $HOME/git/tvtmaaddons17` vao `.odoo-ai/context.md` |

---

## 6. Khi FAIL - vong fix tiep

1. Ghi lai observation cu the:
   - Checklist item nao FAIL (A1, B3, F2...).
   - Output agent log lien quan (Step nao dung/sai).
   - Artifact thuc te vs ky vong.

2. Doi chieu voi agent/skill:
   - **Step 0-1 fail** -> `odoo-doc-illustrator.md` Section "Step 0" / "Step 1".
   - **Step 2 fail (OSM)** -> kiem tra OSM server + `odoo-doc-illustrator.md` Section "Step 2".
   - **Step 3 fail (auth)** -> `docs/odoo-ui-knowledge.md` auth section.
   - **Step 4 fail (capture/cp)** -> `odoo-doc-illustrator.md` "Critical path constraint" + Branch A/B logic.
   - **Step 5 fail (artifact)** -> `odoo-doc-illustrator.md` Section "Step 5" + naming convention.
   - **Step 6 fail (manifest)** -> `odoo-doc-illustrator.md` Section "Step 6".

3. Mo issue hoac sua trong scope:
   - Bug trong agent workflow -> `agents/odoo-doc-illustrator.md`.
   - Bug trong skill brief/routing -> `skills/odoo-doc-illustration/SKILL.md`.
   - Chay lai dispatch sau sua, lap lai tu buoc kiem tra Section 4.
