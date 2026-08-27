"""Slice parsed ledgers by financial year and reconcile each year on its own.

The single-period pipeline (step1/step2/step3) is unchanged — this just feeds it
one year's rows at a time, plus an "all years" pass over everything. A file
covering six years and six files covering one year each both end up here in the
same shape.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import closing as closing_mod
import step1
import step2
import step3

ALL = "All years"


def fy_of(date_str):
    """Indian financial year label for an ISO date — April to March."""
    return step3.fy_of(date_str)


def split_by_fy(rows):
    out = {}
    for row in rows:
        if row.get("date"):
            out.setdefault(fy_of(row["date"]), []).append(row)
    return out


def dedupe(rows):
    """Merging overlapping exports must not double-count. Identity is the whole
    visible row, so a genuinely repeated transaction (same day, same voucher,
    same amount) is kept only once."""
    seen, out = set(), []
    for row in rows:
        key = (row.get("date"), row.get("voucher_no"), row.get("bill_no"),
               row.get("vch_type"), row.get("amount"), row.get("particulars"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def reconcile(delta_rows, jindal_rows, register_rows=None, register_meta=None):
    """-> {"order": [fy, ...], "years": {fy: {step1, step2, step3, headline}}}.

    Every year present in either ledger gets an entry, even when one side has
    nothing for it — a year the counterparty never booked is itself a finding.
    """
    delta_by_fy = split_by_fy(delta_rows)
    jindal_by_fy = split_by_fy(jindal_rows)
    register_by_fy = split_by_fy(register_rows or [])

    fys = sorted(set(delta_by_fy) | set(jindal_by_fy))
    years = {}
    for fy in fys + [ALL]:
        d = delta_rows if fy == ALL else delta_by_fy.get(fy, [])
        j = jindal_rows if fy == ALL else jindal_by_fy.get(fy, [])
        r = (register_rows or []) if fy == ALL else register_by_fy.get(fy, [])

        s1 = step1.compute(d, j)
        s2 = step2.compute(d, j)
        s3 = step3.compute(r, register_meta, d) if r else None
        years[fy] = {
            "step1": s1, "step2": s2, "step3": s3,
            "headline": headline(fy, s1, s2, s3, d, j),
        }
    mark_cross_year(years, fys)
    return {"order": fys + [ALL], "years": years, "all_label": ALL,
            "closing": closing_mod.compute(delta_rows, jindal_rows)}


def headline(fy, s1, s2, s3, delta_rows, jindal_rows):
    """The few numbers a year's timeline entry shows before it is expanded."""
    dates = [r["date"] for r in delta_rows + jindal_rows if r.get("date")]
    period = s1["summary"]
    tds = None
    if s3 and s3["periods"]:
        tds = {
            "computed": sum(p["tds_computed"] for p in s3["periods"]),
            "booked": sum(p["tds_booked"] for p in s3["periods"]),
            "base": round(sum(p["net_base"] for p in s3["periods"]), 2),
        }
    return {
        "fy": fy,
        # A file whose period spills a few days into the next year creates a
        # thin year with no invoices in it. Real data, but say so.
        "sparse": period["delta_bill_count"] == 0 and period["jindal_bill_count"] == 0,
        "from": min(dates) if dates else None,
        "to": max(dates) if dates else None,
        "delta_rows": len(delta_rows),
        "jindal_rows": len(jindal_rows),
        "matched": period["matched_count"],
        "mismatched": period["matched_mismatch_count"],
        "only_delta": period["only_delta_count"],
        "only_jindal": period["only_jindal_count"],
        "matched_diff": s1["totals"]["matched"]["diff"],
        "unmatched_diff": s1["totals"]["unmatched"]["diff"],
        "matched_value": s1["totals"]["matched"]["delta"],
        "has_register": s3 is not None,
        "tds": tds,
    }


def _bill_series_fy(bill_no):
    """The financial year written into the invoice number itself — 'GJ/19-20/2863'
    and 'GJ/18/2526/1755' both carry one. Only a pair of consecutive years counts,
    which is what keeps the '1755' in that second number from reading as 17-55."""
    for a, b in re.findall(r"(?<!\d)(\d{2})-?(\d{2})(?!\d)", str(bill_no or "")):
        if int(b) == int(a) + 1:
            return f"20{a}-{b}"
    return None


def mark_cross_year(years, fys):
    """Remark on every unmatched bill that the other side did book — just not in
    this year. Booking a 2019-20 invoice in 2024-25 leaves it unmatched in both
    years' slices while nothing is actually missing, and reading that as a real
    gap is the whole point of this note. Every year is compared against every
    other, not just the neighbouring one: a bill can sit unpaid for years."""
    key = step1.normalise_bill  # the written form differs between the books
    booked_in = {"delta": {}, "jindal": {}}
    for fy in fys:
        s1 = years[fy]["step1"]
        for m in s1["matched"]:
            booked_in["delta"].setdefault(key(m["bill_no"]), []).append(fy)
            booked_in["jindal"].setdefault(key(m["bill_no"]), []).append(fy)
        for row in s1["only_delta"]:
            booked_in["delta"].setdefault(key(row["bill_no"]), []).append(fy)
        for row in s1["only_jindal"]:
            booked_in["jindal"].setdefault(key(row["bill_no"]), []).append(fy)

    for fy in fys:
        s1 = years[fy]["step1"]
        for side, other, who in (("only_delta", "jindal", "Jindal"),
                                 ("only_jindal", "delta", "Delta")):
            for row in s1[side]:
                elsewhere = sorted(f for f in booked_in[other].get(key(row["bill_no"]), [])
                                   if f != fy)
                series_fy = _bill_series_fy(row["bill_no"])
                if elsewhere:
                    row["remark"] = f"Booked by {who} in {', '.join(elsewhere)} ({_gap(fy, elsewhere)})"
                elif series_fy and series_fy != fy:
                    row["remark"] = f"{series_fy} invoice booked in {fy} ({_gap(series_fy, [fy])})"
                else:
                    row["remark"] = ""


def _gap(fy, others):
    """How far apart, in years — the difference between a bill booked next year
    and one still unbooked five years on is the whole reason to look."""
    years_apart = [int(o[:4]) - int(fy[:4]) for o in others]
    n = max(years_apart, key=abs)
    unit = "year" if abs(n) == 1 else "years"
    return f"{abs(n)} {unit} {'later' if n > 0 else 'earlier'}"
