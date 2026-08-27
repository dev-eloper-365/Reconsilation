"""The notes tab's filter and sort logic, exercised as it is written.

The rules live in JavaScript inside render_page.py, so the marked block is
lifted out of that file verbatim and run under node — testing a copy of the
logic would pass while the page stayed broken. Skips if node is absent.

Run: .venv/bin/python recon/test_table_controls.py
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
START = "// --- pure filter/sort logic"
END = "// --- end pure filter/sort logic ---"


def logic():
    with open(os.path.join(HERE, "render_page.py"), encoding="utf-8") as f:
        source = f.read()
    start, end = source.index(START), source.index(END) + len(END)
    return source[start:end]


CHECKS = r"""
const assert = (ok, what) => { if (!ok) { console.error("FAIL: " + what); process.exit(1); } };
const cols = [
  {label: 'Bill', key: 'bill_no', type: 'text'},
  {label: 'Amount', key: 'amount', type: 'num'},
  {label: 'Date', key: 'date', type: 'date'},
  {label: 'Claim', key: 'adj_kind', type: 'enum'},
  {label: 'Shown', get: r => 'x'},                       // display-only, no key
];
const rows = [
  {bill_no: 'DGRPL/22-23/464', amount: 47460, date: '2023-03-31', adj_kind: 'Rate difference'},
  {bill_no: 'DGRPL/20-21/047', amount: 323,   date: '2020-07-31', adj_kind: 'Rate difference'},
  {bill_no: 'DGRPL/23-24/007', amount: 312436, date: '2023-04-24', adj_kind: null},
];
const run = filters => rows.filter(r => keep({columns: cols, filters}, r)).map(r => r.bill_no);

assert(run({}).length === 3, 'no filter keeps every row');
assert(JSON.stringify(run({0: '20-21'})) === '["DGRPL/20-21/047"]', 'text filter matches a substring');
assert(JSON.stringify(run({0: 'dgrpl/20-21'})) === '["DGRPL/20-21/047"]', 'text filter ignores case');
assert(run({3: 'Rate difference'}).length === 2, 'enum filter takes the whole value');
assert(run({3: 'Rate'}).length === 0, 'enum filter is not a substring match');
assert(run({'1:from': '1000'}).length === 2, 'number filter honours a lower bound');
assert(run({'1:from': '1000', '1:to': '100000'}).length === 1, 'number range bounds both ends');
assert(run({'1:to': '9'}).length === 0, 'a bound nothing meets keeps nothing');
assert(run({'2:from': '2023-01-01'}).length === 2, 'date filter compares as a date, not a string');
assert(run({'2:from': '2023-04-01', '2:to': '2023-04-30'}).length === 1, 'date range bounds both ends');
// A row with no claim cannot satisfy a claim filter, and must not crash one.
assert(run({3: 'Quality difference'}).length === 0, 'enum filter excludes empty cells');

const sorted = (i, dir) => rows.slice().sort(compare(cols[i], dir)).map(r => r.amount);
assert(JSON.stringify(sorted(1, 1)) === '[323,47460,312436]', 'numbers sort by value, not by text');
assert(JSON.stringify(sorted(1, -1)) === '[312436,47460,323]', 'descending reverses it');
assert(JSON.stringify(sorted(2, 1)) === '[323,47460,312436]', 'dates sort oldest first');
// Blanks go last in both directions, so a sort never hides them at the top.
const withBlank = rows.concat([{bill_no: 'X', amount: null, date: '', adj_kind: null}]);
assert(withBlank.slice().sort(compare(cols[1], 1)).pop().bill_no === 'X', 'blanks sink ascending');
assert(withBlank.slice().sort(compare(cols[1], -1)).pop().bill_no === 'X', 'blanks sink descending');
console.log("ok");
"""


def main():
    node = shutil.which("node")
    if not node:
        print("skipped — node not installed")
        return
    proc = subprocess.run([node, "--input-type=module", "-e", logic() + CHECKS],
                          capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
