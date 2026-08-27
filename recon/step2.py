"""Step 2: side-by-side listing (no auto-match — granularity differs too
much between the two ledgers) of Receipts, Journal entries (TDS + other),
and Credit/Debit notes. Writes output/step2_data.json.

Usage: .venv/bin/python recon/step2.py
"""
import collections
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from parsers import delta as delta_parser
from parsers import jindal as jindal_parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DELTA_FILE = os.path.join(ROOT, "data", "Delta 25-16.6.2026.xlsx")
JINDAL_FILE = os.path.join(ROOT, "data", "Jindal 25-16.6.2026.xls")


def is_tds(particulars):
    return particulars is not None and "tds" in particulars.lower()


# Jindal deducts 194Q per shipment, one JV against that shipment's CF-####-NN
# reference. Not all of them say so: in FY 2025-26, 255 of the 582 read only
# "JV LEDGER" with no mention of TDS. Going by the narration alone understated
# Jindal's 194Q by exactly the ₹85,070 that year's difference was made of, so
# the shipment reference is the reliable signal and the narration is not.
CF_REFERENCE = re.compile(r"ref\.no\.:\s*cf-\d{4}-\d+", re.I)


def is_tds_by_reference(particulars):
    return particulars is not None and bool(CF_REFERENCE.search(particulars))


# Jindal settles some invoices by transfer instead of through its bank ledger,
# booking a JV against a "TP/JDI/..." reference. That is money moving, the same
# event as a bank payment — filing it as a journal understates what Jindal paid
# and leaves the receipts comparison with a gap nothing accounts for.
TRANSFER_REFERENCE = re.compile(r"ref\.no\.:\s*tp/", re.I)


def is_payment_transfer(row):
    return bool(TRANSFER_REFERENCE.search(row.get("particulars") or ""))


def is_interest_adjustment(particulars):
    # Jindal JVs referencing "BD/JDI/..." are one-off interest/payment
    # adjustments, not the regular per-shipment "CF-####-NN" referenced JVs.
    return particulars is not None and bool(re.search(r"ref\.no\.:\s*bd", particulars.lower()))


# Claims raised against a shipment rather than against the trade: a weight
# shortage, a price revision, a quality deduction. Jindal raises each one as a
# debit note the day it is settled ("SHORTAGE A/C", "RATE DIFFERENCE", "QUALITY
# CLAIMS", "WEIGHT DIFFERENT", every one against a CF-####-NN shipment). Delta
# books the mirror as a credit note, usually months later at year end and
# usually narrated as plain coal. Naming the claim on both rows, and pointing
# each at the row that answers it, is what turns two unrelated-looking notes
# months apart into one settled claim.
ADJUSTMENT_KINDS = (
    ("Shortage", r"SHORTAGE"),
    ("Rate difference", r"RATE\s*DIFF"),
    ("Quality difference", r"QUALITY"),
    ("Weight difference", r"WEIGHT\s*DIFF"),
)


def adjustment_kind(particulars):
    """Which claim a narration describes, or None if it is ordinary trade."""
    text = (particulars or "").upper()
    for name, pattern in ADJUSTMENT_KINDS:
        if re.search(pattern, text):
            return name
    return None


def is_jindal_tds(row):
    """Jindal's 194Q: it says TDS, or it hangs off a shipment reference."""
    return row["is_tds"] or is_tds_by_reference(row["particulars"])


def shipment_ref(particulars):
    """The CF-####-NN shipment a claim was raised against."""
    match = re.search(r"CF-\d{4}-\d+", particulars or "", re.I)
    return match.group(0).upper() if match else None


SIDE_NAME = {"delta": "Delta", "jindal": "Jindal"}
# Which book the remark is pointing at — reading it the other way round
# inverts who is owed the money.
SIDE_VERB = {"delta": "booked", "jindal": "booked"}


def _label(row, side):
    """How to point at a row in the other book: the reference it carries."""
    if side == "delta":
        what = "journal" if (row.get("vch_type") or "") == "Journal" else "note"
        return (f"{what} {row['bill_no']} on {row['date']}" if row.get("bill_no")
                else f"{what} on {row['date']}")
    ref = shipment_ref(row["particulars"])
    return f"{row['vch_type']} on {row['date']}" + (f" against {ref}" if ref else "")


def _ordinal(date):
    return datetime.date.fromisoformat(date).toordinal() if date else 0


