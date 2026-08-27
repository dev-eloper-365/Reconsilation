# Company profile: Delta columnar register export

Source: Tally columnar register / "Ledger Account" export **with quantity and
ledger breakup columns**, `.xlsx`, one sheet per counterparty (sheet name =
counterparty, e.g. "Jindal Worldwide Ltd."). Same letterhead block as the plain
Delta ledger, and the same voucher set — the difference is the columns.

This is the file `docs/tds_flow.md` asks for: it states the taxable value
directly, so Step 3 never has to derive a base amount.

## Layout

- Letterhead rows 1-N, no fixed count. Locate the header by scanning column A
  for the value `Date`, exactly as with the plain ledger.
- **Only five columns are required**: `Date`, `Voucher Type`, `Voucher No.`,
  `Value`, `Gross Total`. `Particulars`, `Buyer/Supplier`, `GSTIN/UIN`,
  `Narration`, `Quantity` and `Rate` are read when present and left null when
  not — which columns a register carries depends on how it was exported, and
  registers arrive without the descriptive ones. Without `Quantity` the
  cess-per-tonne cross-check is skipped; everything else still computes.
- Header row columns, in the file seen so far:

  | Column | Meaning |
  |---|---|
  | `Date` | voucher date |
  | `Particulars` | counterparty ledger |
  | `Buyer/Supplier` | counterparty; blank on receipts and journals |
  | `Voucher Type` | e.g. `Imported Steam Coal @ 5% GST`, `Receipt`, `Journal`, `CREDIT NOTE ISSUE` |
  | `Voucher No.` | **the bill number** for invoices (`GJ/FY/NNNN`) |
  | `GSTIN/UIN` | counterparty GSTIN |
  | `Narration` | free text (vessel, LR number, "as per 26AS", ...) |
  | `Quantity` | **metric tonnes** — the field the plain ledger lacks |
  | `Alt. Units` | empty in every export seen |
  | `Rate` | per-MT rate |
  | `Value` | **taxable value — this is the base amount** |
  | `Gross Total` | invoice total; ties to the plain ledger's amount |
  | *(then one column per ledger the voucher touched)* | see below |

- The trailing `Grand Total` row has no date — stop at the first row whose date
  cell is not a date.

## Ledger columns are not fixed

Everything after `Gross Total` is one column per ledger account posted in the
period, so **the column count and names change between exports** and must be
resolved by header text, never by index. In the 1-Apr-2025 to 16-Jun-2026
export: `Imported Steam Coal@5%`, `CGST @ 2.5%`, `SGST @ 2.5%`,
`GST Compensation Cess @ 400 PMT`, `ROUNDING OFF`, `SHORTAGE NON GST`,
`IDFC FIRST BANK - 5879`, `Tds Receivable 194Q F.Y. 2025-26`,
`Imported Steam Coal@18%`, `CGST @ 9%`, `SGST @ 9%`,
`Hdfc Bank A/c 50200054779692`, `Quality Difference - Coal`,
`Rate Difference - Coal`.

`recon/parsers/register.py` matches the ones that matter by pattern:

- cess — `compensation cess`; **the per-tonne rate is read out of the header
  itself** (`@ 400 PMT`), not hardcoded, because it is a matter of law.
- TDS — `194Q` or `tds`. Note the header names a financial year
  (`Tds Receivable 194Q F.Y. 2025-26`), so a multi-year export may carry TDS
  columns for one year only.
- shortage, rounding — by name.
- GST — every column matching `CGST|SGST|IGST|UTGST` is **summed**, because a
  period spanning a rate change has one column per slab (2.5% and 9% both
  appear above). Matching only the first would silently halve the GST.

Anything unmatched is still returned per row in a `ledgers` dict, so a new
ledger account does not need a code change to be visible.

## Sign conventions

Credit note rows carry a **negative** `Value`, so note amounts are *added* to
the invoice base to net them off — subtracting them doubles the adjustment in
the wrong direction.

## Verified against the 1-Apr-2025 to 16-Jun-2026 export

- 901 data rows: 765 invoices, 114 receipts, 16 journals, 6 credit notes —
  the same voucher set as the plain ledger.
- `Value + GST + cess + rounding == Gross Total` on all 765 invoices.
- `cess == 400 × Quantity` on all 383 invoices in the 5% period.
- All 765 `Gross Total` values tie exactly to the plain Delta ledger amounts.
