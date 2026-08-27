"""Closing balance position: what each ledger says the other owes, and a bridge
that accounts for every rupee of the difference.

Both ledgers are cumulative, so the closing balance is the running total of all
movement. Two rules matter:

- **Opening-balance rows are not movement.** A multi-year export restates the
  prior year's closing at the top of each year block; adding those double-counts
  (₹3.88 crore in the 2019-2026 Delta export).
- **Each side signs its own way.** Delta's ledger is the customer account, so a
  `Cr`-flagged row increases what Jindal owes; Jindal's is the supplier account,
  so a `CR` row increases what it owes Delta. Both closings are then positive
  when Jindal owes Delta.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import step1
import step3

BUCKETS = ("invoices", "notes", "payments", "other")


def is_opening(row):
    return "opening balance" in (row.get("particulars") or "").lower()


def delta_signed(row):
    return (row["amount"] or 0) * (1 if row["drcr"] == "Cr" else -1)


def jindal_signed(row):
    return (row["amount"] or 0) * (1 if row["side"] == "CR" else -1)


def delta_bucket(row):
    vch = (row.get("vch_type") or "").upper()
    if (step1.normalise_bill(row.get("bill_no")) or "").startswith(step1.INVOICE_PREFIX):
        return "invoices"
    if "NOTE" in vch:
        return "notes"
    # Receipts, journals and direct payments are all settlement traffic; the two
    # books split them differently (Jindal posts TDS and payments as JV), so they
    # only reconcile when compared as one group.
    if vch in ("RECEIPT", "JOURNAL", "PAYMENT", "CONTRA"):
        return "payments"
    return "other"


def jindal_bucket(row):
    vch = (row.get("vch_type") or "").upper()
    if vch == "PU":
        return "invoices"
    if vch in ("DN", "CN"):
        return "notes"
    if vch in ("BP", "BR", "JV"):
        return "payments"
    return "other"


def _totals(rows, sign, bucket):
    out = {b: {"amount": 0.0, "count": 0} for b in BUCKETS}
    for row in rows:
        b = bucket(row)
        out[b]["amount"] += sign(row)
        out[b]["count"] += 1
    for b in out:
        out[b]["amount"] = round(out[b]["amount"], 2)
    return out


def compute(delta_rows, jindal_rows):
    delta_rows = [r for r in delta_rows if not is_opening(r) and r.get("date")]
    jindal_rows = [r for r in jindal_rows if not is_opening(r) and r.get("date")]

    fys = sorted({step3.fy_of(r["date"]) for r in delta_rows + jindal_rows})
    periods, d_run, j_run = [], 0.0, 0.0
    for fy in fys:
        d_year = [r for r in delta_rows if step3.fy_of(r["date"]) == fy]
        j_year = [r for r in jindal_rows if step3.fy_of(r["date"]) == fy]
        d_move = round(sum(delta_signed(r) for r in d_year), 2)
        j_move = round(sum(jindal_signed(r) for r in j_year), 2)
        d_run, j_run = round(d_run + d_move, 2), round(j_run + j_move, 2)
        periods.append({
            "fy": fy,
            "delta_movement": d_move, "jindal_movement": j_move,
            "delta_closing": d_run, "jindal_closing": j_run,
            "difference": round(d_run - j_run, 2),
            "bridge": bridge(d_year, j_year),
        })

    overall = {
        "delta_closing": round(sum(delta_signed(r) for r in delta_rows), 2),
        "jindal_closing": round(sum(jindal_signed(r) for r in jindal_rows), 2),
        "bridge": bridge(delta_rows, jindal_rows),
        "invoice_detail": invoice_detail(delta_rows, jindal_rows),
        "from": min(r["date"] for r in delta_rows + jindal_rows),
        "to": max(r["date"] for r in delta_rows + jindal_rows),
    }
    overall["difference"] = round(overall["delta_closing"] - overall["jindal_closing"], 2)
    return {"periods": periods, "overall": overall}


def bridge(delta_rows, jindal_rows):
    """Per bucket: what each side booked, and the gap. The gaps sum to the
    difference between the two closing balances, exactly."""
    d = _totals(delta_rows, delta_signed, delta_bucket)
    j = _totals(jindal_rows, jindal_signed, jindal_bucket)
    return [{
        "bucket": b,
        "delta": d[b]["amount"], "delta_count": d[b]["count"],
        "jindal": j[b]["amount"], "jindal_count": j[b]["count"],
        "difference": round(d[b]["amount"] - j[b]["amount"], 2),
    } for b in BUCKETS]


def invoice_detail(delta_rows, jindal_rows):
    """Split the invoice gap into the three things that cause it."""
    s1 = step1.compute(delta_rows, jindal_rows)
    only_delta = round(sum(r["amount"] for r in s1["only_delta"]), 2)
    only_jindal = round(sum(r["amount"] for r in s1["only_jindal"]), 2)
    mismatch = round(sum(m["diff"] for m in s1["matched"]), 2)
    odd_d = s1["unrecognised"]["delta_total"]
    odd_j = s1["unrecognised"]["jindal_total"]
    return {
        "only_delta": only_delta, "only_delta_count": len(s1["only_delta"]),
        "only_jindal": only_jindal, "only_jindal_count": len(s1["only_jindal"]),
        "mismatch": mismatch, "mismatch_count": s1["summary"]["matched_mismatch_count"],
        # bills carrying a reference that isn't in the invoice series at all
        "unrecognised_delta": odd_d, "unrecognised_delta_count": len(s1["unrecognised"]["delta"]),
        "unrecognised_jindal": odd_j, "unrecognised_jindal_count": len(s1["unrecognised"]["jindal"]),
        "subtotal": round(only_delta - only_jindal + mismatch + odd_d - odd_j, 2),
    }
