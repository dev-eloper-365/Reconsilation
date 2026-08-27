"""Step 1: match identical bill numbers between Delta's and Jindal's ledgers,
tally the amount on each side, and write output/step1_data.json.
Run recon/render_page.py after to build the viewer from that JSON.

Usage: .venv/bin/python recon/step1.py
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from parsers import delta as delta_parser
from parsers import jindal as jindal_parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DELTA_FILE = os.path.join(ROOT, "data", "Delta 25-16.6.2026.xlsx")
JINDAL_FILE = os.path.join(ROOT, "data", "Jindal 25-16.6.2026.xls")

# Invoice-bearing rows are the ones whose bill no. carries the seller's invoice
# series; everything else (bank receipts, journals, notes) is Step 2's problem.
INVOICE_PREFIX = "GJ/"


def normalise_bill(bill_no):
    """The two books type the same bill number differently — 'GJ/21-22/ 0655'
    with a stray space, 'GJ/21-22/0629.' with a trailing dot, 'GJ/23-24/0534`'
    with a stray backtick, 'GJ/23-24-2121' with a hyphen where the other book
    puts a slash. Comparing raw strings reports those as bills missing from one
    side, which is the single most misleading thing this tool can do. Match on a
    key with the typing differences removed — separators are all one character,
    quoting junk is gone — and keep the written form for display."""
    if not bill_no:
        return None
    key = re.sub(r"""[\s`'"]""", "", str(bill_no)).upper()
    key = re.sub(r"[-/\\]+", "/", key)
    # 'GI/1920/2811' — the party typed I for J on the invoice series, and wrote
    # the financial year as one number where the other book hyphenates it.
    # Both are typing slips on the same bill, not a different document.
    key = re.sub(r"^GI/", "GJ/", key)
    key = re.sub(r"^([A-Z]+)/(\d\d)/(\d\d)/", r"\1/\2\3/", key)
    return key.strip("./,;:") or None


def looks_like_reference(bill_no):
    """A bill number that isn't ours but is clearly meant to be a document
    reference — Jindal has booked one as 'GI/1920/2811', letter I for J. Such a
    row belongs to neither the matched nor the unmatched bucket, so without
    catching it here it vanishes from the reconciliation entirely."""
    return bool(bill_no) and "/" in bill_no and any(c.isdigit() for c in bill_no)


# Voucher types that are NOT an invoice, on either side. A credit note's own
# number (DGRPL/25-26/024) is not a stray invoice reference, so a note must not
# be flagged as one.
NON_INVOICE = ("RECEIPT", "JOURNAL", "PAYMENT", "CONTRA", "NOTE", "BP", "BR", "JV", "DN", "CN")


def is_invoice_row(row):
    vch = (row.get("vch_type") or "").upper()
    return not any(kind in vch for kind in NON_INVOICE)


def unrecognised(rows, prefix=INVOICE_PREFIX, key="bill_no"):
    """Invoice rows whose bill number is not in the invoice series at all."""
    out = []
    for row in rows:
        bill_no = normalise_bill(row.get(key))
        if (bill_no and not bill_no.startswith(prefix)
                and looks_like_reference(bill_no) and is_invoice_row(row)):
            out.append({**row, "bill_no": str(row[key]).strip()})
    return out


def group_by_bill(rows, prefix=INVOICE_PREFIX, key="bill_no"):
    groups = defaultdict(lambda: {"amount": 0, "rows": [], "raw": set()})
    for row in rows:
        bill_no = normalise_bill(row.get(key))
        if not bill_no or not bill_no.startswith(prefix):
            continue  # not an invoice-bearing row (bank receipt, journal, etc.)
        g = groups[bill_no]
        g["amount"] += row["amount"] or 0
        g["rows"].append(row)
        g["raw"].add(str(row.get(key)).strip())
    return groups


def _raw(group, shown):
    """The bill number as actually written, when it differs from what is shown."""
    written = sorted(r for r in group["raw"] if r != shown)
    return written[0] if written else None


def _display(*groups):
    """The bill number to show. The matching key flattens separators, so it is
    not a number anyone would recognise on an invoice — show the form the books
    actually wrote, the most common one when they disagree."""
    forms = defaultdict(lambda: [0, 0])
    for rank, g in enumerate(groups):
        for written in g["raw"]:
            forms[written][0] += 1
            forms[written][1] = min(forms[written][1] or rank, rank)
    # Ties go to the first group given — Delta raises the invoice, so when the
    # two books type it differently, Delta's is the number on the document.
    return min(forms, key=lambda f: (-forms[f][0], forms[f][1], f))


def compute(delta_rows, jindal_rows, prefix=INVOICE_PREFIX):
    """Bill-level match between two parsed ledgers -> the step1_data payload."""
    delta_by_bill = group_by_bill(delta_rows, prefix)
    jindal_by_bill = group_by_bill(jindal_rows, prefix)

    common_bills = sorted(set(delta_by_bill) & set(jindal_by_bill))
    matched = []
    for key in common_bills:
        bill_no = _display(delta_by_bill[key], jindal_by_bill[key])
        d_amt = round(delta_by_bill[key]["amount"], 2)
        j_amt = round(jindal_by_bill[key]["amount"], 2)
        d_row = delta_by_bill[key]["rows"][0]
        j_row = jindal_by_bill[key]["rows"][0]
        matched.append({
            "bill_no": bill_no,
            "date": d_row["date"],
            "delta_amount": d_amt,
            "jindal_amount": j_amt,
            "diff": round(d_amt - j_amt, 2),
            "delta_drcr": d_row["drcr"],
            "delta_particulars": d_row["particulars"],
            "delta_vch_type": d_row["vch_type"],
            "delta_row_count": len(delta_by_bill[key]["rows"]),
            "jindal_date": j_row["date"],
            "jindal_voucher_no": j_row["voucher_no"],
            "jindal_vch_type": j_row["vch_type"],
            "jindal_particulars": j_row["particulars"],
            "jindal_side": j_row["side"],
            "jindal_row_count": len(jindal_by_bill[key]["rows"]),
            "delta_bill_written": _raw(delta_by_bill[key], bill_no),
            "jindal_bill_written": _raw(jindal_by_bill[key], bill_no),
        })

    only_delta = []
    for key in sorted(set(delta_by_bill) - set(jindal_by_bill)):
        bill_no = _display(delta_by_bill[key])
        row = delta_by_bill[key]["rows"][0]
        only_delta.append({
            "bill_no": bill_no,
            "amount": round(delta_by_bill[key]["amount"], 2),
            "date": row["date"],
            "drcr": row["drcr"],
            "particulars": row["particulars"],
            "vch_type": row["vch_type"],
            "row_count": len(delta_by_bill[key]["rows"]),
            "bill_written": _raw(delta_by_bill[key], bill_no),
        })

    odd_delta = unrecognised(delta_rows, prefix)
    odd_jindal = unrecognised(jindal_rows, prefix)

    only_jindal = []
    for key in sorted(set(jindal_by_bill) - set(delta_by_bill)):
        bill_no = _display(jindal_by_bill[key])
        row = jindal_by_bill[key]["rows"][0]
        only_jindal.append({
            "bill_no": bill_no,
            "amount": round(jindal_by_bill[key]["amount"], 2),
            "date": row["date"],
            "voucher_no": row["voucher_no"],
            "vch_type": row["vch_type"],
            "particulars": row["particulars"],
            "side": row["side"],
            "row_count": len(jindal_by_bill[key]["rows"]),
            "bill_written": _raw(jindal_by_bill[key], bill_no),
        })

    summary = {
        "delta_bill_count": len(delta_by_bill),
        "jindal_bill_count": len(jindal_by_bill),
        "matched_count": len(matched),
        "matched_exact_count": sum(1 for m in matched if m["diff"] == 0),
        "matched_mismatch_count": sum(1 for m in matched if m["diff"] != 0),
        "only_delta_count": len(only_delta),
        "only_jindal_count": len(only_jindal),
        "bill_variant_count": sum(
            1 for m in matched if m["delta_bill_written"] or m["jindal_bill_written"]),
        "unrecognised_count": len(odd_delta) + len(odd_jindal),
    }

    matched_delta_total = round(sum(m["delta_amount"] for m in matched), 2)
    matched_jindal_total = round(sum(m["jindal_amount"] for m in matched), 2)
    only_delta_total = round(sum(r["amount"] for r in only_delta), 2)
    only_jindal_total = round(sum(r["amount"] for r in only_jindal), 2)
    totals = {
        "matched": {"delta": matched_delta_total, "jindal": matched_jindal_total, "diff": round(matched_delta_total - matched_jindal_total, 2)},
        "unmatched": {"delta": only_delta_total, "jindal": only_jindal_total, "diff": round(only_delta_total - only_jindal_total, 2)},
    }

    return {
        "summary": summary,
        "totals": totals,
        "matched": matched,
        "only_delta": only_delta,
        "only_jindal": only_jindal,
        "unrecognised": {
            "delta": odd_delta, "jindal": odd_jindal,
            "delta_total": round(sum(r["amount"] or 0 for r in odd_delta), 2),
            "jindal_total": round(sum(r["amount"] or 0 for r in odd_jindal), 2),
        },
    }


def main():
    delta_rows = delta_parser.parse(DELTA_FILE)
    letterhead, jindal_rows = jindal_parser.parse(JINDAL_FILE)
    if "JINDAL" not in letterhead.upper():
        print(f"WARNING: Jindal file letterhead is '{letterhead}', expected Jindal — check the file.")

    data = compute(delta_rows, jindal_rows)
    print(json.dumps(data["summary"], indent=2))

    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    with open(os.path.join(ROOT, "output", "step1_data.json"), "w") as f:
        json.dump(data, f, indent=2)

    print(f"wrote output/step1_data.json — run recon/render_page.py to build the viewer")


if __name__ == "__main__":
    main()
