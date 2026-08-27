"""Step 3: taxable (base) value per invoice and the section 194Q TDS position.

Reads Delta's columnar register export, which carries the quantity and the
taxable Value the plain ledger lacks, and answers: what is the base value per
financial year, what TDS does 194Q call for on it, and how does that compare
with the TDS actually booked as receivable.

Nothing here derives a base value by arithmetic — the register states it, and
the derivation formulas exist only as a cross-check that the stated value is
internally consistent (see docs/tds_flow.md for why: with a flat per-tonne cess
the base is not recoverable from the invoice total alone).

Usage: .venv/bin/python recon/step3.py
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from parsers import delta as delta_parser
from parsers import register as register_parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTER_FILE = os.path.join(ROOT, "data", "Register 1.4.25 to 16.6.2026.xlsx")
DELTA_FILE = os.path.join(ROOT, "data", "Delta 25-16.6.2026.xlsx")

# Section 194Q: 0.1% on the purchase value above ₹50 lakh, per seller, per FY.
TDS_RATE = 0.001
TDS_THRESHOLD = 5_000_000
# 194Q commenced 01-Jul-2021. Purchases from 01-Apr-2021 count toward the ₹50
# lakh threshold, but tax is deductible only on amounts credited or paid on or
# after commencement — so FY 2021-22 has a part-year deduction base.
TDS_COMMENCEMENT = "2021-07-01"
TOLERANCE = 1.5  # rupees; invoice components are rounded to paise before summing


def fy_of(date_str):
    """Indian financial year label for an ISO date — April to March."""
    d = datetime.date.fromisoformat(date_str)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def rate_period(vch_type):
    """The GST slab is written into the voucher type, which is the most direct
    of the three signals that identify a rate period (see learnings.md)."""
    v = (vch_type or "").replace(" ", "")
    for slab in ("18%", "12%", "5%", "0%"):
        if slab in v:
            return slab
    return None


def is_invoice(row):
    return rate_period(row["vch_type"]) is not None and row.get("value") is not None


# Notes name the invoice they act on in their own narration, in several
# phrasings: "Issued against:GJ/19-20/2864", "Issued Aginst: GJ/…",
# "BEING SHORTAGE AGAINST INVOICE NO GJ/24-25/2147". The reference is worth far
# more than an amount match, because a partial reversal matches no amount.
INVOICE_REF = re.compile(r"\b(GJ\s*/\s*[\w-]+\s*/\s*\w+)", re.I)


def referenced_invoices(*texts):
    out = []
    for text in texts:
        for m in INVOICE_REF.finditer(text or ""):
            ref = "".join(m.group(1).split()).upper()
            if ref not in out:
                out.append(ref)
    return out


def is_note(row):
    return "NOTE" in (row["vch_type"] or "").upper()


def r2(x):
    return round(x or 0, 2)


def slab_of(ledger_headers, gst_headers):
    """A note's voucher type says only 'CREDIT NOTE ISSUE'; the GST ledger it
    posts to is what identifies its rate slab (CGST @ 2.5% -> 5%, @ 9% -> 18%)."""
    for h in ledger_headers:
        if h in gst_headers:
            m = re.search(r"@\s*([\d.]+)\s*%", h)
            if m:
                return f"{float(m.group(1)) * 2:g}%"
    return None


def compute(register_rows, meta, ledger_rows=None):
    cess_per_unit = meta.get("cess_per_unit")
    gst_headers = set(meta.get("gst_columns", []))
    special_headers = set(meta.get("special_columns", {}).values()) | gst_headers

    # Ledgers the invoices themselves post to are the goods ledgers. A note that
    # posts to one of those is reversing goods — quantity and all. A note that
    # posts anywhere else (Quality Difference, Rate Difference) is a price
    # adjustment on tonnage that was already delivered, and its "quantity" must
    # NOT be netted off the delivered tonnage.
    goods_ledgers = set()
    for row in register_rows:
        if is_invoice(row):
            goods_ledgers |= {h for h in (row.get("ledgers") or {}) if h not in special_headers}

    invoices, notes, tds_entries, warnings = [], [], [], []

    ledger_by_bill = {}
    if ledger_rows:
        for row in ledger_rows:
            bill = row.get("bill_no")
            if bill:
                ledger_by_bill[bill] = ledger_by_bill.get(bill, 0) + (row["amount"] or 0)

    for row in register_rows:
        if row.get("tds"):
            tds_entries.append({
                "date": row["date"], "fy": fy_of(row["date"]), "voucher_no": row["voucher_no"],
                "vch_type": row["vch_type"], "narration": row["narration"], "amount": r2(row["tds"]),
            })

        if is_note(row):
            ledgers = row.get("ledgers") or {}
            own = {h for h in ledgers if h not in special_headers}
            kind = "reversal" if own & goods_ledgers else "adjustment"
            notes.append({
                "date": row["date"], "fy": fy_of(row["date"]), "bill_no": row["voucher_no"],
                "particulars": row["particulars"], "vch_type": row["vch_type"],
                "kind": kind,
                "slab": slab_of(ledgers, gst_headers),
                "against": sorted(own),
                # only a goods reversal moves tonnage; a price adjustment does not
                "quantity": row.get("quantity") if kind == "reversal" else None,
                "stated_quantity": row.get("quantity"),
                "base": r2(row.get("value")), "gst": r2(row.get("gst")),
                "cess": r2(row.get("cess")), "gross": r2(row.get("gross_total")),
                "narration": row.get("narration"),
            })
            continue

        if not is_invoice(row):
            continue

        slab = rate_period(row["vch_type"])
        qty = row.get("quantity")
        base, gst, cess = r2(row.get("value")), r2(row.get("gst")), r2(row.get("cess"))
        gross = r2(row.get("gross_total"))
        rounding = r2(row.get("rounding"))

        # cross-check 1: stated components must rebuild the invoice total.
        # The ROUNDING OFF column carries a magnitude, not a signed amount — it
        # is added or subtracted depending on which way the total was rounded —
        # so test the gap, not a fixed sign. Rounding is sub-rupee by definition.
        gap = r2(gross - (base + gst + cess))
        if abs(gap) > 1.0:
            warnings.append(
                f"{row['voucher_no']}: value {base} + GST {gst} + cess {cess} = "
                f"{r2(base + gst + cess)}, but gross total is {gross} — a gap of {gap}, "
                f"too large to be rounding."
            )
        elif rounding and abs(abs(gap) - abs(rounding)) > 0.05:
            warnings.append(
                f"{row['voucher_no']}: components leave a gap of {gap} against the gross total, "
                f"but the ROUNDING OFF column says {rounding}."
            )
        # cross-check 2: cess is a flat per-tonne charge, so it must equal rate x quantity
        if cess and cess_per_unit and qty and abs(cess - cess_per_unit * qty) > TOLERANCE:
            warnings.append(
                f"{row['voucher_no']}: cess {cess} is not {cess_per_unit} x {qty} MT "
                f"(= {r2(cess_per_unit * qty)})."
            )
        # cross-check 3: the register's invoice total must tie to the ledger's
        if ledger_by_bill:
            ledger_amount = ledger_by_bill.get(row["voucher_no"])
            if ledger_amount is None:
                warnings.append(f"{row['voucher_no']}: in the register but not in the Delta ledger.")
            elif abs(ledger_amount - gross) > TOLERANCE:
                warnings.append(
                    f"{row['voucher_no']}: register total {gross} vs ledger {r2(ledger_amount)}."
                )

        invoices.append({
            "bill_no": row["voucher_no"], "date": row["date"], "fy": fy_of(row["date"]),
            "slab": slab, "quantity": qty, "rate": row.get("rate"),
            "base": base, "gst": gst, "cess": cess, "rounding": rounding, "gross": gross,
            "narration": row["narration"],
        })

    # A goods reversal cancels a specific invoice. Pair them on equal-and-opposite
    # value (and quantity, where stated) so the cancelled invoice can be named —
    # it will legitimately show as unmatched in Step 1, because the counterparty
    # never booked it.
    by_bill = {inv["bill_no"]: inv for inv in invoices}
    reversals = []
    for note in notes:
        if note["kind"] != "reversal":
            continue

        # 1. the invoice the note itself names, if that invoice is in this data
        refs = [r for r in referenced_invoices(note.get("narration"), note.get("particulars"))
                if r in by_bill]
        # 2. otherwise, an invoice this note exactly cancels
        hits = [] if refs else [
            inv for inv in invoices
            if abs(inv["base"] + note["base"]) < 0.01
            and inv["date"] <= note["date"]
            and (note["quantity"] is None or inv["quantity"] is None
                 or abs((inv["quantity"] or 0) + note["quantity"]) < 0.001)
        ]
        matched_no = refs[0] if len(refs) == 1 else (hits[0]["bill_no"] if len(hits) == 1 else None)
        inv = by_bill.get(matched_no)

        extent = None
        if inv:
            # a note cancelling the whole invoice is a different event from one
            # claiming a shortage or a quality difference against part of it
            extent = "full" if abs(inv["base"] + note["base"]) < 0.01 else "partial"

        reversals.append({
            "note_no": note["bill_no"], "note_date": note["date"], "slab": note["slab"],
            "base": note["base"], "gross": note["gross"], "quantity": note["quantity"],
            "invoice_no": matched_no,
            "invoice_date": inv["date"] if inv else None,
            "invoice_base": inv["base"] if inv else None,
            "invoice_quantity": inv["quantity"] if inv else None,
            "extent": extent,
            "matched_by": "reference" if refs and matched_no else ("amount" if matched_no else None),
            "candidates": (refs if len(refs) > 1 else [h["bill_no"] for h in hits]) if not matched_no else [],
            "unresolved_refs": [r for r in referenced_invoices(note.get("narration")) if r not in by_bill],
            "narration": note.get("narration"),
        })
        if inv:
            note["reverses"] = matched_no
            note["extent"] = extent
            if extent == "full":
                inv["reversed_by"] = note["bill_no"]
            else:
                inv.setdefault("reduced_by", []).append(note["bill_no"])

    fys = sorted({r["fy"] for r in invoices} | {r["fy"] for r in notes} | {r["fy"] for r in tds_entries})
    periods = []
    for fy in fys:
        inv = [r for r in invoices if r["fy"] == fy]
        nts = [r for r in notes if r["fy"] == fy]
        tds_booked = r2(sum(t["amount"] for t in tds_entries if t["fy"] == fy))

        base = r2(sum(r["base"] for r in inv))
        # Credit notes carry a negative Value in the register, so adding them
        # reduces the purchase value — do not subtract them a second time.
        note_adj = r2(sum(r["base"] for r in nts))
        net_base = r2(base + note_adj)

        by_slab = {}
        for slab in sorted({r["slab"] for r in inv} | {r["slab"] for r in nts if r["slab"]}):
            slab_rows = [r for r in inv if r["slab"] == slab]
            slab_notes = [r for r in nts if r["slab"] == slab]
            qty = round(sum(r["quantity"] or 0 for r in slab_rows), 3)
            base = r2(sum(r["base"] for r in slab_rows))
            note_qty = round(sum(r["quantity"] or 0 for r in slab_notes), 3)
            note_base = r2(sum(r["base"] for r in slab_notes))
            by_slab[slab] = {
                "count": len(slab_rows),
                "quantity": qty,
                "base": base,
                "gst": r2(sum(r["gst"] for r in slab_rows)),
                "cess": r2(sum(r["cess"] for r in slab_rows)),
                "gross": r2(sum(r["gross"] for r in slab_rows)),
                "note_count": len(slab_notes),
                "note_quantity": note_qty,
                "note_base": note_base,
                "net_quantity": round(qty + note_qty, 3),
                "net_base": r2(base + note_base),
            }

        # Purchases before commencement consume the threshold but are not
        # themselves deductible. After FY 2021-22 this is a no-op.
        pre_base = r2(sum(r["base"] for r in inv if r["date"] < TDS_COMMENCEMENT)
                      + sum(r["base"] for r in nts if r["date"] < TDS_COMMENCEMENT))
        post_base = r2(net_base - pre_base)
        threshold_left = r2(max(0, TDS_THRESHOLD - pre_base))
        taxable = r2(max(0, post_base - threshold_left))
        tds_net = round(TDS_RATE * taxable)
        tds_gross = round(TDS_RATE * max(0, base - TDS_THRESHOLD))
        periods.append({
            "fy": fy,
            "invoice_count": len(inv),
            "note_count": len(nts),
            "quantity": round(sum(r["quantity"] or 0 for r in inv), 3),
            "note_quantity": round(sum(r["quantity"] or 0 for r in nts), 3),
            "net_quantity": round(sum(r["quantity"] or 0 for r in inv) + sum(r["quantity"] or 0 for r in nts), 3),
            "base": base,
            "note_adjustment": note_adj,
            "net_base": net_base,
            "gst": r2(sum(r["gst"] for r in inv)),
            "cess": r2(sum(r["cess"] for r in inv)),
            "gross": r2(sum(r["gross"] for r in inv)),
            "threshold": TDS_THRESHOLD,
            "pre_commencement_base": pre_base,
            "deductible_base": post_base,
            "threshold_applied": threshold_left,
            "taxable_for_tds": taxable,
            "tds_computed": tds_net,
            "tds_computed_before_notes": tds_gross,
            "tds_booked": tds_booked,
            "diff": r2(tds_booked - tds_net),
            "by_slab": by_slab,
        })

    for rev in reversals:
        if rev["invoice_no"] and rev["extent"] == "full":
            warnings.append(
                f"Note {rev['note_no']} fully reverses invoice {rev['invoice_no']} "
                f"({rev['slab']} slab, ₹{abs(rev['gross']):,.2f}"
                + (f", {abs(rev['quantity'])} MT" if rev["quantity"] else "")
                + "). The reversed invoice will show as unmatched in Step 1 if the "
                  "counterparty never booked it — that is the reversal, not a missing bill."
            )
        elif rev["invoice_no"]:
            warnings.append(
                f"Note {rev['note_no']} partly reduces invoice {rev['invoice_no']}: "
                f"₹{abs(rev['base']):,.2f} of ₹{abs(rev['invoice_base'] or 0):,.2f}"
                + (f", {abs(rev['quantity'])} MT of {rev['invoice_quantity']} MT"
                   if rev["quantity"] and rev["invoice_quantity"] else "")
                + f" (matched by the invoice number in its own narration). The invoice stays "
                  f"matched in Step 1 at its full value; only the 194Q base is reduced."
            )
        elif rev["unresolved_refs"]:
            warnings.append(
                f"Note {rev['note_no']} names invoice {', '.join(rev['unresolved_refs'])} in its "
                f"narration, but that invoice is not in this data — it predates the export, or "
                f"belongs to a period not uploaded."
            )
        elif rev["candidates"]:
            warnings.append(
                f"Note {rev['note_no']} looks like a goods reversal but matches "
                f"{len(rev['candidates'])} invoices ({', '.join(rev['candidates'][:4])}) — "
                f"pair it by hand."
            )
        else:
            warnings.append(
                f"Note {rev['note_no']} posts to a goods ledger (so it reverses goods, "
                f"not price) but no invoice matches it equal-and-opposite. Check whether "
                f"it is a partial reversal."
            )

    if len(periods) > 1:
        warnings.append(
            f"This export spans {len(periods)} financial years ({', '.join(p['fy'] for p in periods)}). "
            f"The ₹50 lakh threshold applies separately to each — see learnings.md."
        )
    tds_header = meta.get("special_columns", {}).get("tds")
    if not tds_header and any(p["tds_computed"] > 0 for p in periods):
        warnings.append(
            "This register has no TDS ledger column at all, so there is nothing to compare the "
            "computed 194Q figure against — the 'TDS booked' line reads zero because the data is "
            "absent, not because nothing was deducted. Re-export with the TDS receivable ledger "
            "shown, or confirm the position from Form 26AS."
        )
    elif tds_header:
        # The TDS ledgers are named per financial year, so a year with nothing
        # booked usually means that year has no ledger column in this export.
        columns = [c.strip() for c in tds_header.split(",")]
        for p in periods:
            if p["tds_booked"] == 0 and p["tds_computed"] > 0:
                short = p["fy"][-5:]
                covered = any(short in c or p["fy"] in c for c in columns)
                warnings.append(
                    f"FY {p['fy']}: no TDS is booked, but 194Q computes to ₹{p['tds_computed']:,}. "
                    + (f"The register does carry a TDS column naming this year, so the entries are "
                       f"genuinely absent." if covered else
                       f"This register carries TDS ledgers for {', '.join(columns)} only — none "
                       f"covers {p['fy']}, so the figure cannot be verified from this export.")
                )

    for p in periods:
        if p["pre_commencement_base"]:
            warnings.append(
                f"FY {p['fy']}: ₹{p['pre_commencement_base']:,.2f} of purchases falls before "
                f"194Q commenced on {TDS_COMMENCEMENT}. It counts toward the ₹50 lakh threshold "
                f"but is not itself deductible, so TDS is computed on the "
                f"₹{p['deductible_base']:,.2f} booked on or after that date."
            )

    return {
        "summary": {
            "invoice_count": len(invoices),
            "note_count": len(notes),
            "tds_entry_count": len(tds_entries),
            "reversal_count": len([r for r in reversals if r["invoice_no"]]),
            "financial_years": [p["fy"] for p in periods],
            "warning_count": len(warnings),
            "cess_per_unit": cess_per_unit,
            "tds_rate": TDS_RATE,
            "threshold": TDS_THRESHOLD,
        },
        "periods": periods,
        "reversals": reversals,
        "invoices": invoices,
        "notes": notes,
        "tds_entries": sorted(tds_entries, key=lambda t: t["date"]),
        "warnings": warnings,
        "meta": meta,
    }


def main():
    _, register_rows, meta = register_parser.parse(REGISTER_FILE)
    ledger_rows = delta_parser.parse(DELTA_FILE) if os.path.exists(DELTA_FILE) else None

    data = compute(register_rows, meta, ledger_rows)
    print(json.dumps(data["summary"], indent=2))
    for p in data["periods"]:
        print(f"  FY {p['fy']}: base {p['net_base']:,.2f} -> TDS {p['tds_computed']:,} "
              f"vs booked {p['tds_booked']:,.2f} (diff {p['diff']:,.2f})")
    for w in data["warnings"]:
        print(f"  ! {w}")

    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    with open(os.path.join(ROOT, "output", "step3_data.json"), "w") as f:
        json.dump(data, f, indent=2)
    print("wrote output/step3_data.json")


if __name__ == "__main__":
    main()
