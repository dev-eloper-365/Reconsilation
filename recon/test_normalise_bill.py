"""Bill-key normalisation: the typing slips that must collapse, and the
distinctions that must survive. Run: .venv/bin/python recon/test_normalise_bill.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step1 import normalise_bill as n


def test():
    # The pair that started this: Delta's GJ/19-20/2811 and Jindal's
    # GI/1920/2811 are one bill typed two ways.
    assert n("GJ/19-20/2811") == n("GI/1920/2811")

    # Existing slips stay collapsed.
    assert n("GJ/21-22/ 0655") == n("GJ/21-22/0655")
    assert n("GJ/23-24/0534`") == n("GJ/23-24/0534")
    assert n("GJ/23-24-2121") == n("GJ/23-24/2121")
    assert n("GJ/21-22/0629.") == n("GJ/21-22/0629")

    # A four-digit middle segment is not a hyphenated year — leave it alone.
    assert n("GJ/18/2526/1426") == "GJ/18/2526/1426"

    # Different bills stay different.
    assert n("GJ/19-20/2811") != n("GJ/19-20/2812")
    assert n("GJ/19-20/2811") != n("GJ/20-21/2811")

    assert n(None) is None and n("") is None
    print("ok")


if __name__ == "__main__":
    test()
