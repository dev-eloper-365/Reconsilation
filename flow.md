# Reconciliation workflow

How this project turns two Tally ledger exports into the reconciliation viewer.
Written to be self-contained: someone (or some agent) handed only this file, the
two exports, and an empty directory should be able to rebuild the whole thing
and get the same views out.

Companion documents: `profiles/delta.md` and `profiles/jindal.md` hold the
per-company parsing rules, `learnings.md` holds the traps discovered the hard
way, and `docs/tds_flow.md` holds the not-yet-built Step 3.

---

## 1. What is being reconciled

Two parties keep their own books of the same trade:

- **Delta Global Resources Pvt Ltd** — the seller, exports imported steam coal
  invoices to Jindal.
- **Jindal Denims Inc.** (Jindal Worldwide group) — the buyer.

Each exports its ledger for the counterparty from Tally. Every real transaction
appears in both files, recorded in each party's own vocabulary, and the job is
to line them up and explain every difference.

The uploaded files are the only input. Nothing in the pipeline depends on a
particular period, financial year, or filename — running it against a different
period's exports is just running it again with different files.

---

## 1a. Inputs

Three files, of which two are required. Each is a Tally export; **what matters
is the export template, not the filename** — the pipeline never reads a filename
or a date from one.

| # | Input | Format | Tally export | Required | Feeds |
|---|---|---|---|---|---|
| 1 | Delta ledger | `.xlsx` | Ledger Account, counterparty ledger | **yes** | Steps 1, 2, and Step 3's tie-out |
| 2 | Jindal ledger | `.xls` or `.xlsx` | Ledger Statement, counterparty ledger | **yes** | Steps 1, 2 |
| 3 | Delta columnar register | `.xlsx` | Ledger Account **with quantity and ledger breakup columns** | optional | Step 3 only |

Without #3 the tool runs Steps 1 and 2 and leaves Step 3 disabled. There is no
partial Step 3 — base value and TDS need the register.

### What each input must contain

Full column layouts are in `profiles/delta.md`, `profiles/jindal.md` and
`profiles/register.md`. The minimum each file has to carry:

**1. Delta ledger** — a header row whose column A is `Date` and column F is
`Debit`; then per row: date, `Dr`/`Cr` flag, particulars, voucher type, voucher
number (the bill number on invoices), and debit/credit amounts. The `Debit`
header check is what stops the register being parsed as a ledger by mistake.

**2. Jindal ledger** — a header row starting `Voucher No.`; then per row:
voucher number, voucher type (`PU`/`BP`/`JV`/`DN`/`CN`), date, particulars, bill
number (populated on `PU` rows — this is the join key), and Dr/Cr amounts.
Either file format works; the parser sniffs the magic bytes and reads `.xls`
with xlrd or `.xlsx` with openpyxl.

**3. Register** — a header row whose column A is `Date`, plus four more columns
by name: `Voucher Type`, `Voucher No.`, `Value`, `Gross Total`. Those five are
the whole requirement. `Particulars`, `Buyer/Supplier`, `GSTIN/UIN`,
`Narration`, `Quantity` and `Rate` are used when present and skipped when
absent — without `Quantity` the cess-per-tonne check simply does not run. `Value` is the taxable amount and is the reason Step 3 derives
nothing. Everything after `Gross Total` is one column per ledger the voucher
touched; the parser matches GST, compensation cess, TDS, shortage and rounding
by pattern and keeps the rest verbatim, so a new ledger account needs no code
change. Two of those columns carry rates in their header text
(`GST Compensation Cess @ 400 PMT`, `Tds Receivable 194Q F.Y. 2025-26`) and are
read from the header rather than hardcoded.

### Identity requirements — the slots are only labels

`recon/identify.py` works out what each uploaded file is from its own content,
so a file dropped in the wrong slot is still read correctly:

| Signal | Delta ledger | Register | Jindal ledger |
|---|---|---|---|
| Header row starts with | `Date` | `Date` | `Voucher No.` |
| Header row also contains | `Debit`, `Credit` | `Value`, `Gross Total` | — |
| Letterhead (cell A1) | Delta … | Delta … | JINDAL DENIMS INC. |

**More than one file of the same kind is merged, not rejected.** Several exports
covering different (or overlapping) periods can be uploaded together; their rows
are concatenated and then put through `years.dedupe`, so an overlap is not
double-counted. A warning names the files that were merged, because a merge is
something the reader should know happened.

**A Jindal workbook can hold one sheet per counterparty.** A group's several
companies each get their own ledger with Jindal, and they are different legal
entities that must not be pooled. `jindal.pick_sheet` chooses the sheet whose
name shares the most significant words with the **Delta file's letterhead** —
legal-form suffixes (`PVT`, `LTD`, `&`, …) being ignored as noise — and falls
back to the first ledger sheet when nothing matches, which is the single-sheet
case. A warning names the sheet read and every sheet ignored, with its row count.
Reading the wrong sheet produces a complete, plausible, entirely wrong
reconciliation, so this warning is worth reading every time.

What is still reported: a file matching no known template, a missing required
kind — named as *"missing the Jindal ledger; what was uploaded was …"* — and a
letterhead naming the wrong company.

## 1b. Outputs