def link_by_amount(candidates, kind_of, tag, noun):
    """Pair the rows one book names with the rows that answer them in the other,
    and write the remark on both. `candidates` is {"delta": rows, "jindal": rows};
    `kind_of(particulars)` names what a row is, or returns None; `tag` is the
    field that name is written to; `noun` is what to call a missing counterpart.

    Only one book usually names the thing. Jindal narrates its debit note
    "SHORTAGE A/C" or "RATE DIFFERENCE" while Delta's answering credit note
    reads "Imported Steam Coal@5%"; from FY 2022-23 it is the other way round,
    Delta writing "RATE DIFFERENCE - SALES" against a Jindal note narrated only
    "COAL & FUELS". So a named row on either side is a starting point, and the
    other book's whole note-and-journal list is searched for its answer.

    Nothing but the amount links the two: the dates are months apart, because
    Jindal books per shipment and Delta at year end. Rows both books named pair
    off first, so a generically narrated note cannot take an amount from the
    row that actually names the claim; ties within a pass go to the nearest
    date. Each row is used once.

    A row already carrying a remark has been paired by an earlier pass and is
    left alone, so two linkers cannot claim the same row.

    Returns {"delta": rows, "jindal": rows}.
    """
    other = {"delta": "jindal", "jindal": "delta"}
    pools = {}
    for side, rows in candidates.items():
        pool = collections.defaultdict(list)
        for row in rows:
            pool[round(row["amount"] or 0, 2)].append(row)
        pools[side] = pool

    named = [(side, row) for side in ("jindal", "delta") for row in candidates[side]
             if kind_of(row["particulars"]) and not row.get("remark")]
    named.sort(key=lambda pair: (pair[1]["date"] or "", -(pair[1]["amount"] or 0)))

    taken, pairs = set(), []
    for same_claim_only in (True, False):
        for side, row in named:
            if id(row) in taken:
                continue
            kind = kind_of(row["particulars"])
            mates = [m for m in pools[other[side]][round(row["amount"] or 0, 2)]
                     if id(m) not in taken and not m.get("remark")
                     and (not same_claim_only or kind_of(m["particulars"]) == kind)]
            if not mates:
                continue
            mate = min(mates, key=lambda m: abs(_ordinal(m["date"]) - _ordinal(row["date"])))
            taken.update((id(row), id(mate)))
            pairs.append((side, row, mate))

    linked = {"delta": [], "jindal": []}
    for side, row, mate in pairs:
        kind = kind_of(row["particulars"])
        mate_kind = kind_of(mate["particulars"]) or kind
        row[tag], mate[tag] = kind, mate_kind
        # When the other book did not name the claim, the remark still points at
        # the row it was matched to — the amount is the only evidence there is.
        row["remark"] = (f"{kind} \u2014 {SIDE_NAME[other[side]]} {SIDE_VERB[other[side]]} "
                         + ("" if mate_kind == kind else f"it as {mate_kind.lower()}, ")
                         + _label(mate, other[side]))
        mate["remark"] = (f"{mate_kind} \u2014 {SIDE_NAME[side]} {SIDE_VERB[side]} "
                          + ("" if mate_kind == kind else f"it as {kind.lower()}, ")
                          + _label(row, side))
        linked[side].append(row)
        linked[other[side]].append(mate)

    for side, row in named:
        if id(row) not in taken:
            row[tag] = kind_of(row["particulars"])
            row["remark"] = (f"{row[tag]} \u2014 {SIDE_NAME[other[side]]} "
                             f"{SIDE_VERB[other[side]]} no {noun} for this amount")
            linked[side].append(row)
    return linked


# Money paid before the goods it covers. Delta writes it into a journal
# ("DGPL - Advances"); Jindal's side of the same transfer is a JV narrated only
# "JV LEDGER", so it is recognisable solely by the amount on the other book's
# row. The named row is a payment and moves to the receipts; the row that only
# matched keeps its place and gains a remark saying what it turned out to be.
def advance_kind(particulars):
    return "Advance payment" if "ADVANCE" in (particulars or "").upper() else None


def _is_debit_note(row):
    return "DEBIT NOTE" in (row.get("vch_type") or "").upper()


def by_amount_desc(rows):
    return sorted(rows, key=lambda r: abs(r["amount"] or 0), reverse=True)


# Money that went back the other way. A payment can fail — a cheque bounces, a
# transfer is rejected — and the bank returns it. Delta books the return as a
# Payment (money leaving Delta), Jindal as a BR (bank receipt, money coming
# back). Counting only the outward leg overstates what was actually collected on
# both sides, so a return is netted off the receipts rather than ignored.
RETURN_TYPES = {"delta": ("Payment",), "jindal": ("BR",)}


