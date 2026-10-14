# Packs: one core, several document types

The core pipeline (OCR, locating the region of interest, grounding, routing, register,
evaluation) is document-agnostic. Everything specific to a document type lives in a **pack**.
`src/revisa/packs/construction.py` is the built example; the two packs below are specified to
show the boundary holds, and are not implemented.

## What a pack provides

| Part | Construction pack | Purpose |
|---|---|---|
| Fields | `SCORED_FIELDS`, `REQUIRED_FIELDS`, `TitleBlock` | What to extract; what a record can't be filed without |
| Field guide | `FIELD_GUIDE` | One sentence per field for the language model |
| Locator keywords | `TITLE_BLOCK_KEYWORDS`, `ARCHIVE_STAMP` | Find the region that holds the fields; ignore known noise |
| Rules | `read_fields` | Free deterministic reader, also the cross-check |
| Coercion | `coerce`, `parse_dates` | Turn printed text into register values |
| Scoring | `normalise`, `field_matches` | When two values are the same value |
| Set checks | `register.check` | Problems only visible across documents |
| Eval set | `datasets/habs` | Labelled public-domain documents |

## Medical: referral letters

A GP referral to a specialist clinic, scanned or faxed. The clinic's intake team keys each one
into the patient management system and triages it.

- **Fields:** patient name, date of birth, NHI number (NZ national health identifier),
  referring clinician and practice, receiving service, reason for referral, urgency as stated,
  date of letter. Required: patient name, date of birth, NHI, receiving service.
- **Locator keywords:** `RE:`, `DOB`, `NHI`, `Dear Dr`, `Referral`, practice letterhead words.
  The region is the letter header and first paragraph rather than a block.
- **Rules:** NHI has a fixed format with a check character, so a rule can validate it fully;
  dates of birth must be in the past and imply a plausible age.
- **Routing:** any NHI that fails its check character, any mismatch between name and NHI in the
  patient index, and every urgent referral goes to a person regardless of confidence.
- **Set checks:** duplicate referrals for the same patient and service within 30 days.
- **Data and privacy:** real referrals can't be used. The eval set would be synthetic letters
  generated from templates with fake NHIs (the Ministry of Health publishes test NHIs), plus a
  small set of real formats with all identifiers replaced. Deployment would need the Azure
  region and data residency agreed with the provider.

## Finance: supplier invoices

Accounts payable receives PDFs and photos of invoices and matches them to purchase orders.

- **Fields:** supplier name, GST number, invoice number, invoice date, due date, purchase order
  number, subtotal, GST, total, currency. Required: supplier, invoice number, date, total.
- **Locator:** none needed for most invoices; Document Intelligence `prebuilt-invoice` already
  returns these fields, so the pack's reader 2 could be that model instead of an LLM, with the
  rules as the cross-check.
- **Rules:** subtotal plus GST equals total; GST is 15% of the subtotal in New Zealand; the GST
  number has a check digit; due date is after invoice date.
- **Routing:** totals that don't add up, an unknown supplier, a PO number not found in the
  finance system, or a bank account different from the supplier's record (a common fraud
  pattern) always go to a person.
- **Set checks:** the same supplier and invoice number twice (duplicate payment risk).
- **Data:** public sample invoices and synthetic ones generated with known values.
