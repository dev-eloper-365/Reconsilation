# Company profile: Delta Global Resources Pvt Ltd

Source: Tally "Ledger Account" export, .xlsx, one sheet per counterparty
(sheet name = counterparty ledger name, e.g. "Jindal Worldwide Ltd.").

## Layout

- Header rows 1-N: company letterhead + counterparty address, no fixed row count.
  Locate the real header by scanning for the row where col A == "Date".
- Header row: `Date | Particulars (merged B:C) | Vch Type | Vch No. | Debit | Credit`
- Data row columns (NOT matching the merged header — B/C split on data rows):
  - A: transaction date (datetime)
  - B: `Dr` / `Cr` flag
  - C: particulars / ledger name (e.g. "Imported Steam Coal@5%", "Opening Balance")
  - D: Vch Type (e.g. "Imported Steam Coal @ 5% GST", "Receipt", "Journal")
  - E: Vch No. — **this is the bill/invoice number** for purchase entries
    (format `GJ/FY/NNNN`, e.g. `GJ/25-26/0062`). Blank for bank receipts/journals.
  - F: Debit amount (used for `Cr` rows in this export — see quirk below)
  - G: Credit amount (used for `Dr` rows in this export — see quirk below)
- Row after last transaction: opening/closing totals row (col A holds a plain
  number, not a datetime) — skip, then a "Closing Balance" row, then a final
  totals row. Stop parsing once col A is not a datetime.

## Quirks

- **Debit/Credit columns are swapped relative to the Dr/Cr flag.** A row
  flagged `Cr` puts its amount in column F (headed "Debit"), and a row
  flagged `Dr` puts its amount in column G (headed "Credit"). Always read
  the amount as `F if F is not None else G` — don't trust the header label.
- Opening balance row has no Vch No / Vch Type, only a `Cr`/`Dr` flag,
  "Opening Balance" particulars, and an amount.
- Bill number series (`GJ/25-26/NNNN`) is Jindal's own sales-invoice
  sequence, shared across Jindal's customers — not exclusive to Delta.
  Numbers will have gaps; that's normal, not a data error.
