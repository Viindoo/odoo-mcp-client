<!-- SSOT snippet. Two recon modes for ingesting a source document: faithful SSOT-extraction
     vs interpretive summary. Consumers: odoo-intake (Phase R), odoo-brl (Phase 0 intake),
     odoo-discovery-summary (Round 1). Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/ssot-extraction-contract.md. -->

# SSOT-Extraction Contract (faithful vs interpretive recon)

A recon pass that reads a source document runs in ONE of two modes. Pick the mode BEFORE reading.

**Selector:** if the user says the input IS a contract / RFP / spec / regulation / requirement
list - or the document otherwise defines the requirement single-source-of-truth - use
**SSOT-extraction mode**. Otherwise (raw meeting notes, brainstorm, free-form transcript) use
**interpretive-summary mode**.

## SSOT-extraction mode (the source IS the requirement SSOT)

- Extract VERBATIM or as structured fields - do not paraphrase the requirement away. Quote the
  original text for every requirement, constraint, number, and named product/service.
- Mark ANY reasoning you add - inference, recommendation, gap you noticed - as
  `[INTERPRETATION: ...]`, kept visibly separate from the extracted text.
- NEVER invent specifics, recommendations, or numbers not in the source. A hosting choice, a
  version, a tier, a price, a deadline that the document does not state is NOT yours to supply.
- If exact text is needed and the file is binary (`.docx` / `.pdf`), extract with a real parser
  (e.g. `python-docx`, a PDF text extractor) - do not eyeball or summarize from a rendered view.

## Interpretive-summary mode (raw notes / brainstorm)

- A condensed summary is fine - the goal is a usable profile, not a transcript.
- Still quote pain points (and any hard numbers/deadlines) VERBATIM where the user transcribed
  the speaker's words; everything else may be summarized.
