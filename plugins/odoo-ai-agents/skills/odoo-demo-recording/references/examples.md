# Demo Recording Examples

## Example 1 - sales order demo MP4

Prompt: "Record a 30-second demo of creating and confirming a sales order in Odoo 17."

- Round 0: context → `odoo_version: <version>`, base URL, login; format MP4, ~30s.
- Round 1 (parallel): `check_module_exists(name='sale_management', odoo_version='<version>')` + `module_inspect(name='sale', method='views', odoo_version='<version>')` + `model_inspect(model='sale.order', method='summary', odoo_version='<version>')` + `find_examples(query='create confirm sale order flow', odoo_version='<version>')` → step list.
- Round 2: log in, navigate to Sales, set clean state.
- Round 3: record click path: New → pick customer → add line → Confirm.
- Round 4: save `.odoo-ai/visual/videos/sale-order-<timestamp>.mp4`, report path + duration.

## Example 2 - website portal GIF, recorder unavailable

Prompt: "Make a GIF of the customer portal invoice download."

- Round 1: `module_inspect` for portal views; `find_examples(query='portal invoice download flow', odoo_version='<version>')`.
- Round 3: recorder unavailable → capture `take_screenshot` frames at each step.
- Round 4: assemble frames into a GIF; prefix output with the recorder-unreachable warning.