def returns_of(rows, kinds):
    return sorted((dict(r) for r in rows if r["vch_type"] in kinds),
                  key=lambda r: r["date"] or "")


def mark_returns(rows, other):
    """A return both books recorded is an agreed reversal. One only this side
    recorded is money this book says came back that the other never booked going
    out — the reason a year's receipts can differ by exactly that amount."""
    unclaimed = collections.Counter(round(r["amount"] or 0, 2) for r in other)
    for row in rows:
        amount = round(row["amount"] or 0, 2)
        agreed = unclaimed[amount] > 0
        unclaimed[amount] -= 1
        row["remark"] = ("Payment returned, netted off receipts — "
                         + ("both books agree" if agreed
                            else "the other side never booked it"))
    return rows


def compute(delta_rows, jindal_rows):
    """Category-wise side-by-side listing -> the step2_data payload."""
    returns_delta = returns_of(delta_rows, RETURN_TYPES["delta"])
    returns_jindal = returns_of(jindal_rows, RETURN_TYPES["jindal"])
    mark_returns(returns_delta, returns_jindal)
    mark_returns(returns_jindal, returns_delta)

    all_journals_delta = [{**r, "is_tds": is_tds(r["particulars"])} for r in delta_rows if r["vch_type"] == "Journal"]
    all_journals_jindal = [{**r, "is_tds": is_tds(r["particulars"])} for r in jindal_rows if r["vch_type"] == "JV"]

    # TDS gets its own listing rather than a flag inside the journals tab: the
    # two books record it at completely different granularity — Delta as a few
    # periodic lump sums, Jindal per invoice — so the only way to compare them
    # is a total against a total.
    tds_delta = by_amount_desc(r for r in all_journals_delta if r["is_tds"])
    tds_jindal = by_amount_desc(r for r in all_journals_jindal if is_jindal_tds(r))
    for row in tds_jindal:
        # Say which signal caught it, so a row classified on the reference alone
        # can be eyeballed rather than taken on trust.
        row["remark"] = ("" if row["is_tds"] else
                         "194Q by shipment reference — narration does not say TDS")

    def plain(rows):
        """Journals that are nothing else: not TDS, not an interest adjustment,
        not a claim. A claim written as a journal is listed with the credit and
        debit notes, beside the note in the other book that answers it; showing
        it here too would read as two separate events."""
        return by_amount_desc(r for r in rows
                              if not r["is_tds"] and not is_jindal_tds(r)
                              and not is_interest_adjustment(r["particulars"])
                              and not is_payment_transfer(r)
                              and not r.get("advance_kind")
                              and not r.get("adj_kind"))

    interest_delta = by_amount_desc(r for r in all_journals_delta if is_interest_adjustment(r["particulars"]))
    interest_jindal = by_amount_desc(r for r in all_journals_jindal if is_interest_adjustment(r["particulars"]))

    all_notes_delta = sorted((r for r in delta_rows if "NOTE" in (r["vch_type"] or "").upper()),
                             key=lambda r: r["date"])
    all_notes_jindal = sorted((r for r in jindal_rows if r["vch_type"] in ("DN", "CN")),
                              key=lambda r: r["date"])

    def claim_candidates(notes, journals):
        """A claim is gathered across voucher types, not within one: Jindal
        raises it as a debit note, Delta answers with a credit note or a
        journal. TDS and interest journals are settlement traffic, and leaving
        them in the pool lets a coincidental amount take a claim's counterpart."""
        return notes + [r for r in journals
                        if not r["is_tds"] and not is_jindal_tds(r)
                        and not is_interest_adjustment(r["particulars"])]

    # Claims are tagged and cross-linked where they lie, not moved: a claim is
    # still a credit note or a journal, and pulling it into a tab of its own
    # made the notes totals disagree with the ledger they came from.
    pool = {"delta": claim_candidates(all_notes_delta, all_journals_delta),
            "jindal": claim_candidates(all_notes_jindal, all_journals_jindal)}
    link_by_amount(pool, adjustment_kind, "adj_kind", "note")
    link_by_amount(pool, advance_kind, "advance_kind", "entry")

    # Delta books some claims as journals rather than credit notes — the
    # "SHORTAGE NON GST" block of FY 2025-26. Same event, same direction, and
    # the counterpart it is compared against is a Jindal debit note, so they are
    # listed with the notes and nowhere else.
    claim_journals_delta = [r for r in all_journals_delta if r.get("adj_kind")]

    # An advance is money paid, so both halves of one belong with the receipts —
    # the row that says "advance" and the row in the other book that turned out
    # to be its other side. Each carries a remark naming the entry it answers.
    # The tag, not the narration, is what selects them: only one book names it.
    advances = lambda rows: [r for r in rows if r.get("advance_kind")]
    receipts_delta = sorted([r for r in delta_rows if r["vch_type"] == "Receipt"]
                            + advances(all_journals_delta), key=lambda r: r["date"])
    receipts_jindal = sorted([r for r in jindal_rows
                              if r["vch_type"] == "BP" or is_payment_transfer(r)]
                             + advances(all_journals_jindal), key=lambda r: r["date"])

    journals_delta = plain(all_journals_delta)
    journals_jindal = plain(all_journals_jindal)
    notes_delta = sorted(all_notes_delta + claim_journals_delta, key=lambda r: r["date"])
    notes_jindal = all_notes_jindal

    def total(rows):
        return round(sum(r["amount"] or 0 for r in rows), 2)

    def totals_for(delta_rows, jindal_rows):
        d, j = total(delta_rows), total(jindal_rows)
        return {"delta": d, "jindal": j, "diff": round(d - j, 2)}

    summary = {
        "receipts_delta": len(receipts_delta),
        "receipts_jindal": len(receipts_jindal),
        "returns_delta": len(returns_delta),
        "returns_jindal": len(returns_jindal),
        "journals_delta": len(journals_delta),
        "journals_jindal": len(journals_jindal),
        "tds_delta": len(tds_delta),
        "tds_jindal": len(tds_jindal),
        "interest_adj_delta": len(interest_delta),
        "interest_adj_jindal": len(interest_jindal),
        "notes_delta": len(notes_delta),
        "notes_jindal": len(notes_jindal),
    }
    return {
            "summary": summary,
            "receipts": {
            "delta": receipts_delta, "jindal": receipts_jindal,
            "returns_delta": returns_delta, "returns_jindal": returns_jindal,
            # Headline totals are net of returns — that is the money that
            # actually stayed. Gross and returned are kept beside them so the
            # netting is visible rather than silently baked in.
            "totals": {
                "delta": round(total(receipts_delta) - total(returns_delta), 2),
                "jindal": round(total(receipts_jindal) - total(returns_jindal), 2),
                "diff": round((total(receipts_delta) - total(returns_delta))
                              - (total(receipts_jindal) - total(returns_jindal)), 2),
                "delta_gross": total(receipts_delta),
                "jindal_gross": total(receipts_jindal),
                "delta_returned": total(returns_delta),
                "jindal_returned": total(returns_jindal),
            }},
            "journals": {"delta": journals_delta, "jindal": journals_jindal, "totals": totals_for(journals_delta, journals_jindal)},
            "tds": {"delta": tds_delta, "jindal": tds_jindal,
                    "totals": totals_for(tds_delta, tds_jindal)},
            "interest_adjustments": {"delta": interest_delta, "jindal": interest_jindal, "totals": totals_for(interest_delta, interest_jindal)},
            "notes": {"delta": notes_delta, "jindal": notes_jindal, "totals": {
                **totals_for(notes_delta, notes_jindal),
                # Note type comes from the voucher type on both sides ("CREDIT NOTE
                # ISSUE" / "DEBIT NOTE ..." in Delta, DN / CN in Jindal). Delta's
                # Dr/Cr column is the ledger side, not the note type.
                "delta_debit": total([r for r in notes_delta if _is_debit_note(r)]),
                # Credit notes plus the claims Delta wrote as journals — both
                # reduce what Jindal owes, so they belong on the same side.
                "delta_credit": total([r for r in notes_delta if not _is_debit_note(r)]),
                "delta_credit_journals": total(claim_journals_delta),
                "jindal_debit": total([r for r in notes_jindal if r["vch_type"] == "DN"]),
                "jindal_credit": total([r for r in notes_jindal if r["vch_type"] == "CN"]),
            }},
    }


def main():
    delta_rows = delta_parser.parse(DELTA_FILE)
    _, jindal_rows = jindal_parser.parse(JINDAL_FILE)

    data = compute(delta_rows, jindal_rows)
    print(json.dumps(data["summary"], indent=2))

    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    with open(os.path.join(ROOT, "output", "step2_data.json"), "w") as f:
        json.dump(data, f, indent=2)
    print("wrote output/step2_data.json")


if __name__ == "__main__":
    main()
