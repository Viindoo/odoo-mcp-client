# RFP Response - Worked Examples

**Example 1:**
Prompt: "RFP has 15 requirements for a manufacturing client: MRP, batch production,
multi-currency invoicing, custom IoT integration for CNC machines, quality control checklists."
Output: MRP -> Yes (CE, `mrp`); batch production -> Yes (CE, `mrp` lot/serial tracking);
multi-currency invoicing -> Yes (CE, `account`, `res.currency`); IoT CNC integration -> No
(custom XL, `iot` EE exists but CNC adapter is bespoke); quality checklists -> Partial
(`quality` EE covers basic checks; advanced custom checklist builder not standard).
Overall fit ~70%. Recommended: bid with EE license requirement noted and CNC integration
scoped as custom work.

**Example 2:**
Prompt: "Rate these 8 HR requirements for a government tender: employee registry, leave
management, payroll, org-chart export to PDF, custom grade/rank field, biometric attendance,
approval workflow for overtime."
Output: Employee registry -> Yes (CE, `hr`); leave management -> Yes (CE, `hr_holidays`);
payroll -> Yes (EE, `hr_payroll`); org-chart PDF export -> Partial (`hr` has org chart view,
no native PDF export - via-Extension with `wkhtmltopdf` route, M); custom grade/rank ->
via-Extension (`hr.employee` `_inherit`, computed field, S); biometric attendance -> No
(custom XL, no standard biometric adapter); overtime approval -> via-Extension
(`mail.activity.mixin` approval pattern, M). Overall fit ~65%.
