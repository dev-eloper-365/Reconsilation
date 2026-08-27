# Learnings — reconciliation workflow

Running log of things discovered while building this that matter for
generalizing into a web tool later. Not a how-to; see `profiles/*.md` for
per-company parsing rules.

## Company profiles are unavoidable

Every party exports Tally differently: sheet layout, header row offset,
file format (`.xlsx` vs legacy `.xls`), which column carries the amount.
There is no universal parser — the design has to be "one parser module per
counterparty, matched by a config/profile", not one parser with options.
`recon/parsers/delta.py` and `recon/parsers/jindal.py` are the two examples
so far. A generalized tool needs a profile registry keyed by company +
possibly by export template, since the same company could change their
export format over time.

## Verify the file before trusting the filename

First "Jindal 24-25.xlsx" the user uploaded had sheet name
`DELTA GLOBAL RESOURCES PVT. LT` (correct) but the actual letterhead inside
read `AMITARA OVERSEAS PRIVATE LIMITED` — a different, unrelated company.
Bill numbers were in the same `GJ/FY/NNNN` format as the real Jindal file
(coincidence — shared Tally convention) but had **zero overlap** even
though the numeric ranges overlapped. That "270 bills, 0 in common" result
is what exposed the wrong file — a silent 0-match result should always be
treated as a parsing/identity bug, not a real reconciliation finding, until
proven otherwise. **Always assert the parsed letterhead/company name
matches who you think you're loading before running any match.**

The corrected file (`Jindal 25-16.6.2026.xls`) also cross-checked cleanly:
its listed opening balance (₹76,906,248 CR... wait, actually the *closing*
balance of the prior Delta-side file, ₹26,777,934.20, matched the new
Delta file's opening balance exactly) — continuity between a closing and
next-period opening balance is a good sanity check that two exports are
really the same book, same account, adjoining periods.

## Same invoice series, gaps are normal

Jindal's `GJ/FY/NNNN` bill numbers are Jindal's own sales-invoice sequence
across *all* their customers, not a Delta-exclusive series. Gaps between
consecutive numbers on Delta's side are expected (other customers' invoices
fill the gaps) — don't treat gaps as evidence of a missing bill.

## Tally exports lie about which column is which

Delta's export literally swaps Debit/Credit: a row flagged `Cr` puts its
amount under the "Debit" header, and `Dr` under "Credit". Don't trust
column headers over the row's own Dr/Cr flag — always resolve the amount
as "whichever of the two amount cells is non-null" and use the flag
separately if direction matters.

## Matching key for Step 1

Only rows where Bill No. starts with the invoice prefix (`GJ/`) participate
in bill-level matching — bank receipts, journals, and other non-invoice
rows correctly have no bill number and are out of scope for Step 1. If the
same bill number appears on multiple rows on one side (e.g. a debit note
referencing an earlier bill), amounts are summed per bill number before
comparing — comparing single rows 1:1 would miscount those.

## Tooling

