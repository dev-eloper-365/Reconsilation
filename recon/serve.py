"""Upload-and-reconcile web front end.

Serves recon/upload.html, accepts a Delta ledger export and a Jindal ledger
export, runs the same step1/step2 code the CLI scripts use, and renders the
viewer. Nothing here knows about a particular period or filename — the files
are the only input.

Usage: .venv/bin/python recon/serve.py [port]   (default port 8000)
Standard library only, no extra dependencies.
"""
import base64
import glob
import http.server
import importlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identify as identify_mod
import render_page
import step1
import step2
import step3
import years as years_mod
from parsers import delta as delta_parser
from parsers import jindal as jindal_parser
from parsers import register as register_parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(ROOT, "output", "reconciliation.html")
# The uploads are kept, not thrown away with a temp dir, so the last
# reconciliation can be re-rendered after a code edit without re-uploading.
UPLOAD_DIR = os.path.join(ROOT, "output", ".uploads")

# Identity guard: which company name must appear on each file's letterhead.
# See learnings.md — a file arrived once with the right sheet name and a
# completely different company inside, and produced a silent zero-match.
EXPECTED = {"delta": "DELTA", "jindal": "JINDAL"}

_result = {"html": None}

def _blank_bill_report(rows, invoice_markers):
    """(has invoice-ish rows, any of them carrying a bill number)."""
    invoice_rows = [r for r in rows
                    if any(m in (r.get("vch_type") or "") for m in invoice_markers)]
    return bool(invoice_rows), any(r.get("bill_no") for r in invoice_rows)


def run(uploads):
    """uploads: list of (name, bytes) in whatever order they were given.

    Files are routed by what they actually are — letterhead plus header layout —
    not by which slot they arrived in, because getting that wrong is the single
    easiest mistake to make here. Returns (html, warnings).
    """
    warnings = []
    tmp = UPLOAD_DIR
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    found = {}
    unknown = []
    for name, blob in uploads:
        if not blob:
            continue
        path = os.path.join(tmp, os.path.basename(name) or "upload")
        with open(path, "wb") as f:
            f.write(blob)
        info = identify_mod.identify(path, blob)
        info["path"], info["name"] = path, os.path.basename(name) or "(unnamed)"
        if info["kind"] is None:
            unknown.append(info)
        else:
            found.setdefault(info["kind"], []).append(info)

    for kind, infos in found.items():
        if len(infos) > 1:
            warnings.append(
                f"{len(infos)} files look like the {identify_mod.KIND_LABELS[kind]} "
                f"({', '.join(i['name'] for i in infos)}). They were merged and "
                f"de-duplicated, so overlapping periods are not double-counted."
            )

    for info in unknown:
        warnings.append(
            f"'{info['name']}' was not recognised as any known Tally export "
            f"(letterhead '{info['letterhead'][:60]}'). It was ignored."
        )

    missing = [k for k in ("delta_ledger", "jindal_ledger") if k not in found]
    if missing:
        have = ", ".join(f"'{i['name']}' = {identify_mod.KIND_LABELS[k]}"
                         for k, infos in found.items() for i in infos) or "nothing usable"
        raise ValueError(
            "missing the " + " and the ".join(identify_mod.KIND_LABELS[k] for k in missing)
            + f". What was uploaded: {have}."
        )

    for kind, expect in (("delta_ledger", "DELTA"), ("register", "DELTA"),
                         ("jindal_ledger", "JINDAL")):
        for info in found.get(kind, []):
            # A merged sheet has no letterhead to check — its first row is
            # the header. Absence is not a mismatch.
            if info["letterhead"] and expect not in info["letterhead"].upper():
                warnings.append(
                    f"'{info['name']}' parses as the {identify_mod.KIND_LABELS[kind]} but its "
                    f"letterhead reads '{info['letterhead']}' — expected a {expect.title()} company."
                )

    delta_rows, jindal_rows, register_rows = [], [], []
    register_meta = None
    for info in found["delta_ledger"]:
        delta_rows += delta_parser.parse(info["path"])

    # Jindal keeps one sheet per counterparty, and a group's companies are
    # separate legal entities — never merge them. Pick the sheet matching the
    # Delta company we are actually reconciling, and say what was left out.
    counterparty = next((i["letterhead"] for i in found["delta_ledger"] if i["letterhead"]), None)
    for info in found["jindal_ledger"]:
        chosen, available = jindal_parser.pick_sheet(info["path"], counterparty)
        if len(available) > 1:
            skipped = ", ".join(f"'{sh['name']}' ({sh['rows']} rows)"
                                for sh in available if sh["name"] != chosen)
            warnings.append(
                f"'{info['name']}' holds {len(available)} counterparty ledgers. Read "
                f"'{chosen}' as the match for {counterparty or 'the Delta ledger'}; ignored "
                f"{skipped} — a different company, not part of this reconciliation."
            )
        jindal_rows += jindal_parser.parse(info["path"], sheet_name=chosen)[1]
    for info in found.get("register", []):
        _, rows, meta = register_parser.parse(info["path"])
        register_rows += rows
        if register_meta is None:
            register_meta = dict(meta)
        else:
            # Registers differ year to year — one may carry a TDS ledger the
            # other does not. Merge, so a column present in any year counts.
            merged = dict(register_meta["special_columns"])
            merged.update(meta["special_columns"])
            register_meta = {**register_meta, **meta, "special_columns": merged}

    delta_rows = years_mod.dedupe(delta_rows)
    jindal_rows = years_mod.dedupe(jindal_rows)
    register_rows = years_mod.dedupe(register_rows)

    payload = years_mod.reconcile(delta_rows, jindal_rows, register_rows, register_meta)
    s1 = payload["years"][payload["all_label"]]["step1"]

    if s1["summary"]["matched_count"] == 0:
        # Distinguish "no bill numbers in the file" from "bill numbers that
        # don't overlap" — they need completely different fixes.
        blank = {
            "Delta": _blank_bill_report(delta_rows, ("Imported", "GST")),
            "Jindal": _blank_bill_report(jindal_rows, ("PU",)),
        }
        empty_side = [side for side, (has_rows, has_bills) in blank.items() if has_rows and not has_bills]
        if empty_side:
            warnings.append(
                f"Zero bills matched because the {empty_side[0]} file has no bill numbers at all: "
                f"its purchase/sale rows parsed fine, but every Bill No. cell is empty, so there "
                f"is nothing to match on. Re-export that ledger from Tally with the Bill No. "
                f"column populated. (This is a property of the export, not of the reconciliation.)"
            )
        else:
            warnings.append(
                "Zero bills matched even though both files carry bill numbers — the numbering "
                "does not overlap at all. Check that both exports cover the same counterparty "
                "and the same period."
            )

    s3 = payload["years"][payload["all_label"]]["step3"]
    if s3:
        warnings += [w for w in s3["warnings"] if ": " in w and "spans" not in w][:5]

    period = render_page.period_of(s1["matched"], s1["only_delta"], s1["only_jindal"])
    html = render_page.build(payload, period)

    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    with open(OUT_FILE, "w") as f:
        f.write(html)
    return html, warnings