| Artefact | Produced by | Contents |
|---|---|---|
| `output/step1_data.json` | `step1.py` | `summary`, `totals`, `matched`, `only_delta`, `only_jindal` |
| `output/step2_data.json` | `step2.py` | `summary` plus `receipts`, `journals`, `interest_adjustments`, `tds`, `notes`, each `{delta, jindal, totals}` |
| `output/step3_data.json` | `step3.py` | `summary`, `periods` (per financial year, with `by_slab`), `invoices`, `notes`, `tds_entries`, `reversals`, `warnings`, `meta` |
| `output/reconciliation.html` | `render_page.py` | the standalone viewer, with every year's payload inlined — one file, no assets, shareable as-is |

The three JSON files above are **one period's** artefacts, written by the CLI
scripts. The viewer is built from a larger structure that `years.reconcile`
assembles: one `{step1, step2, step3, headline}` per financial year, plus an
"All years" pass, plus the closing position. That structure is never written to
disk — `render_page.build(payload, period)` takes it directly.

The JSON files are the contract between stages: they make a refactor provable
(run, diff, require no change) and they are what the server path builds in
memory instead of on disk. The web path writes only the HTML.

The answers the whole thing exists to produce:

- which bills tie, which differ, and which exist on one side only (Step 1);
- what the non-invoice traffic is on each side, category by category (Step 2);
- the taxable value per financial year, the 194Q TDS it implies, and the gap
  against the TDS actually booked (Step 3);
- what each ledger says the other owes at the end, and a bridge accounting for
  every rupee between the two figures (Closing position).

## 2. Pipeline shape

```
Delta ledger .xlsx  ─▶ parsers/delta.py    ─┐
Jindal ledger .xls  ─▶ parsers/jindal.py   ─┤
Register .xlsx      ─▶ parsers/register.py ─┤   (identify.py routes each file by
  (optional)                                │    its content, not by upload slot)
                                            ▼
                                   years.reconcile()
                                            │
             split rows by financial year, then per year:
                    step1.compute() ─┐
                    step2.compute() ─┤
                    step3.compute() ─┘      + an "All years" pass over everything
                                            │
                       years.mark_cross_year(), closing.compute()
                                            ▼
                              render_page.build(payload, period)
                                            ▼
                             output/reconciliation.html
```

`years.reconcile` is the orchestrator; **the per-step `compute()` functions know
nothing about years**. They are handed one slice of rows and reconcile it. That
separation is what lets the same code produce a single-period report and a
seven-year timeline with no branching inside the steps.

Two ways to run it:

**Web (any period, no terminal work after start):**

```
.venv/bin/python recon/serve.py        # then open http://localhost:8000
```

Upload the two ledgers — plus the register, if Step 3 is wanted — and get the viewer. `recon/serve.py` calls the exact same
`compute()` and `build()` functions the CLI does — there is no second
implementation of the reconciliation logic anywhere, and no JavaScript port of
it. Result is served at `/result` and also written to
`output/reconciliation.html`.

**CLI (regenerates the JSON artefacts, uses the hardcoded paths in the scripts):**

```
.venv/bin/python recon/step1.py
.venv/bin/python recon/step2.py
.venv/bin/python recon/step3.py     # needs the register export
.venv/bin/python recon/render_page.py
```

Dependencies: `openpyxl` (for `.xlsx`) and `xlrd` (for legacy `.xls` — openpyxl
cannot read BIFF). Both Jindal formats are supported. The server is standard
library only.

---

## 3. Parsing contract

Both parsers return plain dicts. Every downstream stage depends only on this
shape, which is what makes adding a third counterparty a matter of writing one
more parser rather than touching the pipeline.

**Delta row** (`recon/parsers/delta.py`, `parse(path) -> list[dict]`):

```python
{"date": "YYYY-MM-DD", "drcr": "Dr"|"Cr", "particulars": str,
 "vch_type": str, "bill_no": str|None, "amount": float|None}
```

**Jindal row** (`recon/parsers/jindal.py`, `parse(path) -> (letterhead, list[dict])`):

```python
{"date": "YYYY-MM-DD", "voucher_no": str|None, "vch_type": str,
 "particulars": str|None, "bill_no": str|None, "amount": float|None,
 "side": "DR"|"CR"}
```

Both also expose the file's letterhead — `delta.letterhead(path)`, and
`jindal.parse` returns it as its first value.

Three rules every parser must follow, each one a bug that actually happened:

1. **Find the header row by scanning**, never by a fixed offset. The letterhead
   block above it has no fixed height.
2. **Resolve the amount as "whichever of the two amount columns is non-empty"**,
   never by trusting the Debit/Credit header. Delta's export puts `Cr`-flagged
   rows under the "Debit" heading and vice versa.
3. **Stop at the first row whose date cell is not a date.** That is how the
   closing-balance and totals rows at the bottom get excluded.

---

## 4. Identity checks — run before believing any number

From `learnings.md`, and enforced in `recon/serve.py`:

- The Delta file's letterhead must name Delta; the Jindal file's must name
  Jindal. A file once arrived with the correct sheet name and an unrelated
  company inside.
- File format is checked by magic bytes (`PK` = xlsx, `D0CF11E0` = legacy xls)
  so a swapped pair is reported as a swapped pair, not as a parser stack trace.