- `.xlsx` → `openpyxl`. Legacy `.xls` (BIFF) → needs `xlrd` (openpyxl
  can't read it); dates come back as raw floats needing
  `xlrd.xldate_as_datetime(value, workbook.datemode)`.
- **The same export template arrives in both formats.** Jindal's Ledger
  Statement has turned up as `.xls` (2023-24, 2025-26) and as `.xlsx`
  (2021-22, 2024-25), identical layout either way. A parser tied to one reader
  rejects half of a counterparty's own history, so sniff the magic bytes, load
  a grid, normalise the date cell, and share the row logic.
- Project has its own `.venv` (not the session scratchpad) so the pipeline
  is runnable standalone later: `.venv/bin/python recon/step1.py`.

## Note type is the voucher type, never the Dr/Cr flag

Delta books every credit note as voucher type `CREDIT NOTE ISSUE` while the
row's own flag reads `Dr` — that flag is the ledger side, not the kind of
document. Splitting notes on the flag labelled all six of Delta's credit notes
as debit notes and produced a debit total of ₹27,21,237 against a real debit
total of zero. Classify by voucher type on both sides (`CREDIT NOTE` /
`DEBIT NOTE` in Delta's wording, `CN` / `DN` in Jindal's) and treat the Dr/Cr
column as direction only.

## The mirror rule: one side's credit note is the other's debit note

Same event, opposite document in each book — the seller issues a credit note
reducing what the buyer owes, the buyer books a debit note against the seller.
So `Delta CN ↔ Jindal DN` and `Delta DN ↔ Jindal CN`, always. Two consequences:

- A note view must say **whose books** its debit/credit labels belong to, or it
  is ambiguous. The two points of view contain the same table pairings with the
  wording flipped, so it is a relabelling, not a regrouping.
- Comparing "Delta's credit notes" against "Jindal's credit notes" is comparing
  unrelated things. In the current file that mistake would show a ₹63,24,276
  difference that is really one unmatched Jindal CN sitting in the wrong
  comparison.

## GST-inclusive totals: base value is not always recoverable

Both ledgers record only the invoice grand total. Unwinding an 18% invoice is
just `total / 1.18`, but the 5% period carried a flat ₹400/MT compensation cess,
which is added per tonne rather than as a percentage — so without the quantity
there are two unknowns and one equation. Tested against every plausible tonnage:
each 5% invoice admits **33–40 mathematically valid (quantity, base) pairs**.
Quantity is a required external input, not something to infer, and no
"reasonable rate" heuristic should be allowed to pick one of those 40 answers.

The real fix is upstream, and it worked: the Tally **columnar register** export
carries `Quantity`, `Rate` and `Value` per voucher, so the base value is read
rather than derived. Ask for that export before writing any arithmetic. The
derivation formulas are now only a cross-check — and as a cross-check they are
worth keeping, since they caught nothing but proved all 765 invoices internally
consistent.

## Tax rate periods are cross-checkable, so cross-check them

Three independent signals in the current file agree on all 765 invoices: the
voucher type (`Imported Steam Coal @ 5% GST` vs `@ 18% GST`), the bill series
(`GJ/25-26/…` vs `GJ/18/…` and `GJ/26-27/…`), and the invoice date (5% ends
2025-09-21, 18% starts 2025-09-28, straddling the 22-Sep-2025 coal rate change).
Classify by one and assert the others rather than hardcoding a date window — a
hardcoded window is exactly what breaks when the next period's file arrives.

## An export longer than twelve months spans two financial years

`1-Apr-2025 to 16-Jun-2026` looks like one period but contains FY 2025-26 (586
invoices) and FY 2026-27 (179). Anything with a per-FY rule — the ₹50 lakh 194Q
threshold above all — computed over the whole file is silently wrong. Bucket by
financial year on the invoice date before applying any threshold, and never
assume one file equals one FY.

## Two voucher types can mean two tax regimes, not two products

`Imported Steam Coal @ 5% GST` and `@ 18% GST` are the same product under
different tax law, split by a rate change mid-period. Voucher types that differ
only by a tax rate are a period marker; treating them as separate product lines
loses that.

## Refactor safety comes free from the JSON artefacts

`output/step1_data.json` and `step2_data.json` are the contract between stages,
so extracting `compute()` out of each script to make it importable by the server
was provable: run the CLI, diff the JSON against the previous run, require zero
difference. Worth keeping that property — any stage that renders straight from
memory without a dumpable artefact loses it.

## Ask what else the export can carry before writing arithmetic

The plain ledger and the columnar register are the *same vouchers from the same
Tally* — 901 rows either way. One carries only a date, a voucher number and an
amount; the other adds quantity, rate, taxable value, and one column per ledger
the voucher touched, including the TDS receivable. A session was spent proving
the base value could not be derived from the first file, when the second file
existed all along. Before deriving anything from a Tally export, ask what
columns that export *can* be given.

## Columnar exports have variable columns — resolve them by header text

Everything after `Gross Total` in the register is one column per ledger account
posted in that period, so the column count and names change from export to
export. Two traps, both hit:

- Matching a column group by "first header that matches" halves the answer when
  a period spans a rate change: `CGST @ 2.5%` and `CGST @ 9%` are both present,
  and GST has to be the **sum** of every matching column.
- Rates written into headers (`GST Compensation Cess @ 400 PMT`,
  `Tds Receivable 194Q F.Y. 2025-26`) should be *read out of* the header, not
  hardcoded. The cess rate is a matter of law and the TDS column names a single
  financial year, which is how "no TDS booked for FY 2026-27" turned out to be
  "that year has no column yet" rather than a shortfall.

## Credit notes carry a negative Value — add, don't subtract

In the register the six credit notes total **−₹25,37,514.59**. The instinct is
"notes reduce the purchase value, so subtract them", which adds ₹50.75 lakh to
the base and inflates the TDS. Check the sign in the data before choosing the
operator; a sign error here moves the answer by twice the note value and still
looks plausible.

## Two files that both start with a "Date" header can still be different files

The register and the plain ledger both put `Date` in column A of their header
row, so the plain ledger's parser finds a header row in the register and then
reads GSTIN as the debit amount — silent nonsense rather than an error. Parsers
need a second assertion beyond "found the header": the ledger parser now
requires column 6 of that row to read `Debit`, and says which file it thinks it
was handed when it does not.

## A validation that passes is still worth building

All three Step 3 cross-checks (components rebuild the total, cess equals rate ×
quantity, register total ties to the ledger) pass on all 765 invoices and found
nothing. They are still the reason the ₹5,904 TDS difference can be reported as
a real accounting question rather than "possibly our arithmetic" — the value of
a check is that it narrows where a difference can be hiding.

## Not every credit note is the same animal — check what ledger it posts to

Credit note `DGRPL/25-26/024` (30-Apr-2025) is a **full reversal** of invoice
`GJ/25-26/0994`: −45.900 MT against +45.900 MT, −₹3,32,228.79 against
+₹3,32,228.79, same ₹3,67,200 gross. The truck was diverted to another buyer, so
the sale un-happened. Notes `178` / `179` / `180` are nothing like it — they are
quality and rate differences on coal that *was* delivered.

The discriminator is the ledger column the note posts to, which only the
columnar register shows:

| Note posts to | Meaning | Treatment |
|---|---|---|
| a **goods** ledger (`Imported Steam Coal@5%`) | the sale is reversed | net off both value **and** tonnage for that slab |
| a **difference** ledger (`Quality Difference - Coal`, `Rate Difference - Coal`) | price adjustment on delivered goods | net off value only — **never** the tonnage |

Getting this wrong is easy and invisible. Notes `192` and `193` state
quantities of 4,069.09 MT and 205 MT, but those tonnes were delivered and
invoiced; netting them off delivered tonnage would remove 4,274 MT that
physically moved. Only the 45.9 MT reversal is a real quantity reversal.

**In the next scan, check for:**

1. **A note whose value and quantity are equal and opposite to a single
   invoice** — that is a full reversal. `recon/step3.py` pairs them
   automatically and names both documents.
2. **The reversed invoice showing as unmatched in Step 1.** `GJ/25-26/0994` is
   one of the eight only-in-Delta bills for exactly this reason: the buyer never
   booked a delivery that was diverted away. That is the reversal working, not a
   missing bill — but it is indistinguishable from a genuinely missing bill
   without the note to explain it, which is why Step 1's unmatched table now
   carries a "Reversed by" column.
3. **A goods-ledger note that matches no invoice equal-and-opposite** — likely a
   partial reversal, which needs manual pairing. Flagged as a warning.
4. **Slab attribution.** A note's own voucher type says only
   `CREDIT NOTE ISSUE`; the GST ledger it uses is what identifies its slab
   (`CGST @ 2.5%` → 5%, `CGST @ 9%` → 18%). Note `192` is an 18% note sitting
   among 5% ones, and putting it in the wrong slab moves ₹2,96,050.95.

## The same counterparty's export can drop the join key between years

Jindal's FY 2025-26 Ledger Statement populates `Bill No.` on every `PU` row.
Jindal's FY 2023-24 Ledger Statement, same company, same export template, has
that column **completely empty** across all 811 purchase rows. Everything else
parses: 811 PU, 48 DN, 40 JV, 31 BP, totals within 0.5% of Delta's side. There
is simply no key to match on.

So "zero bills matched" has at least two distinct causes that need opposite
responses, and the tool now separates them:

- **No bill numbers in one file** — the export is missing the column. Re-export
  from Tally with `Bill No.` shown. Nothing about the code can fix it.
- **Bill numbers present on both sides but non-overlapping** — wrong
  counterparty, wrong period, or the wrong file entirely.

Measured fallback options, for when a re-export is impossible: amount alone
pairs 797 of 807 rows, but 50 amounts are ambiguous (repeat on a side), and
date+amount pairs only 3 — the buyer books on the inward date, days after the
seller's invoice date, so dates cannot disambiguate. Any amount-based matcher
must therefore be labelled approximate and keep the ambiguous set separate.

## Identify uploads by content, not by which box they were dropped in

Three consecutive upload failures were all the same mistake: the right files,
the wrong slots. Both Delta exports are `.xlsx` with the *counterparty* as the
sheet name, so "which file is which" is genuinely not obvious from outside.

Every export in this project self-identifies, and reading that is more reliable
than filename, extension, or slot:

| Signal | Delta ledger | Register | Jindal ledger |
|---|---|---|---|
| Header row starts | `Date` | `Date` | `Voucher No.` |
| Header contains | `Debit`, `Credit` | `Value`, `Gross Total` | — |
| Letterhead (A1) | Delta … | Delta … | JINDAL DENIMS INC. |

`recon/identify.py` routes uploads on that basis, so the slots are labels only.
The failure that remains is the one worth reporting: *"missing the Jindal
ledger; what was uploaded was two Delta-side files"* — which names the real
problem instead of complaining about a file extension.

## Normalise the join key — the same bill number is typed two ways

FY 2021-22 reported 10 bills as "only in Jindal" and 27 as "only in Delta".
Thirteen of those were the *same bills*, keyed differently:

| Delta wrote | Jindal wrote |
|---|---|
| `GJ/21-22/0655` | `GJ/21-22/ 0655` (space after the slash) |
| `GJ/21-22/0629` | `GJ/21-22/0629.` (trailing dot) |
| `GJ/21-22/0604` | `GJ /21-22/0604` (space *before* the slash) |

Amounts tied to the rupee in every case. Matching raw strings turned thirteen
perfect matches into twenty-six phantom exceptions — the most misleading output
this tool can produce, because an unmatched bill reads as a missing document.

`step1.normalise_bill` now strips **all** whitespace (not just the ends),
upper-cases, and trims trailing punctuation, keeping the original for display so
the viewer can show "written by Jindal as …". After that, FY 2021-22 goes from
206 to **219 matched, zero unmatched on the Jindal side**, and FY 2025-26 is
unchanged at 757 — normalisation found real matches without inventing any.

**Whitespace and trailing dots were not the end of it.** Over the full 2019-2026
range, two more pairs were still being reported as unmatched on both sides:

| Delta wrote | Jindal wrote | Amount | What differs |
|---|---|---|---|
| `GJ/23-24/2121` | `GJ/23-24-2121` | ₹3,89,205 | hyphen where the other book puts a slash |
| `GJ/23-24/0534` | ``GJ/23-24/0534` `` | ₹2,83,901 | a stray backtick |

Amounts tied to the rupee again. The normaliser now also drops quoting
characters and collapses every run of separators to a single `/`, which took the
full range from 4,336 to **4,338 matched**, only-Delta 34 → 32, only-Jindal 9 → 7.

The catch that came with it: once separators are collapsed, the key is no longer
a number anyone would recognise — `GJ/23-24/2121` keys as `GJ/23/24/2121`.
Displaying the key would have made every matched bill look mistyped. So the key
is now strictly internal and the viewer shows the form the books **wrote**
(`step1._display`), preferring Delta's when the two disagree, since Delta raises
the invoice. **The more aggressive the normalisation, the more important it is
that the display form comes from the source, not from the key.**

What is *not* worth automating: 13 unmatched bills have an exact amount twin on
the other side under a genuinely different number — Delta's `GJ/19-20/2866` and
Jindal's `GJ/19-20/2869`, both ₹1,38,876, for instance. Matching on amount alone
would silently merge two real invoices. Same digits plus same amount is
evidence; same amount alone is a coincidence worth showing a human, no more.

Worth remembering: a hand-keyed reference in one system and a hand-keyed
reference in another will differ in whitespace and punctuation long before they
differ in substance. Normalise before comparing, always; report the raw forms
alongside so a genuine numbering difference is still visible.

## A letter the eye skips: `GI` for `GJ`

`CF/PU/1920/5141`, 19-Mar-2020, ₹1,81,163, booked by Jindal against bill
`GI/1920/2811`. Delta's `GJ/19-20/2811` is the same bill, ₹1,81,162. It sat
unmatched for two reasons at once, and fixing either alone would have changed
nothing:

| | Delta wrote | Jindal wrote |
|---|---|---|
| Series letter | `GJ` | `GI` — letter I for J |
| Financial year | `19-20` | `1920`, unhyphenated |

The letter is the interesting one. `group_by_bill` only admits bills starting
`GJ/`, so `GI/…` never entered the matching pool at all. It did not become an
unmatched bill either — it fell into the `unrecognised` bucket, which exists
precisely so that a row belonging to neither the matched nor the unmatched side
does not vanish. That bucket is easy to skim past: **the reconciliation was not
wrong, it was quiet**, and a quiet exception is worse than a loud one.

Frequency is what makes this safe to automate: across 2019-2026, `GJ` appears
4,345 times and `GI` once; the year segment is hyphenated 4,344 times and joined
once. Both anomalies are single occurrences of an otherwise rigid pattern, which
is the signature of a typo rather than of a second series. So the normaliser
rewrites a leading `GI/` to `GJ/` and joins a two-plus-two year — narrowly, at
the prefix only, and requiring exactly two digits either side so the `2526` in
`GJ/18/2526/1426` is not mistaken for a financial year.

Result: 4,338 → **4,339 matched**, only-Delta 32 → 31, unrecognised 1 → 0, no
match lost. The bill now shows a ₹1 difference, which is the rounding on Delta's
invoice (base ₹1,54,844.43 + GST ₹7,742.22 + cess ₹18,576 + rounding ₹0.65) —
a real, tiny, visible discrepancy in place of a silent absence.

**The lesson:** before adding a character-substitution rule, count how often each
form occurs. One occurrence against four thousand is a typo. A hundred against
four thousand is a second series, and rewriting it would destroy real
information.

## One event, two books, two names — and the naming side changes

Jindal raises a claim against a shipment as a debit note narrated `SHORTAGE A/C`,
`RATE DIFFERENCE`, `QUALITY CLAIMS` or `WEIGHT DIFFERENT`. Delta answers with a
credit note. They never share a reference, and their dates are months apart —
Jindal books per shipment on the day, Delta at year end. The amount is the only
thing the two rows have in common.

The first attempt searched one way: start from a Jindal row that names a claim,
look for Delta's answer. It found 10 of 28. The reason it missed the rest is the
part worth remembering:

| Period | Who names the claim | Who narrates it as ordinary coal |
|---|---|---|
| to FY 2021-22 | Jindal (`RATE DIFFERENCE`) | Delta (`Imported Steam Coal@5%`) |
| FY 2022-23 on | Delta (`RATE DIFFERENCE - SALES`) | Jindal (`COAL & FUELS`) |

**The convention flipped mid-history.** A one-directional search was right for
half the data and silently wrong for the other half — and its wrongness was
confidently worded: 20 Delta credit notes carried the remark *"Jindal raised no
note for this amount"* when Jindal had raised one for the identical amount,
`DGRPL/22-23/473` ₹15,25,935 against a Jindal DN of the same day among them.

Searching from a named row on **either** side took it to 30 of 35 on Delta's side
and 48 rows on Jindal's, with zero unpaired rows left having a same-amount
counterpart anywhere.

**The lesson, twice over.** A cross-book heuristic must be symmetric unless you
have checked that the asymmetry holds for the whole period — conventions change,
and the data before FY 2022-23 is not evidence about the data after it. And a
remark that asserts a negative (*"the other side has none"*) is a claim about
completeness; it is only as trustworthy as the search behind it, so it deserves
the same scepticism as a match.

## Pair on amount, but pair carefully

`step2.link_by_amount` is shared by claims and advances. Four rules earn their
place, each after something went wrong without it:

1. **Two passes.** Rows both books named pair first. Otherwise a generically
   narrated note takes an amount away from the row that actually names the claim.
2. **Nearest date breaks a tie.** Amounts repeat — `CF-2223-1546` alone answers
   four different Delta notes.
3. **One row is used once.** Without it, several claims of the same value all
   point at one counterpart.
4. **Keep the pool clean.** TDS and interest journals are excluded from
   candidates. 1,312 Jindal TDS JVs in the pool is 1,312 chances for a
   coincidental amount to take a real counterpart before the right row gets it.

And the safeguard that makes amount-pairing acceptable at all, the same one Step
1 uses for invoices: **tag and remark, never merge.** Both rows stay visible with
the basis of the link written on them. Netting them into one figure would hide a
guess inside a total.

A related trap, found while testing: Delta's `Debtors Written Off` journal is
₹22,02,585.24 and so is a Jindal JV. They are not related. Only rows whose
narration names the event are starting points; a bare amount coincidence is never
enough to start from.

## A journal can be money moving

Two of Jindal's `JV` families are payments, not adjustments, and both were
sitting in the journals tab distorting the receipts comparison:

| Signal | Rows | Value | What it is |
|---|---|---|---|
| `Ref.No.: TP/…` | 103 | ₹23,54,32,980 | Jindal settling invoices by transfer instead of through its bank ledger |
| matched to Delta's `DGPL - Advances` | 1 | ₹3,64,95,832 | the far side of an advance payment |

Every one of the 103 transfer rows is narrated only `JV LEDGER`. Routing them to
the receipts took the receipts difference from **₹26.4 crore to ₹2.8 crore** —
the gap was never an underpayment, it was a filing decision.

`JV` is a container, not a meaning. Tally's voucher type says how an entry was
posted, not what it was for; `Receipt`, `BP`, `Journal` and `JV` are all shaped
by whichever module the clerk happened to use. Classify on the **reference**
where there is one, and the voucher type only as a last resort.

## When one book names an event and the other does not, follow the naming

The advance shows the rule in its cleanest form. Delta writes `DGPL - Advances`;
Jindal's half of the same transfer reads `JV LEDGER` with no reference at all.
Only the amount and the date connect them.

The reflex is to write a rule for "Delta's advance journals". The durable version
is: **the row that names the event decides what the event is; the row found only
by amount inherits it.** That is why the selection keys off the tag the linker
wrote and not off the narration — the narration exists on one side only, and
which side that is, is not something to hard-code.

Both halves then move to the receipts together. Moving only the named half
opened a ₹3.64 crore hole in the receipts difference that was purely an artefact
of where the two rows were filed.

## File by what a row *is*, not by what it *means*

Claims were first given their own tab. It read well and it was wrong: pulling 30
credit notes out of the notes list made the notes tab's totals stop agreeing with
the ledger those rows came from. Anyone checking the tab against Tally would have
found a gap with no explanation in the tool.

Rows now stay in the tab their voucher type puts them in, and carry a tag and a
remark instead. The two exceptions are deliberate and both preserve the tie-back:

- a claim Delta wrote as a **journal** is listed with its credit notes, because
  the row it is compared against is a Jindal debit note — and the totals bar
  carries an `… of which journals` figure so the Delta side stays decomposable;
- an **advance** moves to the receipts on both sides at once, so no total is left
  half-counting it.

The general rule: a derived view may re-group rows, but every total it shows must
still be traceable to a set of source rows someone can find in the export.

## A year-end file cuts off mid-flow

Ten of FY 2021-22's fourteen remaining Delta-only bills (₹53,09,980) are dated
26–30 March 2022, against a Jindal ledger ending 31 March 2022. Goods invoiced
in the last week of a financial year are received and booked by the buyer in the
next one, so they are *expected* to be missing — they will appear in the buyer's
following-year statement, not as a discrepancy.

When reviewing unmatched bills, sort by date first: a cluster in the final days
of the period is a cutoff artefact, not a finding. What deserves attention is
what remains after removing the cutoff cluster and any reversed invoices — here,
three October bills totalling ₹11,86,703.

## A failed payment comes back, and receipts are gross until you net it

FY 2020-21 receipts differed by ₹44,28,883 with no obvious cause: both books
carried the same invoices, and the bank lines looked ordinary. The difference was
in voucher types Step 2 was not reading at all.

A payment can fail — a bounced cheque, a rejected transfer — and the bank returns
the money. Neither book records that as a receipt:

| Book | Voucher type | Rows | Amount |
|---|---|---|---|
| Delta | `Payment` (money leaving Delta again) | 4 | ₹65,79,258 |
| Jindal | `BR`, bank receipt (money coming back) | 1 | ₹21,50,375 |

Step 2 classified receipts as Delta `Receipt` against Jindal `BP` and ignored
both of these types, so the inward leg was counted and the outward leg was not.
Netting returns off receipts took FY 2020-21 from a ₹44,28,883 gap to **exactly
zero**.

The arithmetic mattered less than the reading. Of the four Delta returns, one
(₹21,50,375, 30-09-2020) is mirrored by Jindal's single `BR` on the same date —
both books agree the money came back. The other three total ₹44,28,883, which is
precisely the gap that existed before: money Delta says came back that Jindal
never booked going out in the first place. So each return row now carries a
remark saying whether the other side booked it too, and that remark is the
finding — the netting alone would have closed the year without ever explaining
which of the two situations it was.

Generalising: **before comparing two cash columns, enumerate every voucher type
each book uses on those accounts, not just the ones you expect.** A category the
classifier does not name is not absent from the data, only from the total.

## A bill can sit in the other book for years, not just one

The unmatched buckets are cut by date, so an invoice raised in March and booked
by the counterparty in May is unmatched on both sides while nothing is missing.
The obvious fix is to check the neighbouring year. That is not enough: a voucher
can go unpaid and unbooked for several years, and a check that only looks one
year either way reports it as a missing document.

`years.mark_cross_year` compares **every year against every year** and states the
distance in the remark ("Booked by Jindal in 2024-25 (5 years later)"), so a
one-year cutoff artefact and a five-year-dormant voucher do not read the same. In
this dataset every late booking happens to be exactly ±1 year — 35 later, 34
earlier, none longer — but that is a property of the data, not a licence to only
check the neighbour.

Two details are load-bearing. The lookup keys on the **normalised** bill number,
because a bill booked in a different year is often typed differently too, and
keying on the displayed form would miss exactly the cases the remark is for. And
the fallback that reads the financial year out of the invoice number itself
requires the two halves to be **consecutive** years, so `GJ/18/2526/1755` gives
2025-26 while the trailing `1755` is not misread as 17-55.

## The two books record TDS at completely different granularity

"How much 194Q was booked" has three different answers, and they were spread
across two steps without ever being put next to each other:

| Source | What it is | All years |
|---|---|---|
| Step 3, `tds_computed` | what 194Q *should* be, from the register | ₹12,49,277 |
| Step 3, `tds_booked` | **Delta's** book — the register's `194Q TDS RECEIVABLE …` ledger columns | ₹6,35,937 |
| Jindal's ledger | **Jindal's** book — per-shipment JVs | ₹4,69,186 |

Step 3's "booked" line reads as though it were the booked figure. It is Delta's
only; the register is Delta's export. Jindal's 194Q was never totalled anywhere —
it was a `TDS` pill on rows inside the general journals tab, one of 1,312 of them.

The granularity is why totals are the only comparable thing. Delta books 194Q as
a handful of periodic receivable journals (15 rows over seven years). Jindal
deducts per shipment (1,312 rows). No row on one side has a counterpart on the
other, so this belongs in its own tab with a totals bar, not in a matcher.

## Classify by the reference, not by the narration

Jindal's per-shipment 194Q JVs do not reliably say "TDS". In FY 2025-26, 327 of
582 read `TDS ON PURCHASE OF GOODS`; the other 255 read only `JV LEDGER`. Both
sets are the same thing — one JV per shipment, hung off that shipment's
`CF-####-NN` reference, all under ₹530.

Going by the word "TDS" gave Jindal ₹1,12,773 for the year against Delta's
₹1,97,843 — a ₹85,070 gap. The 255 unlabelled rows total **exactly ₹85,070**.
Classifying on the shipment reference instead ties FY 2025-26 to the rupee:

| FY | Delta booked | Jindal booked | Diff |
|---|---|---|---|
| 2023-24 | ₹2,45,379 | ₹0 | ₹2,45,379 |
| 2024-25 | ₹1,92,715 | ₹1,93,342 | −₹627 |
| 2025-26 | ₹1,97,843 | ₹1,97,843 | **₹0** |
| 2026-27 | ₹0 | ₹78,001 | −₹78,001 |

The general lesson: **in a Tally export the narration is free text and the
reference is structured, so classify on the reference.** The narration is
whatever the person posting the entry typed that day; it is evidence, not a key.
The same reasoning already applies to `BD/JDI/…` (interest adjustments) and
`TP/JDI/…`, which the same rule excludes for free — and `TP/JDI/…` later turned
out to be a payment transfer, not a nothing. See *A journal can be money moving*.

The safeguard that makes this acceptable: rows caught by the reference but not
the narration carry a remark saying so, so a human can see which classification
rested on the heuristic rather than on the text.

## A closing balance is a running total, so what you exclude matters more than what you add

Two things, either of which alone makes the closing position wrong by an amount
large enough to look like fraud.

**Opening-balance rows are not movement.** A multi-year export restates the prior
year's closing at the top of each year block. Summing every row therefore counts
those years twice — ₹3.88 crore of double-count in the 2019-2026 Delta export.
They are dropped by matching "opening balance" in the particulars.

**Each side signs its own way.** Delta keeps a customer account, Jindal a supplier
account; they are mirror images. Signed correctly, both closings are positive
when Jindal owes Delta. Sign one side backwards and the difference comes out at
roughly twice the balance — a number so alarming it invites a hunt for a missing
crore that was never missing.

The defence against both is the same, and it is worth building even though
nothing asks for it: **make the bridge sum exactly.** The four bucket differences
must add to the difference between the two closing balances, to the paisa. An
exact identity cannot come out right by accident, so it catches a sign error, a
double-counted opening balance and a dropped bucket at once. The looser version —
"the numbers look about right" — catches none of them.

A second identity guards Step 1 the same way: the invoice-gap detail (only-Delta,
only-Jindal, amount mismatches, and both unrecognised totals) must equal the
invoice bucket's difference. That one is what makes it impossible to quietly
forget the `unrecognised` bucket, which is exactly the bucket that hid the
`GI/1920/2811` typo.

## Bucket coarsely to prove, finely to read

The closing bridge groups Delta's `Receipt`, `Journal`, `Payment` and `Contra`
against Jindal's `BP`, `BR` and `JV` as one `payments` bucket. Step 2 splits that
same traffic into receipts, journals, TDS, interest, transfers and advances.

That is not an inconsistency to be tidied away. The two books split settlement
differently — Jindal posts TDS and payments as `JV` — so those categories only
reconcile **as a group**. Step 2 splits them because a human investigating needs
them apart; the bridge keeps them together because it needs them to add up.

The general point: a grouping that proves an identity and a grouping that is
readable are different groupings, and forcing one to serve both purposes breaks
whichever purpose is less loudly defended — usually the identity, silently.

## "All years" is not the sum of the years

The per-year slices are cut by each row's own date, on each side independently.
An invoice Delta raised in March and Jindal booked in May is unmatched in *both*
years' slices and matched in the "All years" pass. So the passes genuinely
disagree, and the total is not the sum of the parts.

This is why every year present in **either** ledger gets an entry even when one
side has nothing for it, why the cross-year remark compares every year against
every other rather than the neighbour, and why "All years" exists at all rather
than being computed by adding the years up.

The trap for anyone rebuilding: it is tempting to make the "All years" figures a
roll-up, because it is cheaper and looks equivalent. It would silently report
every cross-year booking as a missing document — the single most misleading
output this tool can produce.

## Merging exports: dedupe on the whole row, and be strict about it

Several exports covering overlapping periods can be uploaded together. Without
deduplication the overlap is counted twice; with the wrong key, real transactions
disappear.

`years.dedupe` keys on the **whole visible row** — date, voucher no., bill no.,
voucher type, amount, particulars. Two rows agreeing on every one of those are
treated as the same row. Anything looser (date + amount, say) would collapse
genuinely repeated transactions, and a dropped transaction is far harder to
notice than a duplicated one: a duplicate shows up as a mismatch, a deletion just
makes the totals quietly smaller.

**Bias a dedupe toward keeping.** The failure you can see beats the failure you
cannot.

## A thin year is real data, not a bug

An export whose period runs a few days past 31 March produces a financial year
with rows in it but no invoices. Rendering that as a normal year shows a row of
zeroes that reads as a catastrophe; dropping it hides real rows.

It is flagged `sparse` and the timeline says outright what it is. The general
habit worth keeping: when a panel would be empty or absurd, spend the line of
code that explains why. An unexplained empty view is indistinguishable from a
broken one, and the reader has no way to tell which they are looking at.

## Open questions for the web-tool generalization

- How to onboard a new company profile without hand-writing a parser each
  time — likely a column-mapping config (which column is date/bill/amount)
  plus a small set of "quirk" flags (swapped Dr/Cr, alternate date format)
  covers most Tally exports, with a python parser as an escape hatch for
  anything stranger.
- Need a place to store the "party B's letterhead must equal X" identity
  check per profile so the wrong-file bug from above is caught
  automatically, not manually.
