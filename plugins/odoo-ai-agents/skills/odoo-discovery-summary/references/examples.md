# Discovery Summary — Worked Examples

## Example 1 — Customer A (manufacturing SME, traceability need)

**User input (VI):**
> "Họp với Customer A hôm nay. Sản xuất linh kiện nhựa, khoảng 80 người, đang dùng
> Excel + phần mềm kế toán cũ. Họ nói 'chúng tôi không biết lô nào gây ra lỗi trả về
> vì không có trace'. Muốn quản lý lô hàng, truy xuất nguồn gốc, báo cáo sản xuất.
> Ngân sách chưa chốt, cần demo trước. Quyết định do giám đốc sản xuất + CFO."

**Expected profile (excerpt):**

```
# Discovery Profile — Customer A

## Snapshot
- Industry: Manufacturing — plastic components
- Headcount band: M (80 employees)
- Current system: Excel + legacy accounting software
- Decision process: Committee (Production Director + CFO)
- Timeline urgency: undefined (demo first)
- Budget signal: [not stated — approval pending demo]

## Pain points
1. Lot traceability gap — "chúng tôi không biết lô nào gây ra lỗi trả về vì không có trace"
2. No production reporting visibility

## Fit assessment
| Pain | Odoo path | Confidence |
|------|-----------|------------|
| Lot traceability | Standard (stock.lot + MRP) | High |
| Production reporting | Config (mrp module dashboards) | Med |

Overall fit: 5/5 — Both pains are covered by standard MRP/inventory modules; main risk
is data migration from legacy accounting.

## Open questions for next call
1. Does the accounting migration need to carry historical transactions (GL balance only vs. full journal)?
2. Are there regulatory traceability requirements (ISO, customer audit mandates)?
3. How many concurrent warehouse users at peak picking time?
```

## Example 2 — Customer B (multi-store retail, POS + inventory sync)

**User input (EN):**
> "Discovery call with Customer B. They run 5 retail stores + 1 online shop. ~200 staff
> total. Using a legacy POS that doesn't sync with their warehouse. Quote: 'We lose at
> least 3 hours a day reconciling stock between stores manually.' Want real-time stock
> visibility across locations and loyalty points that work both in-store and online.
> Budget approved up to USD 40k. Must go live Q1 next year. Owner decides alone."

**Expected profile (excerpt):**

```
# Discovery Profile — Customer B

## Snapshot
- Industry: Retail — multi-store + e-commerce
- Headcount band: M (200 employees)
- Current system: Legacy POS (vendor unspecified), separate warehouse system
- Decision process: Single owner
- Timeline urgency: Q1 <next year>
- Budget signal: Approved up to USD 40k

## Pain points
1. Real-time cross-location stock sync — "We lose at least 3 hours a day reconciling
   stock between stores manually."
2. Unified loyalty programme (in-store + online)

## Fit assessment
| Pain | Odoo path | Confidence |
|------|-----------|------------|
| Cross-location stock sync | Standard (multi-warehouse + POS module) | High |
| Unified loyalty (POS + eCommerce) | Config (loyalty.card + eCommerce bridge) | Med |

Overall fit: 4/5 — Core pain is standard; loyalty cross-channel sync may need config
tuning. USD 40k budget is tight if data migration from 5 legacy POS instances is needed.

## Open questions for next call
1. What is the current loyalty card data format — can it be exported for migration?
2. Does the online shop run on a third-party platform (Shopify, WooCommerce) or is a new
   Odoo eCommerce site also in scope?
3. Are the 5 stores on separate tax jurisdictions requiring different fiscal positions?
```