def _saved_uploads():
    """The files from the last run, read back off disk."""
    return [(os.path.basename(f), open(f, "rb").read())
            for f in sorted(glob.glob(os.path.join(UPLOAD_DIR, "*")))]


def _source_mtime():
    return max(os.path.getmtime(f)
               for f in glob.glob(os.path.join(HERE, "**", "*.py"), recursive=True))


def _reload_source():
    """Re-import the recon modules in place so an edit takes effect without a
    restart. serve.py itself is not reloaded — that one still needs a restart."""
    here = HERE + os.sep
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None) or ""
        if f.startswith(here) and name not in ("__main__", "serve"):
            importlib.reload(mod)


def current_result():
    """(html, rebuild_error). Re-renders the last upload when the code has
    changed since the page was built. A failed rebuild returns the old page:
    a stale result beats no result."""
    if os.path.exists(OUT_FILE) and _source_mtime() > os.path.getmtime(OUT_FILE):
        uploads = _saved_uploads()
        if uploads:
            try:
                _reload_source()
                _result["html"] = run(uploads)[0]
                return _result["html"], None
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                with open(OUT_FILE) as f:
                    return f.read(), error
    if _result["html"] is None and os.path.exists(OUT_FILE):
        with open(OUT_FILE) as f:
            _result["html"] = f.read()
    return _result["html"], None


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "upload.html")) as f:
                self._send(200, f.read())
        elif self.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif self.path == "/result":
            html, error = current_result()
            if html is None:
                self._send(404, "<p>Nothing reconciled yet. Go back to <a href='/'>the upload page</a>.</p>")
            else:
                if error:
                    html = (f"<p style='background:#4a1010;color:#fff;padding:12px;margin:0'>"
                            f"Showing the previous result — rebuilding after the code change "
                            f"failed: {error}</p>") + html
                self._send(200, html)
        else:
            self._send(404, "not found")

    def do_POST(self):
        if self.path != "/run":
            return self._send(404, "not found")
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            # Either {"files": [{name, data}, ...]} or the older fixed slots.
            if payload.get("files"):
                uploads = [(f.get("name", ""), base64.b64decode(f["data"]))
                           for f in payload["files"] if f.get("data")]
            else:
                uploads = [(payload.get(f"{slot}_name", slot), base64.b64decode(payload[slot]))
                           for slot in ("delta", "jindal", "register") if payload.get(slot)]
            html, warnings = run(uploads)
            _result["html"] = html
            self._send(200, json.dumps({"ok": True, "warnings": warnings}), "application/json")
        except Exception as e:  # a bad upload must explain itself, not 500 silently
            self._send(200, json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}),
                       "application/json")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"reconciliation server on http://localhost:{port}  (ctrl-c to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
