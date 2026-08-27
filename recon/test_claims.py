"""Shortage / rate-difference / quality claims: classified on both sides and
paired across voucher types. Run: .venv/bin/python recon/test_claims.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import step2


def delta(date, vch, amount, particulars, bill_no=None):
    return {"date": date, "drcr": "Dr", "particulars": particulars,
            "vch_type": vch, "bill_no": bill_no, "amount": amount}


def jindal(date, vch, amount, particulars):
    return {"date": date, "voucher_no": "X", "vch_type": vch, "particulars": particulars,
            "bill_no": None, "amount": amount, "side": "DR", "sheet": "s"}


def test_payment_transfers():
    """A JV against a "TP/JDI/..." reference is Jindal settling an invoice by
    transfer — money moving, so it belongs with the receipts, not the journals."""
    j = [
        jindal("2022-09-26", "JV", 7190591, "JV LEDGER   \n Ref.No.:  TP/JDI/2223/00481"),
        jindal("2020-03-23", "BP", 577509, "BANK OF INDIA A/C-203530110000023    Ref.No.:"),
        # A plain JV, and one that is 194Q by shipment reference: both stay put.
        jindal("2023-03-31", "JV", 797964, "JV LEDGER   \n Ref.No.:"),
        jindal("2023-03-31", "JV", 1234, "JV LEDGER   Ref.No.:  CF-2223-1"),
    ]
    out = step2.compute([], j)
    assert [r["amount"] for r in out["receipts"]["jindal"]] == [577509, 7190591]
    assert [r["amount"] for r in out["journals"]["jindal"]] == [797964]
    assert [r["amount"] for r in out["tds"]["jindal"]] == [1234]


def test_advances():
    """A row a book calls an advance is money paid, so it joins the receipts —
    and so does the row in the other book that turned out to be its other side,
    which is only knowable from the amount. Both carry the remark."""
    d = [delta("2022-01-31", "Journal", 36495832, "DGPL - Advances", "513"),
         delta("2022-02-28", "Journal", 2202585.24, "Debtors Written Off", "618")]
    j = [jindal("2022-01-31", "JV", 36495832, "JV LEDGER   Ref.No.:"),
         jindal("2022-02-28", "JV", 2202585.24, "JV LEDGER   Ref.No.:")]
    out = step2.compute(d, j)

    advance = [r for r in out["receipts"]["delta"] if r["bill_no"] == "513"]
    assert len(advance) == 1, out["receipts"]["delta"]
    assert advance[0]["advance_kind"] == "Advance payment"
    assert "2022-01-31" in advance[0]["remark"]
    # It moved: the journals tab keeps only the row that is nothing else.
    assert [r["bill_no"] for r in out["journals"]["delta"]] == ["618"]

    # Jindal's half moves to the receipts too, carrying its own remark.
    moved = [r for r in out["receipts"]["jindal"] if r.get("advance_kind")]
    assert len(moved) == 1 and moved[0]["amount"] == 36495832
    assert "journal 513" in moved[0]["remark"], moved[0]["remark"]
    assert not [r for r in out["journals"]["jindal"] if r.get("advance_kind")]

    # The same-amount JV that answers an ordinary journal is left untouched.
    other = [r for r in out["journals"]["jindal"] if r["amount"] == 2202585.24]
    assert len(other) == 1 and not other[0].get("advance_kind")


def test():
    assert step2.adjustment_kind("SHORTAGE A/C   Against Referene No. CF-1920-1865") == "Shortage"
    assert step2.adjustment_kind("RATE DIFFERENCE - SALES") == "Rate difference"
    assert step2.adjustment_kind("Quality Difference - Coal") == "Quality difference"
    assert step2.adjustment_kind("QUALITY CLAIMS   Against Referene No. CF-2021-284") == "Quality difference"
    assert step2.adjustment_kind("Imported Steam Coal@5%") is None
    assert step2.shipment_ref("SHORTAGE A/C Ref.No.:  CF-1920-1865") == "CF-1920-1865"

    d = [
        # Narrated as plain coal — only the amount ties it to Jindal's claim.
        delta("2020-07-31", "CREDIT NOTE ISSUE", 323, "Imported Steam Coal@5%", "DGRPL/20-21/047"),
        # Names the claim itself, but Jindal never raised one.
        delta("2023-03-31", "CREDIT NOTE ISSUE", 47460, "RATE DIFFERENCE - SALES", "DGRPL/22-23/464"),
        # From FY 2022-23 it is Delta that names the claim and Jindal that does
        # not, so the search has to run in both directions.
        delta("2023-03-31", "CREDIT NOTE ISSUE", 20456, "RATE DIFFERENCE - SALES", "DGRPL/22-23/472"),
        # Ordinary trade note: must stay out of the claims tab entirely.
        delta("2023-04-24", "CREDIT NOTE ISSUE", 312436, "Imported Steam Coal@5%", "DGRPL/23-24/007"),
        # Delta writes some claims as journals; they belong in the notes tab
        # beside the credit notes, and are not repeated in the journals tab.
        delta("2025-04-30", "Journal", 18472.79, "SHORTAGE NON GST", "126"),
        # An ordinary journal stays out of the notes tab.
        delta("2022-02-28", "Journal", 2202585.24, "Debtors Written Off", "618"),
    ]
    j = [
        jindal("2020-07-01", "DN", 323, "RATE DIFFERENCE   Ref.No.:  CF-2021-4"),
        jindal("2020-01-31", "DN", 7255, "SHORTAGE A/C   Ref.No.:  CF-1920-1865"),
        jindal("2022-10-18", "DN", 20456, "COAL & FUELS   Ref.No.:  CF-2223-1546"),
        jindal("2021-01-01", "DN", 500, "COAL & FUELS   Ref.No.:  CF-2021-9"),
    ]
    out = step2.compute(list(d), list(j))

    # Claims stay in the tab their voucher type puts them in — the credit and
    # debit notes list — carrying the claim name and the cross-reference.
    notes_d = {r["bill_no"]: r for r in out["notes"]["delta"]}
    notes_j = {r["amount"]: r for r in out["notes"]["jindal"]}
    assert set(notes_d) == {"DGRPL/20-21/047", "DGRPL/22-23/464",
                            "DGRPL/22-23/472", "DGRPL/23-24/007", "126"}, set(notes_d)
    assert notes_d["126"]["adj_kind"] == "Shortage"
    # Listed with the notes and nowhere else — the journals tab keeps only the
    # journals that are nothing but journals.
    assert [r["bill_no"] for r in out["journals"]["delta"]] == ["618"]
    assert out["notes"]["totals"]["delta_credit_journals"] == 18472.79
    assert set(notes_j) == {323, 7255, 20456, 500}, set(notes_j)

    # Delta did not name this one; the kind comes from the Jindal note it answers.
    paired = notes_d["DGRPL/20-21/047"]
    assert paired["adj_kind"] == "Rate difference"
    assert "CF-2021-4" in paired["remark"], paired["remark"]
    assert "DGRPL/20-21/047" in notes_j[323]["remark"]

    # And the other direction: Delta names it, Jindal's note reads "COAL & FUELS".
    assert "CF-2223-1546" in notes_d["DGRPL/22-23/472"]["remark"]
    assert notes_j[20456]["adj_kind"] == "Rate difference"
    assert "DGRPL/22-23/472" in notes_j[20456]["remark"]

    # A one-sided claim says so on the side that raised it.
    assert "no note" in notes_d["DGRPL/22-23/464"]["remark"]
    assert "no note" in notes_j[7255]["remark"]

    # Ordinary trade rows are left alone, not labelled with someone's claim.
    assert notes_d["DGRPL/23-24/007"].get("adj_kind") is None
    assert notes_j[500].get("adj_kind") is None

    # Totals cover every note in the ledger plus the claim journals, and the
    # two sides of the Delta total still add back up to it.
    notes_only = round(sum(r["amount"] for r in d if r["vch_type"] != "Journal"), 2)
    assert out["notes"]["totals"]["delta"] == round(notes_only + 18472.79, 2)
    assert (out["notes"]["totals"]["delta_credit"] + out["notes"]["totals"]["delta_debit"]
            == out["notes"]["totals"]["delta"])
    assert out["notes"]["totals"]["jindal"] == round(sum(r["amount"] for r in j), 2)
    print("ok")


if __name__ == "__main__":
    test_payment_transfers()
    test_advances()
    test()