- **A zero-match result is a bug report, not a finding**, and its two causes get
  different messages: *no bill numbers at all in one file* (the export is
  missing the column — re-export it; Jindal's FY 2023-24 statement is like
  this) versus *bill numbers on both sides that do not overlap* (wrong
  counterparty, period, or file).
- Optional manual check: the closing balance of one period's export should equal
  the opening balance of the next period's export for the same account.

---

## 4a. Financial-year slicing — `years.py`

Everything above runs **per financial year**, and `recon/years.py` is what makes
that happen. Nothing in `step1`/`step2`/`step3` is year-aware.

`reconcile(delta_rows, jindal_rows, register_rows=None, register_meta=None)`
returns:

```python
{"order": [fy, ..., "All years"],
 "years": {fy: {"step1": …, "step2": …, "step3": …, "headline": …}},
 "all_label": "All years",
 "closing": {…}}
```

The rules it applies:

- **Financial year is April to March** (`fy_of`, shared with `step3`), labelled
  `2025-26`. Slicing is by the row's **own date**, on each side independently —
  which is exactly why the cross-year remark in Step 1 exists.
- **Every year present in either ledger gets an entry**, even when one side has
  nothing for it. A year the counterparty never booked at all is itself a
  finding, and dropping it would hide it.
- **An "All years" pass runs over the unsliced rows.** It is not the sum of the
  years: a bill raised in one year and booked in another matches here and in
  neither year's slice. When a year shows an unmatched bill, check "All years"
  before calling it missing.
- **`dedupe` runs when exports are merged.** Two uploads covering overlapping
  periods would otherwise double-count. Identity is the whole visible row — date,
  voucher no., bill no., voucher type, amount, particulars — so a genuinely
  repeated transaction that differs in none of those is kept once. This is
  deliberately strict: it is safer to keep a duplicate that is really two
  transactions than to drop one that is.
- **`headline`** produces the few numbers the timeline shows per year before it
  is expanded. It flags a year as `sparse` when neither side has a single bill in
  it — the tail of an export whose period runs a few days past a year end. That
  is real data, but it is not a reconciliation, and the timeline says so rather
  than showing an alarming row of zeroes.

---

## 4b. Closing position — `closing.py`

This is the answer to "what does each book think the other owes, and why do the
two figures differ". `compute(delta_rows, jindal_rows)` returns `periods` (one
per financial year, cumulative) and `overall`.

Both ledgers are cumulative, so a closing balance is the running total of all
movement. Two rules decide whether that total is right:

**Opening-balance rows are not movement.** A multi-year export restates the prior
year's closing at the top of each year block. Adding those double-counts — ₹3.88
crore of it in the 2019-2026 Delta export. Rows whose particulars contain
"opening balance" are dropped before anything is summed.

**Each side signs its own way.** Delta's ledger is the customer account; Jindal's
is the supplier account. They are mirror images:

| | Increases what Jindal owes Delta | Decreases it |
|---|---|---|
| Delta's book (customer account) | `Cr` | `Dr` |
| Jindal's book (supplier account) | `CR` | `DR` |

Signed that way, **both closing balances are positive when Jindal owes Delta**,
and the two are directly comparable. Getting this backwards on one side produces
a difference of twice the balance, which looks like a catastrophe and is an
arithmetic error.

### The bridge

The difference between the two closings is split into four buckets that **sum to
it exactly** — that exactness is the point, and is what makes the bridge a proof
rather than a summary:

| Bucket | Delta side | Jindal side |
|---|---|---|
| `invoices` | bill no. in the invoice series | `vch_type == "PU"` |
| `notes` | `vch_type` contains "NOTE" | `DN` / `CN` |
| `payments` | `Receipt`, `Journal`, `Payment`, `Contra` | `BP`, `BR`, `JV` |
| `other` | everything else | everything else |

Note that this bucketing is **deliberately coarser than Step 2's**, and is not
derived from it. Settlement traffic is one bucket here because the two books
split it differently — Jindal posts TDS and payments as `JV` — and only
reconciles when compared as a group. Step 2 splits those apart to make them
readable; the bridge keeps them together to make them add up. Two different
questions, two different groupings, on purpose.

`invoice_detail` then splits the invoice gap into its causes by re-running
`step1.compute` over the same rows: bills only Delta has, bills only Jindal has,
amount mismatches on matched bills, and the unrecognised-reference totals from
either side. Those five figures sum to the invoice bucket's difference.

---

## 5. Step 1 — bill number match

`recon/step1.py`, `compute(delta_rows, jindal_rows, prefix="GJ/")`.

Only rows carrying an invoice number participate — those whose `bill_no` starts
with the seller's invoice prefix (`GJ/`). Bank receipts, journals, and notes have
no bill number and belong to Step 2.

Bill numbers are **normalised before they are compared**
(`step1.normalise_bill`), in this order:

1. all whitespace stripped, quoting junk (backtick, single and double quote)
   removed, upper-cased;
