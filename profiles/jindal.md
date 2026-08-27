# Company profile: Jindal Denims Inc. (Jindal Worldwide group)

Source: Tally "Ledger Statement" export, in **either** legacy `.xls` (BIFF, read
with `xlrd`) or `.xlsx` (read with `openpyxl`) — the same export template arrives
in both formats depending on who saved it, and `recon/parsers/jindal.py` sniffs
the magic bytes and picks the reader. One sheet per counterparty (sheet name =
counterparty name, e.g. "DELTA GLOBAL RESOURCES PVT. LT").

The only format-dependent detail is the date cell: `.xls` gives an xlrd serial
float needing `xldate_as_datetime`, `.xlsx` gives a datetime directly. The
parser normalises that before the shared row logic runs.

**Verify the letterhead (row 1, col A) matches the expected counterparty's
own name before trusting the sheet** — a file was received once with the
sheet correctly named "DELTA GLOBAL RESOURCES..." but the letterhead said
"AMITARA OVERSEAS PRIVATE LIMITED" (wrong/unrelated company, zero bill-no
overlap with Delta's own ledger). Confirmed-good files say
"JINDAL DENIMS INC." on row 1.

## Layout

- Row 1: reporting company letterhead.
- Row 2: period string, e.g. "Ledger Statement For The Period Of : 01-Apr-2025 To : 16-Jun-2026".
- Header row (row 4, 0-indexed row 3): `Voucher No. | VType | Date | Particular | Bill No. | Bill Amount | Dr. Amount | Cr. Amount | Closing | (Dr/Cr)`
- Row 5 (0-indexed 4): counterparty name repeated, not data.
- Data rows start row 6 (0-indexed 5), first row is `*** Opening Balance ***`.
- Columns (0-indexed):
  - 0: Voucher No. (internal, e.g. `CF/PU/2526/229`)
  - 1: VType (`PU` purchase, `BP` bank payment, `DN` debit note, `JV` journal)
  - 2: Date — datetime in `.xlsx`; **xlrd float serial** in `.xls`, converted with `xlrd.xldate_as_datetime(v, workbook.datemode)`
  - 3: Particular (free text, includes embedded "Ref.No.:" text)
  - 4: **Bill No.** — the invoice number to match against Delta's Vch No.
    (format `GJ/FY/NNNN`). Populated only on `PU` (purchase) rows — **and not
    always even then**: the FY 2023-24 statement leaves it empty on all 811 `PU`
    rows, which removes the only join key. See learnings.md.
  - 5: Bill Amount — observed always blank in this export; don't rely on it.
  - 6: Dr. Amount
  - 7: Cr. Amount
  - 8: Closing balance running total
  - 9: `CR` / `DR` flag for the closing balance
- Amount for a row = `col6 if col6 not in (None,'') else col7`.
- No fixed end-of-data marker seen yet — read to `sheet.nrows`, skip rows
  where col 2 isn't a valid date serial (defensive, not yet observed needed).