2. every run of separators (`-`, `/`, `\`) collapsed to a single `/`;
3. a leading `GI/` rewritten to `GJ/` — the party types letter I for J;
4. a two-plus-two financial year after the prefix joined up, so `GJ/19/20/2811`
   and `GJ/1920/2811` become the same key;
5. trailing punctuation trimmed.

The two books type the same reference differently — `GJ/21-22/ 0655`,
`GJ/21-22/0629.`, `GJ /21-22/0604`, ``GJ/23-24/0534` ``, `GJ/23-24-2121`,
`GI/1920/2811` — and raw-string matching turns each of those into a phantom
"missing bill" exception on *both* sides at once.

Rules 3 and 4 are narrow on purpose. Rule 3 only fires on the prefix, so a
genuine `GI` series elsewhere in the number survives. Rule 4 requires exactly
two digits, a separator, then two digits, which is what keeps the `2526` in
`GJ/18/2526/1426` from being read as a financial year and joined to the `18`
before it.

The normalised key is a matching key, not a document number: `GJ/23-24/2121`
keys as `GJ/23/24/2121`, which is not a number anyone would recognise on an
invoice. So the viewer shows the form the books actually **wrote**
(`step1._display`) — the most common one, and Delta's when the two disagree,
since Delta raises the invoice. The other side's differing form is carried
alongside as `*_bill_written` and shown as "written by … as …".

Rows are **grouped and summed by bill number before comparing**, not matched one
row to one row: the same bill can legitimately appear on several rows on one side
(a note referencing an earlier bill, a split entry), and 1:1 matching would
miscount those.

Output buckets:

| Bucket | Meaning |
|---|---|
| `matched` | bill number present on both sides, with each side's total and the difference |
| `only_delta` | invoiced by Delta, absent from Jindal's book |
| `only_jindal` | recorded by Jindal, absent from Delta's book |
| `unrecognised` | a reference that is clearly a document number but is not in the invoice series at all, on either side — parked here rather than dropped, because a row in neither the matched nor the unmatched bucket vanishes from the reconciliation entirely |

Each unmatched row carries a **`remark`** naming the expected cause when there is
one — see *Cross-year booking* below. When reading the unmatched buckets,
discount two expected causes first: invoices reversed by a credit note (Step 3
names them, and Step 1 tags them "Reversed by"), and invoices the counterparty
booked in a different year, which the remark names outright.

### Cross-year booking

The per-year slices are cut by **date**, so an invoice Delta raised in March
2020 and Jindal booked in May 2020 lands in a different financial year on each
side. It is then unmatched in *both* years' slices while nothing is actually
missing — it matches in the "All years" pass. Reading that as a missing document
is the mistake this remark exists to prevent.

`years.mark_cross_year` runs after every year is computed. It indexes every bill
each side booked, in **every** year, then annotates each unmatched row:

| Remark | Meaning |
|---|---|
| `Booked by Jindal in 2024-25 (5 years later)` | The other side did book this bill, in another year. Not missing. |
| `2019-20 invoice booked in 2024-25 (5 years later)` | Nobody else booked it, but the invoice number's own series names a different year — the fallback when the counterparty has no record at all. |
| *(empty)* | Genuinely absent from the other book in every year. This is the real exception. |

Two things matter here. The comparison is **every year against every year**, not
just the neighbouring one — a voucher can sit unpaid for years, and the gap in
the remark says how far. And the lookup keys on the *normalised* bill number,
not the written form, because the two books may type it differently as well as
book it in different years.

The invoice number's own financial year (`years._bill_series_fy`) is read from
any part of it that is a pair of **consecutive** years, so both `GJ/19-20/2863`
and `GJ/18/2526/1755` are understood, while the `1755` in the second is not
mistaken for 17-55.

Note on gaps: the `GJ/FY/NNNN` series is the seller's own sequence across *all*
its customers. Missing numbers on this counterparty's ledger are other
customers' invoices, not missing bills.

### Views

- **Matched** — one row per bill: status pill (tie / mismatch), both amounts, the
  difference, and each side's own date, voucher, particulars and row count so a
  mismatch can be investigated without opening the source files. Mismatching rows
  are tinted. Two controls sit above the table: **Show** (all bills / amount
  mismatches only) and **Sort** (by bill no. / largest difference first, ordered
  by size in either direction, since an over-booking matters as much as an
  under-booking). With a filter on, the right of the control row reads how many
  bills are showing and their net difference. Both choices persist across years.
- **Unmatched** — two tables side by side, only-in-Delta against only-in-Jindal,
  so a bill recorded under a slightly different number on one side is spotted by
  eye. Both carry a **Remark** column naming the year the other side booked the
  bill in, when it booked it at all.
- **Summary** — collapsible counts: bills per side, matched, tie-outs,
  mismatches, unmatched per side.
- **Totals bar** — Delta total, Jindal total, difference; the difference turns
  green at zero.

---

## 6. Step 2 — everything without a shared reference

`recon/step2.py`, `compute(delta_rows, jindal_rows)`.

Non-invoice rows carry no reference number common to both ledgers, and the row
granularity differs (one Delta receipt often covers several Jindal bank-payment
lines). So these are **listed side by side for manual cross-check, never
auto-matched** — a fake match here would be worse than no match.

Classification, all of it derived from voucher type plus a keyword in the
particulars:

| Category | Delta side | Jindal side |
|---|---|---|
| Receipts | `vch_type == "Receipt"`, plus anything tagged an advance | `vch_type == "BP"` (bank payment), plus `JV` carrying a `Ref.No.: TP/…` transfer reference, plus anything tagged an advance |
| Returned payments | `vch_type == "Payment"` | `vch_type == "BR"` (bank receipt) |
| Journals | `vch_type == "Journal"` | `vch_type == "JV"` |
| TDS 194Q | particulars contain "TDS" | particulars contain "TDS", **or** carry a `CF-####-NN` shipment reference |
| Interest adjustments | particulars match `Ref.No.: BD…` | same |
| Credit / debit notes | `vch_type` contains "CREDIT NOTE" / "DEBIT NOTE", plus journals tagged a claim | `vch_type` is `CN` / `DN` |
| Claims (shortage, rate, quality, weight) | tagged in place wherever the row lies — see below | same |
| Advances | tagged, and listed with the receipts | same |

TDS, interest adjustments, transfers and advances are journals too; they are
pulled out *before* the general journals tab is built, so the journals tab holds
only what is nothing else. The `plain()` filter inside `step2.compute` does that, and it keys off the
**tag** a row was given, not off its narration — a row identified only by the
amount on the other book's row has no keyword to match.

### A journal is not always an adjustment

Two kinds of Jindal `JV` are money moving, not a book adjustment, and leaving
them in the journals tab makes the receipts comparison unreadable:

| Signal | What it is | Where it goes |
|---|---|---|
| `Ref.No.: TP/…` | Jindal settling invoices by transfer instead of through its bank ledger — 103 rows, ₹23.5 crore, all `DR`, the same direction as a `BP` | Receipts |
| matched to a row narrated "advance" | the other half of an advance payment | Receipts |

Both are recognised the same way the 194Q rule works: `TP/` is a **structured
reference**, so it is classified on the reference and not on the narration
(every one of those rows reads only `JV LEDGER`).

### The TDS 194Q tab — the two books at different granularity

This is the only place the two ledgers' own 194Q figures sit side by side. Step 3
computes what 194Q *should* be from the register; this tab shows what each book
actually **recorded**, which is a different question.

The granularity is not comparable row for row:

| | How it is booked | FY 2025-26 |
|---|---|---|
| Delta | 194Q receivable, a few periodic journals (`194Q TDS RECEIVABLE 2023-24`, `Tds Receivable 194Q F.Y. 2024-25`) | 11 rows |
| Jindal | one JV per shipment, against that shipment's `CF-####-NN` reference | 582 rows |

So only the **totals** mean anything here, and the tab says so above the tables.

**Jindal's rows are found by the shipment reference, not by the narration.** Many
of them do not mention TDS at all — they read only `JV LEDGER`. Classifying on
the word "TDS" alone silently drops them. A Jindal JV counts as 194Q when the
particulars mention TDS **or** match `ref.no.: CF-####-NN`; rows caught by the
reference alone carry a `remark` saying so, so the heuristic can be checked by
eye rather than trusted. The other two reference families are excluded by the
same rule and routed elsewhere: `BD/JDI/…` is an interest adjustment, `TP/JDI/…`
is a transfer and belongs with the receipts.

The general journals tab is what is left once TDS, interest, transfers, advances
and claims are removed.

Receipts and notes are sorted by date; journals and interest by absolute amount
descending, largest first, because that is the order someone investigating a
difference wants them in.

### Claims and advances — one event, two books, two names

Some events are booked by both parties under names that share nothing but the
amount. The two the ledgers actually contain:

| Event | How Jindal writes it | How Delta writes it |
|---|---|---|
| Shortage, rate difference, quality claim, weight difference | a `DN` narrated `SHORTAGE A/C`, `RATE DIFFERENCE`, `QUALITY CLAIMS`, `WEIGHT DIFFERENT`, each against a `CF-####-NN` shipment | a credit note or a journal — narrated `RATE DIFFERENCE - SALES` / `Quality Difference - Coal` from FY 2022-23, but before that only `Imported Steam Coal@5%` |
| Advance payment | a `JV` narrated only `JV LEDGER` | a journal narrated `DGPL - Advances` |

**Only one book names the event, and which book that is changes.** For claims up
to FY 2021-22 Jindal names it and Delta does not; from FY 2022-23 it reverses.
For advances only Delta ever names it. So the search has to run **in both
directions**: a row that names the event on *either* side is a starting point,
and the other book's whole note-and-journal list is searched for its answer.

`step2.link_by_amount(candidates, kind_of, tag, noun)` does this for both, and
the only thing that separates the two uses is which narrations count as a name:

```python
link_by_amount(pool, adjustment_kind, "adj_kind", "note")     # claims
link_by_amount(pool, advance_kind, "advance_kind", "entry")   # advances
```

The rules it applies:

- **Amount is the only key.** The dates are months apart — Jindal books per
  shipment on the day, Delta at year end — and the narrations do not correspond.
- **Two passes.** Rows that *both* books named pair off first, so a generically
  narrated row cannot take an amount away from the row that actually names the
  event. Ties inside a pass go to the nearest date.
- **One row is used once**, on each side.
- **A row already carrying a remark is left alone**, which is what stops the
  claims pass and the advances pass from both claiming the same row.
- **TDS and interest journals are kept out of the candidate pool** — 1,312 Jindal
  TDS JVs in the pool is 1,312 chances for a coincidental amount to take a real
  counterpart.

What lands where afterwards differs by event, and it is the **naming** that
decides, not the voucher type:

| Event | Row that names it | Row found only by amount |
|---|---|---|
| Claim | stays where its voucher type puts it — a credit note stays a note, a journal is listed with the notes | same, tagged and remarked |
| Advance | moved to the receipts: it is money paid | moved to the receipts too, so both halves are counted on the same side |

### Remarks written by the linker

Every row it touches carries a remark naming the row in the other book that
answers it, or saying there is none:

| Remark | Meaning |
|---|---|
| `Rate difference — Jindal booked DN on 2022-09-30 against CF-2223-1467` | Paired. The `CF-…` reference is the shipment the claim was raised against, so the counterpart can be found in the source file. |
| `Rate difference — Jindal booked it as weight difference, DN on 2022-08-17 against CF-2223-1012` | Paired, but the two books call the claim different things. Both names are kept rather than one being picked. |
| `Shortage — Jindal booked no note for this amount` | Named by one book, with nothing of that amount in the other. A genuine one-sided claim. |
| `Advance payment — Delta booked journal 513 on 2022-01-31` | The row that never said "advance"; this is the only thing marking it as one. |

The `Claim` column beside the remark holds the tag itself (`Shortage`,
`Rate difference`, `Quality difference`, `Weight difference`) so the tables can
be filtered by it.

**Why a remark and not a merge.** A pairing made on amount alone is evidence, not
proof — the same reasoning that keeps Step 1 from matching invoices on amount.
Tagging and remarking leaves both rows visible with the basis of the link
written on them; netting them into one figure would hide it.

### Receipts are net of returned payments

A payment can fail — a cheque bounces, a transfer is rejected — and the bank
sends the money back. The return is booked as a **`Payment`** on the Delta side
(money leaving Delta again) and as a **`BR`**, bank receipt, on the Jindal side.
Neither voucher type is a receipt, so counting only the inward leg overstates
what was actually collected on both sides.

`step2.compute` therefore reports receipts **net of returns**:

```
receipts total (net) = receipts − returns
```

Both legs stay visible. The returns are listed in their own pair of tables under
the receipts tab, and the totals bar carries `Delta received (gross)`,
`Delta returned`, `Jindal paid (gross)`, `Jindal returned` beside the net
figures, so the netting can be read off the page instead of being taken on
trust. When neither side has a return, the extra tables and figures are hidden
and the totals are plain gross — the netting adds nothing to a clean period.

Each return row carries a `remark` saying whether the other side booked the same
return:

| Remark | Meaning |
|---|---|
| `… both books agree` | Both ledgers recorded the reversal. Nets out on both sides. |
| `… the other side never booked it` | Only this book recorded the money coming back. This is a genuine difference and will show up in the receipts diff. |

Pairing is by amount, one return consuming one opposite return, so two returns
of the same value do not both claim the same counterpart.

### Views

Five tabs, each Delta on the left and Jindal on the right with its own totals bar
(Delta total, Jindal total, difference): **Receipts**, **Journals**,
**TDS 194Q**, **Interest adj.**, **Credit/debit notes**. The TDS tab also carries
the Step 3 computed figure beside the two booked ones. The receipts tab adds a
second row of tables for returned payments when either side has any, and its
totals are net of them.

There is deliberately **no separate claims tab**. Claims were tried in one, and
pulling them out of the notes list made the notes totals disagree with the ledger
they came from — a row filed by what it *means* rather than by what it *is* stops
tying back to the source. They are tagged and remarked where they lie instead.

The receipts and credit/debit notes tables carry **sort and filter controls**,
with the control chosen by the field's type: a substring box for text, a from/to
pair for amounts and dates, and a dropdown of the values actually present for
`Dr/Cr`, `Vch type`, `Side` and `Claim`. Clicking a header sorts ascending, then
descending, then back to the ledger's own order. Sorting and filtering read the
**raw** value behind the cell, not the rendered text, so amounts sort as numbers
and dates as dates; the two columns the notes tab relabels for display carry a
matching raw accessor so the dropdown offers what is on screen. Blank cells sink
to the bottom of a sort in both directions — a missing value is not a small one.

### The credit/debit notes tab in detail

This tab has two extra pieces of logic worth stating explicitly.

**It holds more than notes.** A claim Delta wrote as a journal (the
`SHORTAGE NON GST` block of FY 2025-26) is listed with Delta's credit notes: same
direction, and the row it is being compared against is a Jindal debit note. Those
rows keep their own `Journal` voucher type on show, and the totals bar carries an
`… of which journals` figure so the Delta side stays decomposable.

**Note type comes from the voucher type, not the Dr/Cr flag.** Delta books every
note as voucher type `CREDIT NOTE ISSUE` while the row's own flag reads `Dr`
(that flag is the ledger side, not the note type). Splitting on the flag labels
all of them debit notes, which is wrong.

**The mirror rule.** The same event is a credit note in one book and a debit note
in the other: the seller issues a credit note reducing what the buyer owes, and
the buyer books a debit note against the seller. So:

```
Delta credit note  ↔  Jindal debit note  (DN)
Delta debit note   ↔  Jindal credit note (CN)
```

Because the pairing is fixed, the two "points of view" contain identical table
pairings — only the debit/credit wording flips. The tab therefore has a
**View as** toggle (`Jindal's books` / `Delta's books`) that relabels the four
tables and their totals rather than regrouping them, and always puts the debit
group first. Four tables: Delta CN + Jindal DN as one pair, Delta DN + Jindal CN
as the other. The totals bar carries per-group totals and per-group differences.

Delta's amounts are displayed as `CN`/`DN` and `DR`/`CR` **in this tab only**, so
both sides read in the same vocabulary; the underlying data and the other tabs
keep each party's own labels.

---

## 7. Step 3 — base value and 194Q TDS

`recon/step3.py`, `compute(register_rows, meta, ledger_rows=None)`. Needs a
third input: Delta's **columnar register** export (`profiles/register.md`),
which carries Quantity, Rate and Value. Optional — without it Steps 1 and 2 run
as normal and the Step 3 tab stays disabled.

**The base value is read, never derived.** The register states the taxable
`Value` per invoice. This matters: for the 5% period a flat ₹400/MT compensation
cess means the base cannot be recovered from the invoice total alone — tested,
and each 5% invoice admits 33–40 mathematically valid (quantity, base) pairs.
The derivation formulas in `docs/tds_flow.md` survive only as a cross-check.

Three validations run on every invoice, and all three pass on the current file:

1. `Value + GST + cess + rounding == Gross Total`
2. `cess == cess_rate × Quantity`, with the rate read out of the column header
   (`GST Compensation Cess @ 400 PMT`) rather than hardcoded
3. the register's `Gross Total` ties to the Delta ledger's amount for that bill

**Credit notes are classified before they are netted**, because they are not
all the same thing. A note that posts to a *goods* ledger reverses a sale — its
value and its tonnage both come off that slab, and `step3` pairs it with the
invoice it cancels by equal-and-opposite value and quantity. A note that posts
to a *difference* ledger (quality, rate) adjusts the price of coal that was
delivered: its value comes off, its stated tonnage must not. A note's own
voucher type does not carry its slab — the GST ledger it uses does
(`CGST @ 2.5%` → 5%, `CGST @ 9%` → 18%).

A reversed invoice legitimately shows as unmatched in Step 1 when the buyer
never booked the delivery, so Step 1's unmatched table carries a "Reversed by"
column fed from Step 3.

Then, **per financial year** (April–March, bucketed on invoice date — a file
longer than twelve months holds more than one, and the threshold is per year):

```
net purchase value = Σ invoice base + Σ note base   (notes carry a negative Value)
TDS                = 0.1% × max(0, net purchase value − ₹50,00,000)
```

compared against the TDS actually booked, taken from the register's
`Tds Receivable 194Q …` column. A per-slab breakdown (count, tonnage, base, GST,
cess, total) sits underneath.

**"TDS booked" here is Delta's book only** — the register is Delta's export, and
its TDS ledger columns are Delta's receivable. Jindal's own 194Q never enters
Step 3. For what each side recorded against the other, use the Step 2 **TDS
194Q** tab; Step 3 answers the different question of what 194Q should have been.

### Views

Step 3 panel, five tabs: **TDS position** (financial years as columns, the
computation as rows, plus the slab breakdown), **Invoices** (per-invoice
quantity, rate, base, GST, cess, total), **Note adjustments**, **TDS booked**
(the actual journal entries), and **Checks** (what passed, and every warning
raised).

Findings and the two open items for the accountant: `docs/tds_flow.md`.

---

## 7a. The Timeline and Closing-position panels

Two panels are not steps and are easy to miss when rebuilding.

**Timeline** (the landing panel) lists one collapsible card per financial year,
newest logic first: matched count, matched difference, unmatched count; expanded,
the matched value, mismatch count, per-side unmatched counts, unmatched
difference, and — when a register was uploaded for that year — 194Q computed,
booked and the difference. Clicking a card's button switches the whole viewer to
that year. It is the only place the years can be compared at a glance, and it is
what makes a seven-year export navigable at all.

Two notes appear on a card when they apply: *no invoices in this financial year*
(the `sparse` flag), and *no register uploaded for this year, so Step 3 is
unavailable*. Both exist so an empty panel is explained rather than looking
broken.

**Closing position** shows, for the whole range: each side's closing balance, the
difference, the four-bucket bridge, the invoice-gap detail, and a per-year table
of movement and running closing on both sides. Unlike Steps 1–3 it is **not**
sliced by the year selector — it is always the full range, because a closing
balance is only meaningful cumulatively.

---

## 8. The viewer

`recon/render_page.py` holds the whole page as one HTML template string and
`build(payload, period)` injects the `years.reconcile` structure as a single JSON
blob plus the reporting period label (derived from the data's own min/max dates —
nothing about the period is hardcoded).

Structure: a left rail of five entries — Timeline, Steps 1–3, Closing position —
one panel each, tabs within a panel. A year selector switches which year's
payload Steps 1–3 render; every table is redrawn from `DATA.years[ACTIVE]`. The
Step 3 rail entry is disabled when no register was uploaded for the active year. All
rendering is done by two small generic helpers — `renderTable(elId, rows,
columns, opts)` where a column is `{label, get(row), cls, key, type, val}`, and
`renderTotals(elId, totals, extra)` — with `deltaCols()` / `jindalCols()`
supplying the standard column sets. Adding a category to Step 2 is a tab, a pair
of `<div>`s, and two `renderTable` calls; it does not need new rendering code.

`get(row)` returns display HTML, so sorting and filtering must not read it. They
read `val(row)`, or `row[key]` when there is no `val` — the number behind a
formatted amount, the ISO date behind a date cell. A column that rewrites its
value for display (Delta's `CREDIT NOTE ISSUE` shown as `CN`) supplies a `val`
returning what is on screen, so its dropdown offers the same vocabulary the
reader sees. A column with neither `key` nor `val` is display-only and gets no
control.

Passing `{controls: true}` adds a sort header and a filter row, with the control
picked from `type`: `text` a substring box, `enum` a dropdown of the values
present, `num` and `date` a from/to pair using native inputs. It is on for the
receipts and credit/debit notes tables.

The filter and sort logic sits between the markers `// --- pure filter/sort
logic` and `// --- end pure filter/sort logic ---`. `recon/test_table_controls.py`
lifts exactly that block out of this file and runs it under node, so the test
exercises the shipped code rather than a copy of it.

Design: light and dark palettes both defined with CSS custom properties, serif
display face for headings, monospace with tabular figures for every number,
Indian digit grouping via `toLocaleString('en-IN')`.

---

## 9. Rebuilding from scratch — order of work

1. Write the parsers against `profiles/*.md`; assert the letterhead and the
   parsed row count before going further.
2. `step1.compute` — group by bill number, diff, three buckets.
3. `render_page.build` — the shell, the generic table/totals helpers, Step 1's
   two tabs.
4. `step2.compute` — the categories, then the side-by-side tabs. Build them by
   voucher type first and get the totals tying back to the ledger, *then* add the
   reference-based rules (`CF-` for TDS, `TP/` for transfers, `BD/` for interest)
   that move rows out of the journals.
5. The notes tab's voucher-type split, then the mirror-rule POV toggle.
6. `link_by_amount` last — claims and advances only make sense once every other
   category has taken its rows out of the candidate pool.
7. `step3.compute` once the register is available: validate every invoice
   first, then aggregate per financial year, then compare against booked TDS.
8. `years.reconcile` — slice by financial year, run the steps per slice, add the
   "All years" pass, then `mark_cross_year`. Only now does the timeline exist.
9. `closing.compute` — the signing rules first, opening-balance exclusion second,
   the bucket bridge last. Prove it by checking the four bucket differences sum
   to the difference between the two closing balances.
10. `serve.py` + `upload.html` on top of the `reconcile`/`build` functions.

Each stage is verifiable on its own: the JSON artefacts in `output/` are the
contract between stages, so a refactor is proved safe by diffing them.

Alongside them, `recon/test_*.py` are runnable with nothing but the venv
(`.venv/bin/python recon/test_claims.py`) and cover the rules that are easy to
break silently: bill-key normalisation, the claim and advance linking, the
routing of `TP/` transfers, and the table filter/sort logic.

### Known-good figures to check a rebuild against

A rebuild is only "done" when it reproduces these. Run over
`data/delta 01-04-2019 16-06-2026.xlsx` and
`data/jindal 01-04-2019 16.06.2026.xlsx`, no register, the **All years** pass:

| | Expected |
|---|---|
| Parsed rows | Delta 4,790 · Jindal 6,237 |
| Financial years found | 2019-20 … 2026-27, plus "All years" |
| Bills per side | Delta 4,370 · Jindal 4,346 |
| Matched | 4,339 — of which 4,284 tie exactly, 55 differ in amount |
| Only Delta / only Jindal | 31 / 7 |
| Unrecognised references | 0 |
| Bill-number variants (the two books typed it differently) | 20 |
| Step 2 receipts | 339 / 322 |
| Step 2 journals | 2 / 5 |
| Step 2 credit/debit notes | 54 / 250 |
| Step 2 TDS 194Q | 15 / 1,312 |
| Closing balance | Delta ₹12,52,51,097.61 · Jindal ₹11,99,38,907.00 |
| Closing difference | ₹53,12,190.61 |

And two identities that must hold **exactly**, not approximately — they are the
real test, because they cannot come out right by accident:

```
sum(bridge bucket differences)        == closing difference        (₹53,12,190.61)
invoice_detail subtotal               == invoices bucket difference (₹81,55,835.43)
```

If the first is off, the signing rule or the opening-balance exclusion is wrong.
If the second is off, Step 1's buckets do not account for every invoice row —
usually because the `unrecognised` bucket was dropped.

A useful smoke test of the whole thing in one line:

```
.venv/bin/python -c "import sys; sys.path.insert(0,'recon'); import years; \
from parsers import delta as d, jindal as j; \
D=d.parse('data/delta 01-04-2019 16-06-2026.xlsx'); \
J=j.parse('data/jindal 01-04-2019 16.06.2026.xlsx')[1]; \
r=years.reconcile(D,J); c=r['closing']['overall']; \
print(r['years']['All years']['step1']['summary']); \
print(round(sum(b['difference'] for b in c['bridge']),2) == c['difference'])"
```
