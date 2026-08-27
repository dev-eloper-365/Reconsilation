"""Builds the multi-step reconciliation viewer (output/reconciliation.html)
from output/step1_data.json + output/step2_data.json.

Importable: build(step1, step2, period) returns the HTML as a string, which is
how recon/serve.py renders an uploaded pair without touching disk. Running this
module directly re-reads the JSON files and writes output/reconciliation.html.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(ROOT, "output", "reconciliation.html")

TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>Delta / Jindal Reconciliation</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Work+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --paper:#F0EDE4; --paper-raised:#F8F6EF; --ink:#1E2A22; --muted:#6B6656;
  --rule:#CDC6AE; --accent:#2F6B4F; --accent-soft:#DCEAE1; --bad:#B23A32; --bad-soft:#F3DCD9;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#141812; --paper-raised:#1B211B; --ink:#E7E2D3; --muted:#9A917A;
    --rule:#3A4038; --accent:#57A87E; --accent-soft:#1E3327; --bad:#E3776A; --bad-soft:#3A2320;
  }
}
:root[data-theme="dark"]{
  --paper:#141812; --paper-raised:#1B211B; --ink:#E7E2D3; --muted:#9A917A;
  --rule:#3A4038; --accent:#57A87E; --accent-soft:#1E3327; --bad:#E3776A; --bad-soft:#3A2320;
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"Work Sans",system-ui,sans-serif; font-size:15px;
}
.shell{display:flex; min-height:100vh;}
.rail{
  width:15rem; flex:none; background:var(--paper-raised); border-right:1px solid var(--rule);
  padding:1.75rem 1.25rem; display:flex; flex-direction:column; gap:2rem;
}
.brand{font-family:"Fraunces",serif; font-weight:600; font-size:1.15rem; line-height:1.3; text-wrap:balance;}
.brand small{display:block; font-family:"Work Sans",sans-serif; font-weight:500; font-size:0.72rem; letter-spacing:0.08em; text-transform:uppercase; color:var(--muted); margin-top:0.35rem;}
nav{display:flex; flex-direction:column; gap:0.25rem;}
.step-link{
  display:flex; gap:0.6rem; align-items:baseline; padding:0.55rem 0.6rem; border-radius:6px;
  cursor:pointer; color:var(--muted); border:1px solid transparent;
}
.step-link .n{font-family:"IBM Plex Mono",monospace; font-size:0.78rem;}
.step-link.active{background:var(--accent-soft); color:var(--ink); border-color:var(--rule);}
.step-link.active .n{color:var(--accent);}
.step-link.disabled{opacity:0.45; cursor:default;}
main{flex:1; padding:2.25rem 2.75rem; max-width:76rem;}
h1{font-family:"Fraunces",serif; font-weight:600; font-size:1.6rem; margin:0 0 0.3rem; text-wrap:balance;}
.subtitle{color:var(--muted); margin:0 0 1.75rem; font-size:0.95rem;}
.stats-head{
  display:flex; align-items:center; gap:0.5rem; cursor:pointer; user-select:none;
  margin-bottom:0.75rem; color:var(--muted); font-size:0.78rem; text-transform:uppercase; letter-spacing:0.06em;
}
.stats-head .chev{
  display:inline-block; transition:transform 0.15s ease; font-family:"IBM Plex Mono",monospace; color:var(--accent);
}
.stats-head.collapsed .chev{transform:rotate(-90deg);}
.stats{
  display:flex; gap:0.9rem; flex-wrap:wrap; margin-bottom:1.75rem;
  overflow:hidden; max-height:8rem; transition:max-height 0.2s ease, opacity 0.2s ease, margin 0.2s ease;
}
.stats.collapsed{max-height:0; opacity:0; margin-bottom:0;}
.stat{
  background:var(--paper-raised); border:1px solid var(--rule); border-radius:10px;
  padding:0.75rem 1rem; min-width:7.5rem;
}
.stat b{display:block; font-family:"IBM Plex Mono",monospace; font-size:1.5rem; font-variant-numeric:tabular-nums;}
.stat span{font-size:0.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.06em;}
.stat.warn b{color:var(--bad);}
.tabs{display:flex; gap:0.4rem; margin-bottom:0.9rem; border-bottom:1px solid var(--rule);}
.tab{
  padding:0.5rem 0.9rem; cursor:pointer; color:var(--muted); font-size:0.88rem;
  border-bottom:2px solid transparent; margin-bottom:-1px;
}
.tab.active{color:var(--ink); border-bottom-color:var(--accent); font-weight:500;}
.totalsbar{display:flex; gap:0.6rem; flex-wrap:wrap; margin:0.9rem 0;}
.totalsbar .t{
  background:var(--paper-raised); border:1px solid var(--rule); border-radius:8px;
  padding:0.4rem 0.8rem; font-size:0.8rem; color:var(--muted);
}
.totalsbar .t b{
  font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums; color:var(--ink);
  margin-left:0.35rem;
}
.totalsbar .t.diff b{color:var(--bad);}
.totalsbar .t.diff.zero b{color:var(--accent);}
.totalsbar .t.sub{border-style:dashed;}
h2.sec{font-family:"Fraunces",serif; font-weight:600; font-size:0.95rem; margin:1.5rem 0 0.5rem; color:var(--muted);}
.table-wrap.scroll{max-height:34rem; overflow-y:auto;}
td.metric{color:var(--muted);}
tr.strong td{font-weight:600;}
tr.strong td.metric{color:var(--ink);}
tr.rule-top td{border-top:2px solid var(--rule);}
.checklist{display:flex; flex-direction:column; gap:0.5rem;}
.check{background:var(--paper-raised); border:1px solid var(--rule); border-left:3px solid var(--bad); border-radius:8px; padding:0.6rem 0.9rem; font-size:0.88rem;}
.check.ok{border-left-color:var(--accent);}
.yearbox{display:flex; flex-direction:column; gap:0.35rem; margin-top:-1rem;}
.yearbox span{font-size:0.7rem; text-transform:uppercase; letter-spacing:0.06em; color:var(--muted);}
.yearbox select{
  font:inherit; font-size:0.88rem; padding:0.4rem 0.5rem; color:var(--ink);
  background:var(--paper); border:1px solid var(--rule); border-radius:8px; width:100%;
}
.year-tag{
  font-family:"IBM Plex Mono",monospace; font-size:0.8rem; font-weight:400; color:var(--accent);
  background:var(--accent-soft); border-radius:99px; padding:0.15rem 0.6rem; vertical-align:middle;
}
.timeline{display:flex; flex-direction:column; gap:0.75rem; position:relative;}
.tl{background:var(--paper-raised); border:1px solid var(--rule); border-radius:12px; overflow:hidden;}
.tl.current{border-color:var(--accent);}
.tl.sparse .tl-head{opacity:0.55;}
.tl-head{
  display:grid; grid-template-columns:auto 1fr auto auto auto; gap:1rem; align-items:center;
  padding:0.9rem 1.1rem; cursor:pointer; user-select:none;
}
.tl-head .chev{font-family:"IBM Plex Mono",monospace; color:var(--accent); transition:transform 0.15s ease;}
.tl.open .tl-head .chev{transform:rotate(90deg);}
.tl-fy{font-family:"Fraunces",serif; font-size:1.05rem; font-weight:600;}
.tl-fy small{display:block; font-family:"IBM Plex Mono",monospace; font-size:0.7rem; font-weight:400; color:var(--muted); margin-top:0.15rem;}
.tl-metric{text-align:right;}
.tl-metric b{display:block; font-family:"IBM Plex Mono",monospace; font-size:0.95rem; font-variant-numeric:tabular-nums;}
.tl-metric span{font-size:0.66rem; text-transform:uppercase; letter-spacing:0.06em; color:var(--muted);}
.tl-metric.good b{color:var(--accent);}
.tl-metric.bad b{color:var(--bad);}
.tl-body{display:none; padding:0 1.1rem 1.1rem; border-top:1px solid var(--rule);}
.tl.open .tl-body{display:block;}
.tl-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(9rem,1fr)); gap:0.75rem; margin:1rem 0;}
.tl-open-btn{
  font:inherit; font-size:0.85rem; padding:0.45rem 1rem; cursor:pointer; color:var(--paper-raised);
  background:var(--accent); border:none; border-radius:99px;
}
.tl-note{font-size:0.82rem; color:var(--muted); margin:0.4rem 0 0;}
.variant{font-family:"Work Sans",sans-serif; font-size:0.72rem; color:var(--muted); white-space:normal;}
.pov{display:flex; align-items:center; gap:0.4rem; margin-bottom:0.25rem; order:-1;}
.pov span{font-size:0.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.06em; margin-right:0.2rem;}
.pov button{
  font:inherit; font-size:0.8rem; padding:0.3rem 0.7rem; cursor:pointer; color:var(--muted);
  background:var(--paper-raised); border:1px solid var(--rule); border-radius:99px;
}
.pov button.active{background:var(--accent-soft); color:var(--ink); border-color:var(--accent);}
.split{display:grid; grid-template-columns:1fr 1fr; gap:1.25rem; align-items:start;}
.split-col h2{font-family:"Fraunces",serif; font-weight:600; font-size:0.95rem; margin:0 0 0.5rem; color:var(--muted);}
.table-wrap{overflow-x:auto; border:1px solid var(--rule); border-radius:10px; background:var(--paper-raised);}
table{border-collapse:collapse; width:100%; font-size:0.86rem;}
th,td{padding:0.5rem 0.8rem; text-align:left; border-bottom:1px solid var(--rule); white-space:nowrap;}
th{
  position:sticky; top:0; background:var(--paper-raised); color:var(--muted);
  font-weight:500; text-transform:uppercase; font-size:0.68rem; letter-spacing:0.06em;
}
td.bill,td.num,td.date{font-family:"IBM Plex Mono",monospace;}
td.num{text-align:right; font-variant-numeric:tabular-nums;}
tr:last-child td{border-bottom:none;}
.pill{display:inline-block; padding:0.15rem 0.55rem; border-radius:99px; font-size:0.72rem; font-weight:500;}
.pill.ok{background:var(--accent-soft); color:var(--accent);}
.pill.bad{background:var(--bad-soft); color:var(--bad);}
tr.mismatch{background:var(--bad-soft);}
.empty{padding:2rem; text-align:center; color:var(--muted); font-family:"Fraunces",serif; font-style:italic;}
th.sortable{cursor:pointer; user-select:none;}
th.sortable:hover{color:var(--ink);}
th .arrow{opacity:0.45; font-size:0.7rem;}
th.sorted{color:var(--ink);}
th.sorted .arrow{opacity:1;}
tr.filters th{position:static; padding:0.3rem 0.5rem; background:var(--paper-raised); text-transform:none; letter-spacing:0;}
tr.filters input,tr.filters select{
  width:100%; min-width:5.5rem; box-sizing:border-box; padding:0.25rem 0.4rem;
  font:inherit; font-size:0.75rem; color:var(--ink);
  background:var(--paper); border:1px solid var(--rule); border-radius:6px;
}
tr.filters .range{display:flex; gap:0.25rem;}
.tablebar{
  display:flex; justify-content:space-between; align-items:center; gap:1rem;
  padding:0.4rem 0.8rem; font-size:0.72rem; color:var(--muted);
  border-bottom:1px solid var(--rule);
}
.tablebar button{
  font:inherit; color:var(--muted); background:none;
  border:1px solid var(--rule); border-radius:99px; padding:0.15rem 0.7rem; cursor:pointer;
}
.tablebar button:hover{color:var(--ink);}
.panel{display:none;}
.panel.active{display:block;}
.tab-panel{display:none;}
.tab-panel.active{display:block;}
.split.tab-panel.active{display:grid;}
</style>
</head>
<body>
<div class="shell">
  <aside class="rail">
    <div class="brand">Delta &times; Jindal<small>Ledger reconciliation<br>__PERIOD__</small></div>
    <div class="yearbox">
      <span>Showing</span>
      <select id="yearpick"></select>
    </div>
    <nav id="stepnav">
      <div class="step-link active" data-step="0"><span class="n">&#9679;</span> Timeline</div>
      <div class="step-link" data-step="1"><span class="n">01</span> Bill No. match</div>
      <div class="step-link" data-step="2"><span class="n">02</span> Receipts, journals &amp; notes</div>
      <div class="step-link disabled" data-step="3" id="nav-3"><span class="n">03</span> Base value &amp; 194Q TDS</div>
      <div class="step-link" data-step="4"><span class="n">04</span> Closing position</div>
    </nav>
  </aside>
  <main>
    <div id="panel-0" class="panel active">
      <h1>Timeline</h1>
      <p class="subtitle">One entry per financial year found in the uploaded ledgers. Expand a year to see its position; open it to load that year into Steps 1&ndash;3.</p>
      <div id="timeline" class="timeline"></div>
    </div>
    <div id="panel-1" class="panel">
      <h1>Step 1 &mdash; exact Bill No. match <span class="year-tag year-label"></span></h1>
      <p class="subtitle">Every invoice-bearing row (Bill No. starting <code>GJ/</code>) grouped by bill number on each side, amounts tallied and compared. Bill numbers are matched on a normalised key &mdash; stray spaces and trailing punctuation differ between the two books and would otherwise report the same bill as missing from one side.</p>
      <div class="stats-head" id="s1-stats-head"><span class="chev">&#9662;</span> Summary</div>
      <div class="stats" id="s1-stats"></div>
      <div class="tabgroup">
        <div class="tabs">
          <div class="tab active" data-target="s1-matched">Matched (<span id="cnt-matched"></span>)</div>
          <div class="tab" data-target="s1-unmatched">Unmatched (<span id="cnt-od"></span> Delta / <span id="cnt-oj"></span> Jindal)</div>
        </div>
        <div id="s1-matched" class="tab-panel active">
          <div id="s1-matched-totals" class="totalsbar"></div>
          <div class="pov" id="s1-matched-controls" style="order:0">
            <span>Show</span>
            <button data-mfilter="all" class="active">All bills</button>
            <button data-mfilter="mismatch">Amount mismatches only</button>
            <span style="margin-left:0.8rem">Sort</span>
            <button data-msort="bill" class="active">By bill no.</button>
            <button data-msort="diff">Largest difference first</button>
            <span id="s1-matched-shown" style="margin-left:auto; text-transform:none; letter-spacing:0"></span>
          </div>
          <div id="s1-matched-table" class="table-wrap"></div>
        </div>
        <div id="s1-unmatched" class="split tab-panel">
          <div id="s1-unmatched-totals" class="totalsbar" style="grid-column:1 / -1"></div>
          <div class="split-col">
            <h2>Only in Delta</h2>
            <div id="s1-onlyDelta" class="table-wrap"></div>
          </div>
          <div class="split-col">
            <h2>Only in Jindal</h2>
            <div id="s1-onlyJindal" class="table-wrap"></div>
          </div>
        </div>
      </div>
    </div>
    <div id="panel-2" class="panel">
      <h1>Step 2 &mdash; Receipts, journals &amp; credit/debit notes <span class="year-tag year-label"></span></h1>
      <p class="subtitle">No shared reference number exists between the two ledgers for these types, and row granularity differs (e.g. one Delta receipt often covers many Jindal bank-payment lines) &mdash; listed side by side, sorted by date, for manual cross-check rather than auto-matched.</p>
      <div class="tabgroup">
        <div class="tabs">
          <div class="tab active" data-target="s2-receipts">Receipts (<span id="cnt-rd"></span> / <span id="cnt-rj"></span>)</div>
          <div class="tab" data-target="s2-journals">Journals (<span id="cnt-jd"></span> / <span id="cnt-jj"></span>)</div>
          <div class="tab" data-target="s2-tds">TDS 194Q (<span id="cnt-td"></span> / <span id="cnt-tj"></span>)</div>
          <div class="tab" data-target="s2-interest">Interest adj. (<span id="cnt-id"></span> / <span id="cnt-ij"></span>)</div>
          <div class="tab" data-target="s2-notes">Credit/debit notes (<span id="cnt-nd"></span> / <span id="cnt-nj"></span>)</div>
        </div>
        <div id="s2-receipts" class="split tab-panel active">
          <div id="s2-receipts-totals" class="totalsbar" style="grid-column:1 / -1"></div>
          <div class="split-col"><h2>Delta &mdash; Receipt &amp; advances</h2><div id="s2-receipts-delta" class="table-wrap"></div></div>
          <div class="split-col"><h2>Jindal &mdash; Bank payment (BP), transfer &amp; advances (JV)</h2><div id="s2-receipts-jindal" class="table-wrap"></div></div>
          <div class="split-col" id="s2-returns-delta-col" hidden><h2>Delta &mdash; Payment returned</h2><div id="s2-returns-delta" class="table-wrap"></div></div>
          <div class="split-col" id="s2-returns-jindal-col" hidden><h2>Jindal &mdash; Bank receipt (BR), returned</h2><div id="s2-returns-jindal" class="table-wrap"></div></div>
        </div>
        <div id="s2-journals" class="split tab-panel">
          <div id="s2-journals-totals" class="totalsbar" style="grid-column:1 / -1"></div>
          <div class="split-col"><h2>Delta &mdash; Journal, largest first</h2><div id="s2-journals-delta" class="table-wrap"></div></div>
          <div class="split-col"><h2>Jindal &mdash; JV (Ref. CF-####-NN), largest first</h2><div id="s2-journals-jindal" class="table-wrap"></div></div>
        </div>
        <div id="s2-tds" class="split tab-panel">
          <div id="s2-tds-totals" class="totalsbar" style="grid-column:1 / -1"></div>
          <p class="subtitle" style="grid-column:1 / -1">Section 194Q is deducted by the buyer. Delta books it as a receivable in a few periodic journals; Jindal books it per invoice, one JV per shipment. The two are only comparable as totals &mdash; a row here has no counterpart row on the other side.</p>
          <div class="split-col"><h2>Delta &mdash; 194Q receivable (Journal)</h2><div id="s2-tds-delta" class="table-wrap"></div></div>
          <div class="split-col"><h2>Jindal &mdash; TDS on purchase of goods (JV)</h2><div id="s2-tds-jindal" class="table-wrap"></div></div>
        </div>
        <div id="s2-interest" class="split tab-panel">
          <div id="s2-interest-totals" class="totalsbar" style="grid-column:1 / -1"></div>
          <div class="split-col"><h2>Delta</h2><div id="s2-interest-delta" class="table-wrap"></div></div>
          <div class="split-col"><h2>Jindal &mdash; JV (Ref. BD/&hellip;), interest/payment adjustment</h2><div id="s2-interest-jindal" class="table-wrap"></div></div>
        </div>
        <div id="s2-notes" class="split tab-panel">
          <div id="s2-notes-totals" class="totalsbar" style="grid-column:1 / -1; order:-2"></div>
          <div class="pov" style="grid-column:1 / -1">
            <span>View as</span>
            <button data-pov="jindal" class="active">Jindal's books</button>
            <button data-pov="delta">Delta's books</button>
          </div>
          <div class="split-col pov-a"><h2 id="h-delta-cn"></h2><div id="s2-notes-delta-credit" class="table-wrap"></div></div>
          <div class="split-col pov-a"><h2 id="h-jindal-dn"></h2><div id="s2-notes-jindal-debit" class="table-wrap"></div></div>
          <div class="split-col pov-b"><h2 id="h-delta-dn"></h2><div id="s2-notes-delta-debit" class="table-wrap"></div></div>
          <div class="split-col pov-b"><h2 id="h-jindal-cn"></h2><div id="s2-notes-jindal-credit" class="table-wrap"></div></div>
        </div>
      </div>
    </div>
    <div id="panel-4" class="panel">
      <h1>Closing position</h1>
      <p class="subtitle">What each ledger says the other owes, and a bridge accounting for every rupee between them. Balances are cumulative across the whole span, so year-block opening balances are excluded &mdash; they restate the prior year's closing rather than being movement.</p>
      <div class="stats" id="s4-stats"></div>
      <h2 class="sec">Bridge &mdash; Delta&rsquo;s closing to Jindal&rsquo;s</h2>
      <div id="s4-bridge" class="table-wrap"></div>
      <h2 class="sec">Inside the invoice gap</h2>
      <div id="s4-invoice" class="table-wrap"></div>
      <h2 class="sec">Closing balance at each year end</h2>
      <div id="s4-years" class="table-wrap"></div>
    </div>
    <div id="panel-3" class="panel">
      <h1>Step 3 &mdash; base value &amp; section 194Q TDS <span class="year-tag year-label"></span></h1>
      <p class="subtitle">Taxable value comes from the register's own <code>Value</code> column, not from unwinding the invoice total &mdash; with a flat per-tonne cess the base is not recoverable from the total alone. Every invoice is cross-checked against its own components, its cess against quantity, and its total against the Delta ledger.</p>
      <div class="stats" id="s3-stats"></div>
      <div class="tabgroup">
        <div class="tabs">
          <div class="tab active" data-target="s3-position">TDS position</div>
          <div class="tab" data-target="s3-invoices">Invoices (<span id="cnt-s3i"></span>)</div>
          <div class="tab" data-target="s3-notes">Note adjustments (<span id="cnt-s3n"></span>)</div>
          <div class="tab" data-target="s3-booked">TDS booked (<span id="cnt-s3t"></span>)</div>
          <div class="tab" data-target="s3-checks">Checks (<span id="cnt-s3w"></span>)</div>
        </div>
        <div id="s3-position" class="tab-panel active">
          <div id="s3-position-table" class="table-wrap"></div>
          <h2 class="sec">Invoice value by GST slab</h2>
          <div id="s3-slab-table" class="table-wrap"></div>
        </div>
        <div id="s3-invoices" class="tab-panel"><div id="s3-invoices-table" class="table-wrap scroll"></div></div>
        <div id="s3-notes" class="tab-panel"><div id="s3-notes-table" class="table-wrap"></div></div>
        <div id="s3-booked" class="tab-panel"><div id="s3-booked-table" class="table-wrap"></div></div>
        <div id="s3-checks" class="tab-panel"><div id="s3-checks-body"></div></div>
      </div>
    </div>
  </main>
</div>
<script>
const DATA = __DATA_JSON__;
// Multi-year payload: DATA.years[fy] = {step1, step2, step3, headline}.
// STEP1/2/3 always point at the year currently on screen.
let ACTIVE = DATA.order[0];
let STEP1, STEP2, STEP3, REVERSED;

function fmt(n){ return Number(n).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}); }
// quantities are tonnages, not money — no forced paise
function qty(n){ return Number(n).toLocaleString('en-IN',{maximumFractionDigits:3}); }
// invoice -> the credit note that cancelled it, so an unmatched bill in Step 1
// can say why it is unmatched instead of looking like a missing bill


function renderStats(){
  const s = STEP1.summary;
  const items = [
    [s.delta_bill_count,'Delta bills'],
    [s.jindal_bill_count,'Jindal bills'],
    [s.matched_count,'Matched'],
    [s.matched_exact_count,'Tie out'],
    [s.matched_mismatch_count,'Amount differs', true],
    [s.only_delta_count,'Only in Delta'],
    [s.only_jindal_count,'Only in Jindal'],
    ...(s.bill_variant_count ? [[s.bill_variant_count,'Bill no. typed differently']] : []),
  ];
  document.getElementById('s1-stats').innerHTML = items.map(([v,label,warn]) =>
    `<div class="stat${warn?' warn':''}"><b>${v}</b><span>${label}</span></div>`).join('');
}

// Which matched bills to show, and in what order. Kept outside renderMatched so
// the choice survives switching between years.
let MFILTER = 'all', MSORT = 'bill';

// Bound once, not from renderAll — that runs again on every year switch and
// would stack a fresh listener on each button each time.
function bindMatchedControls(){
  document.querySelectorAll('#s1-matched-controls button').forEach(b =>
    b.addEventListener('click', () => {
      const group = b.dataset.mfilter ? 'mfilter' : 'msort';
      if (group === 'mfilter') MFILTER = b.dataset.mfilter; else MSORT = b.dataset.msort;
      document.querySelectorAll(`#s1-matched-controls button[data-${group}]`)
        .forEach(x => x.classList.toggle('active', x === b));
      renderMatched();
    }));
}

function matchedRows(){
  const rows = MFILTER === 'mismatch'
    ? STEP1.matched.filter(m => m.diff !== 0) : STEP1.matched.slice();
  // Largest difference means largest in size, either direction — a bill Jindal
  // over-booked matters as much as one it under-booked.
  return MSORT === 'diff'
    ? rows.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff)) : rows;
}

function renderMatched(){
  const rows = matchedRows();
  document.getElementById('cnt-matched').textContent = STEP1.matched.length;
  const shown = document.getElementById('s1-matched-shown');
  const net = rows.reduce((t, m) => t + m.diff, 0);
  shown.textContent = rows.length === STEP1.matched.length ? ''
    : `${rows.length} of ${STEP1.matched.length} bills · net ${fmt(net)}`;
  const body = rows.map(m => `
    <tr class="${m.diff !== 0 ? 'mismatch' : ''}">
      <td class="bill">${m.bill_no}${(m.delta_bill_written || m.jindal_bill_written)
        ? `<br><span class="variant">written ${m.delta_bill_written ? 'by Delta' : 'by Jindal'} as “${m.delta_bill_written || m.jindal_bill_written}”</span>` : ''}</td>
      <td>${m.diff === 0 ? '<span class="pill ok">Match</span>' : '<span class="pill bad">Mismatch</span>'}</td>
      <td class="num">${fmt(m.delta_amount)}</td>
      <td class="num">${fmt(m.jindal_amount)}</td>
      <td class="num">${fmt(m.diff)}</td>
      <td class="date">${m.date}</td>
      <td>${m.delta_drcr ?? ''}</td>
      <td>${m.delta_particulars ?? ''}</td>
      <td>${m.delta_vch_type ?? ''}</td>
      <td class="num">${m.delta_row_count}</td>
      <td class="date">${m.jindal_date ?? ''}</td>
      <td class="bill">${m.jindal_voucher_no ?? ''}</td>
      <td>${m.jindal_vch_type ?? ''}</td>
      <td>${m.jindal_particulars ?? ''}</td>
      <td>${m.jindal_side ?? ''}</td>
      <td class="num">${m.jindal_row_count}</td>
    </tr>`).join('');
  document.getElementById('s1-matched-table').innerHTML = `
    <table><thead><tr>
      <th>Bill No.</th><th>Status</th><th>Delta amount</th><th>Jindal amount</th><th>Diff</th>
      <th>Delta date</th><th>Delta Dr/Cr</th><th>Delta particulars</th><th>Delta vch type</th><th>Delta rows</th>
      <th>Jindal date</th><th>Jindal voucher no.</th><th>Jindal vch type</th><th>Jindal particulars</th><th>Jindal side</th><th>Jindal rows</th>
    </tr></thead>
    <tbody>${body}</tbody></table>`;
}

// generic: rows -> table, columns = [{label, get(row), cls, key, type, val}]
// Pass {controls:true} to add sorting and a filter row. `get` returns display
// HTML, so sorting and filtering read `val(row)` — or `row[key]` — instead:
// the number behind a formatted amount, the date behind a date string.
function renderTable(elId, rows, columns, opts){
  const state = {rows, columns, controls: (opts || {}).controls, sort: null, filters: {}};
  TABLES[elId] = state;
  const el = document.getElementById(elId);
  if (!rows.length){ el.innerHTML = `<div class="empty">None.</div>`; return; }
  if (!state.controls){
    el.innerHTML = `<table><thead><tr>${columns.map(c => `<th>${c.label}</th>`).join('')}</tr></thead>
       <tbody>${body(rows, columns)}</tbody></table>`;
    return;
  }
  el.innerHTML = `
    <div class="tablebar"><span class="count"></span><button type="button" data-clear>Clear filters</button></div>
    <table><thead>
      <tr>${columns.map((c, i) => `<th class="sortable" data-sort="${i}">${c.label} <span class="arrow"></span></th>`).join('')}</tr>
      <tr class="filters">${columns.map((c, i) => `<th>${control(c, i, rows)}</th>`).join('')}</tr>
    </thead><tbody></tbody></table>`;
  el.querySelectorAll('th.sortable').forEach(th => th.onclick = () => {
    const i = +th.dataset.sort;
    // third click clears the sort and puts the ledger's own order back
    state.sort = !state.sort || state.sort.col !== i ? {col: i, dir: 1}
               : state.sort.dir === 1 ? {col: i, dir: -1} : null;
    drawRows(elId);
  });
  el.oninput = el.onchange = e => {
    if (!e.target.dataset.filter) return;
    state.filters[e.target.dataset.filter] = e.target.value;
    drawRows(elId);
  };
  el.querySelector('[data-clear]').onclick = () => {
    state.filters = {};
    el.querySelectorAll('[data-filter]').forEach(f => f.value = '');
    drawRows(elId);
  };
  drawRows(elId);
}

const TABLES = {};

// --- pure filter/sort logic (extracted verbatim by recon/test_table_controls.py) ---
const value = (c, r) => c.val ? c.val(r) : (c.key ? r[c.key] : null);
const text = v => (v === null || v === undefined) ? '' : String(v);
const blank = v => v === null || v === undefined || v === '';

// The control matches the field: a picker for a column holding a handful of
// distinct values, a from/to pair for dates and amounts, a substring box for
// prose. A column with no key is display-only and gets nothing.
function control(c, i, rows){
  if (!c.key && !c.val) return '';
  if (c.type === 'enum'){
    const seen = [...new Set(rows.map(r => text(value(c, r))).filter(Boolean))].sort();
    return `<select data-filter="${i}"><option value="">All</option>`
      + seen.map(v => `<option>${v}</option>`).join('') + `</select>`;
  }
  if (c.type === 'num' || c.type === 'date'){
    const t = c.type === 'date' ? 'date' : 'number';
    return `<div class="range">
      <input type="${t}" data-filter="${i}:from" placeholder="from">
      <input type="${t}" data-filter="${i}:to" placeholder="to"></div>`;
  }
  return `<input type="search" data-filter="${i}" placeholder="contains">`;
}

function keep(state, r){
  return state.columns.every((c, i) => {
    const v = value(c, r);
    if (c.type === 'num' || c.type === 'date'){
      const from = state.filters[i + ':from'], to = state.filters[i + ':to'];
      if (!from && !to) return true;
      // a row with nothing in the column cannot satisfy a range
      if (blank(v)) return false;
      const n = c.type === 'num' ? Number(v) : text(v);
      if (from && n < (c.type === 'num' ? Number(from) : from)) return false;
      if (to && n > (c.type === 'num' ? Number(to) : to)) return false;
      return true;
    }
    const want = state.filters[i];
    if (!want) return true;
    if (c.type === 'enum') return text(v) === want;
    return text(v).toLowerCase().includes(want.toLowerCase());
  });
}

// Blanks sink to the bottom either way — a missing value is not a small one.
function compare(c, dir){
  return (a, b) => {
    const x = value(c, a), y = value(c, b);
    if (blank(x) || blank(y)) return blank(x) && blank(y) ? 0 : blank(x) ? 1 : -1;
    return dir * (c.type === 'num' ? Number(x) - Number(y) : text(x).localeCompare(text(y)));
  };
}
// --- end pure filter/sort logic ---

function drawRows(elId){
  const state = TABLES[elId], el = document.getElementById(elId);
  let rows = state.rows.filter(r => keep(state, r));
  if (state.sort) rows = rows.slice().sort(compare(state.columns[state.sort.col], state.sort.dir));
  el.querySelector('tbody').innerHTML = rows.length ? body(rows, state.columns)
    : `<tr><td colspan="${state.columns.length}"><div class="empty">No row matches these filters.</div></td></tr>`;
  el.querySelector('.count').textContent = rows.length === state.rows.length
    ? `${state.rows.length} rows` : `${rows.length} of ${state.rows.length} rows`;
  el.querySelectorAll('th.sortable').forEach((th, i) => {
    const on = state.sort && state.sort.col === i;
    th.classList.toggle('sorted', !!on);
    th.querySelector('.arrow').textContent = on ? (state.sort.dir === 1 ? '\u25b2' : '\u25bc') : '';
  });
}

function body(rows, columns){
  return rows.map(r => `<tr>${columns.map(c => `<td class="${c.cls || ''}">${c.get(r)}</td>`).join('')}</tr>`).join('');
}

const deltaCols = (withCount) => [
  {label: 'Bill/Vch No.', key: 'bill_no', type: 'text', get: r => r.bill_no ?? '', cls: 'bill'},
  {label: 'Amount', key: 'amount', type: 'num', get: r => fmt(r.amount), cls: 'num'},
  {label: 'Date', key: 'date', type: 'date', get: r => r.date, cls: 'date'},
  {label: 'Dr/Cr', key: 'drcr', type: 'enum', get: r => r.drcr ?? ''},
  {label: 'Particulars', key: 'particulars', type: 'text', get: r => r.particulars ?? ''},
  {label: 'Vch type', key: 'vch_type', type: 'enum', get: r => r.vch_type ?? ''},
  ...(withCount ? [{label: 'Rows', key: 'row_count', type: 'num', get: r => r.row_count, cls: 'num'}] : []),
];
const jindalCols = (withCount) => [
  {label: 'Voucher no.', key: 'voucher_no', type: 'text', get: r => r.voucher_no ?? '', cls: 'bill'},
  {label: 'Amount', key: 'amount', type: 'num', get: r => fmt(r.amount), cls: 'num'},
  {label: 'Date', key: 'date', type: 'date', get: r => r.date, cls: 'date'},
  {label: 'Vch type', key: 'vch_type', type: 'enum', get: r => r.vch_type ?? ''},
  {label: 'Particulars', key: 'particulars', type: 'text', get: r => r.particulars ?? ''},
  {label: 'Side', key: 'side', type: 'enum', get: r => r.side ?? ''},
  ...(withCount ? [{label: 'Rows', key: 'row_count', type: 'num', get: r => r.row_count, cls: 'num'}] : []),
];

// generic: totals = {delta, jindal, diff} -> a small stat-pill bar
function renderTotals(elId, totals, extra){
  const zero = totals.diff === 0;
  document.getElementById(elId).innerHTML = `
    <div class="t">Delta total<b>${fmt(totals.delta)}</b></div>
    <div class="t">Jindal total<b>${fmt(totals.jindal)}</b></div>
    <div class="t diff${zero ? ' zero' : ''}">Diff<b>${fmt(totals.diff)}</b></div>`
    + (extra || []).map(([label, v]) => `<div class="t sub">${label}<b>${fmt(v)}</b></div>`).join('');
}

// Shortage, rate difference and quality claims: which claim the row settles,
// and the remark naming the row in the other book that answers it.
const claimCol = {label: 'Claim', key: 'adj_kind', type: 'enum', get: r => r.adj_kind ?? ''};
// An unmatched bill the other side booked in a different year is not missing.
const remarkCol = {label: 'Remark', key: 'remark', type: 'text', get: r => r.remark
  ? `<span class="pill ok">${r.remark}</span>` : ''};

function renderAll(){
  const year = DATA.years[ACTIVE];
  STEP1 = year.step1; STEP2 = year.step2; STEP3 = year.step3;
  REVERSED = Object.fromEntries((STEP3?.reversals ?? [])
    .filter(r => r.invoice_no).map(r => [r.invoice_no, r]));
  document.querySelectorAll('.year-label').forEach(e => e.textContent = ACTIVE);
  renderStats();
  renderMatched();
  renderTotals('s1-matched-totals', STEP1.totals.matched);
  renderTotals('s1-unmatched-totals', STEP1.totals.unmatched);
  document.getElementById('cnt-od').textContent = STEP1.only_delta.length;
  renderTable('s1-onlyDelta', STEP1.only_delta, [...deltaCols(true),
    {label: 'Reversed by', get: r => REVERSED[r.bill_no]
      ? `<span class="pill ok">${REVERSED[r.bill_no].note_no}</span>` : ''},
    remarkCol]);
  document.getElementById('cnt-oj').textContent = STEP1.only_jindal.length;
  renderTable('s1-onlyJindal', STEP1.only_jindal, [
    {label: 'Bill No.', get: r => r.bill_no ?? '', cls: 'bill'},
    ...jindalCols(true),
    remarkCol,
  ]);

  document.getElementById('cnt-rd').textContent = STEP2.receipts.delta.length;
  document.getElementById('cnt-rj').textContent = STEP2.receipts.jindal.length;
  // An advance carries a remark naming the entry the other book made for it.
  renderTable('s2-receipts-delta', STEP2.receipts.delta, [...deltaCols(false), remarkCol], {controls: true});
  renderTable('s2-receipts-jindal', STEP2.receipts.jindal, [...jindalCols(false), remarkCol], {controls: true});
  // A failed payment goes back to the payer. Shown on its own, not mixed into
  // the receipts, so the netting in the totals bar can be read off the page.
  const rd = STEP2.receipts.returns_delta ?? [], rj = STEP2.receipts.returns_jindal ?? [];
  document.getElementById('s2-returns-delta-col').hidden = !rd.length;
  document.getElementById('s2-returns-jindal-col').hidden = !rj.length;
  renderTable('s2-returns-delta', rd, [...deltaCols(false), remarkCol]);
  renderTable('s2-returns-jindal', rj, [...jindalCols(false), remarkCol]);
  const rt = STEP2.receipts.totals;
  renderTotals('s2-receipts-totals', rt, (rd.length || rj.length) ? [
    ['Delta received (gross)', rt.delta_gross],
    ['Delta returned', -rt.delta_returned],
    ['Jindal paid (gross)', rt.jindal_gross],
    ['Jindal returned', -rt.jindal_returned],
  ] : []);

  document.getElementById('cnt-jd').textContent = STEP2.journals.delta.length;
  document.getElementById('cnt-jj').textContent = STEP2.journals.jindal.length;
  renderTable('s2-journals-delta', STEP2.journals.delta, [...deltaCols(false), claimCol, remarkCol]);
  renderTable('s2-journals-jindal', STEP2.journals.jindal, [...jindalCols(false), claimCol, remarkCol]);
  renderTotals('s2-journals-totals', STEP2.journals.totals);

  const tds = STEP2.tds ?? {delta: [], jindal: [], totals: {delta: 0, jindal: 0, diff: 0}};
  document.getElementById('cnt-td').textContent = tds.delta.length;
  document.getElementById('cnt-tj').textContent = tds.jindal.length;
  renderTable('s2-tds-delta', tds.delta, deltaCols(false));
  renderTable('s2-tds-jindal', tds.jindal, [...jindalCols(false), remarkCol]);
  // What Step 3 computes 194Q *should* be, next to what each book actually
  // recorded — the three numbers only mean anything together.
  renderTotals('s2-tds-totals', tds.totals, STEP3 ? [
    ['194Q computed (Step 3)', (STEP3.periods ?? []).reduce((t, p) => t + p.tds_computed, 0)],
  ] : []);

  document.getElementById('cnt-id').textContent = STEP2.interest_adjustments.delta.length;
  document.getElementById('cnt-ij').textContent = STEP2.interest_adjustments.jindal.length;
  renderTable('s2-interest-delta', STEP2.interest_adjustments.delta, deltaCols(false));
  renderTable('s2-interest-jindal', STEP2.interest_adjustments.jindal, jindalCols(false));
  renderTotals('s2-interest-totals', STEP2.interest_adjustments.totals);

  document.getElementById('cnt-nd').textContent = STEP2.notes.delta.length;
  document.getElementById('cnt-nj').textContent = STEP2.notes.jindal.length;
  const isNote = (r, kind) => (r.vch_type || '').toUpperCase().includes(kind + ' NOTE');
  // Delta spells notes out ("CREDIT NOTE ISSUE" / "Dr"); show them as DN/CN + DR/CR
  // so this tab reads the same on both sides.
  // The displayed value is the one to sort and filter on, so the columns that
  // rewrite it for display carry a matching `val`.
  // A claim Delta booked as a journal sits with the credit notes — same
  // direction, same counterpart — and keeps its own voucher type on show.
  const noteType = r => isNote(r, 'DEBIT') ? 'DN' : isNote(r, 'CREDIT') ? 'CN' : (r.vch_type ?? '');
  const noteDeltaCols = deltaCols(false).map(c =>
    c.label === 'Vch type' ? {...c, get: noteType, val: noteType}
    : c.label === 'Dr/Cr' ? {...c, get: r => (r.drcr ?? '').toUpperCase(), val: r => (r.drcr ?? '').toUpperCase()}
    : c);
  const noteCols = [...noteDeltaCols, claimCol, remarkCol];
  const jindalNoteCols = [...jindalCols(false), claimCol, remarkCol];
  const sortable = {controls: true};
  renderTable('s2-notes-delta-debit', STEP2.notes.delta.filter(r => isNote(r, 'DEBIT')), noteCols, sortable);
  renderTable('s2-notes-delta-credit', STEP2.notes.delta.filter(r => !isNote(r, 'DEBIT')), noteCols, sortable);
  renderTable('s2-notes-jindal-debit', STEP2.notes.jindal.filter(r => r.vch_type === 'DN'), jindalNoteCols, sortable);
  renderTable('s2-notes-jindal-credit', STEP2.notes.jindal.filter(r => r.vch_type === 'CN'), jindalNoteCols, sortable);
  // A note issued by one side is booked as its opposite by the other: Delta's
  // credit note is Jindal's debit note, and vice versa. So the table pairings are
  // fixed (pov-a = Delta CN / Jindal DN, pov-b = Delta DN / Jindal CN) and only the
  // debit/credit wording flips between the two views.
  const nt = STEP2.notes.totals;
  function setPov(pov){
    const jin = pov === 'jindal';
    const aSide = jin ? 'Debit' : 'Credit', bSide = jin ? 'Credit' : 'Debit';
    document.getElementById('h-delta-cn').textContent = `Delta \u2014 credit notes & claim journals (${aSide} in ${jin ? "Jindal" : "Delta"}'s books)`;
    document.getElementById('h-jindal-dn').textContent = `Jindal \u2014 debit notes DN (${aSide})`;
    document.getElementById('h-delta-dn').textContent = `Delta \u2014 debit notes (${bSide} in ${jin ? "Jindal" : "Delta"}'s books)`;
    document.getElementById('h-jindal-cn').textContent = `Jindal \u2014 credit notes CN (${bSide})`;
    // debit group always shown first
    document.querySelectorAll('#s2-notes .pov-a').forEach(e => e.style.order = jin ? 0 : 1);
    document.querySelectorAll('#s2-notes .pov-b').forEach(e => e.style.order = jin ? 1 : 0);
    renderTotals('s2-notes-totals', nt, [
      [`${aSide} \u2014 Delta`, nt.delta_credit],
      // Delta's side is not all notes; say how much of it came in as journals.
      ...(nt.delta_credit_journals ? [['\u2026 of which journals', nt.delta_credit_journals]] : []),
      [`${aSide} \u2014 Jindal`, nt.jindal_debit],
      [`${aSide} diff`, nt.delta_credit - nt.jindal_debit],
      [`${bSide} \u2014 Delta`, nt.delta_debit],
      [`${bSide} \u2014 Jindal`, nt.jindal_credit],
      [`${bSide} diff`, nt.delta_debit - nt.jindal_credit],
    ]);
    document.querySelectorAll('#s2-notes .pov button').forEach(b => b.classList.toggle('active', b.dataset.pov === pov));
  }
  document.querySelectorAll('#s2-notes .pov button').forEach(b =>
    b.addEventListener('click', () => setPov(b.dataset.pov)));
  setPov('jindal');

  // ---- Step 3: base value and 194Q TDS. Only rendered when a register was supplied.
  if (STEP3) {
    const s3 = STEP3, P = s3.periods;
  
    document.getElementById('s3-stats').innerHTML = [
      [s3.summary.invoice_count, 'Invoices priced'],
      [qty(P.reduce((a, p) => a + p.quantity, 0)), 'Tonnes'],
      [s3.summary.financial_years.join(' · '), 'Financial years'],
      [s3.summary.tds_entry_count, 'TDS entries booked'],
      [s3.warnings.length, 'Checks to read', s3.warnings.length > 0],
    ].map(([v, label, warn]) => `<div class="stat${warn ? ' warn' : ''}"><b>${v}</b><span>${label}</span></div>`).join('');

    // metrics down the side, one column per financial year — the threshold applies
    // per FY, so the years must never be added together
    const money = v => fmt(v);
    const ROWS = [
      ['Invoices', p => p.invoice_count, 0],
      ['Quantity (MT)', p => qty(p.quantity), 0],
      ['Quantity reversed by notes', p => p.note_quantity ? qty(p.note_quantity) : '—', 0],
      ['Net quantity (MT)', p => qty(p.net_quantity), 0],
      ['Base (taxable) value', p => money(p.base), 1],
      ['Credit / debit note adjustment', p => money(p.note_adjustment), 0],
      ['Net purchase value', p => money(p.net_base), 1],
      ...(P.some(p => p.pre_commencement_base) ? [
        ['Before 194Q commenced (not deductible)', p => money(p.pre_commencement_base), 0],
        ['Deductible purchase value', p => money(p.deductible_base), 0],
      ] : []),
      ['Less: 194Q threshold', p => money(-(p.threshold_applied ?? p.threshold)), 0],
      ['Value liable to TDS', p => money(p.taxable_for_tds), 1],
      ['TDS @ 0.1%', p => money(p.tds_computed), 1],
      ['TDS actually booked', p => money(p.tds_booked), 1],
      ['Difference', p => money(p.diff), 1],
      ['&nbsp;', () => '', 0],
      ['GST charged', p => money(p.gst), 0],
      ['Compensation cess', p => money(p.cess), 0],
      ['Invoice total (gross)', p => money(p.gross), 0],
      ['TDS if notes are not netted off', p => money(p.tds_computed_before_notes), 0],
    ];
    document.getElementById('s3-position-table').innerHTML = `
      <table><thead><tr><th>&nbsp;</th>${P.map(p => `<th>FY ${p.fy}</th>`).join('')}</tr></thead>
      <tbody>${ROWS.map(([label, get, strong], i) => `
        <tr class="${strong ? 'strong' : ''}${label === 'TDS @ 0.1%' ? ' rule-top' : ''}">
          <td class="metric">${label}</td>
          ${P.map(p => `<td class="num">${get(p)}</td>`).join('')}
        </tr>`).join('')}</tbody></table>`;

    const slabRows = P.flatMap(p => Object.entries(p.by_slab).map(([slab, v]) => ({fy: p.fy, slab, ...v})));
    renderTable('s3-slab-table', slabRows, [
      {label: 'FY', get: r => r.fy},
      {label: 'GST slab', get: r => r.slab},
      {label: 'Invoices', get: r => r.count, cls: 'num'},
      {label: 'Quantity (MT)', get: r => qty(r.quantity), cls: 'num'},
      {label: 'Base value', get: r => fmt(r.base), cls: 'num'},
      {label: 'GST', get: r => fmt(r.gst), cls: 'num'},
      {label: 'Notes', get: r => r.note_count || '', cls: 'num'},
      {label: 'Note effect on base', get: r => r.note_base ? fmt(r.note_base) : '', cls: 'num'},
      {label: 'Net base', get: r => fmt(r.net_base), cls: 'num'},
      {label: 'Net qty (MT)', get: r => qty(r.net_quantity), cls: 'num'},
      {label: 'GST', get: r => fmt(r.gst), cls: 'num'},
      {label: 'Cess', get: r => fmt(r.cess), cls: 'num'},
    ]);

    document.getElementById('cnt-s3i').textContent = s3.invoices.length;
    renderTable('s3-invoices-table', s3.invoices, [
      {label: 'Bill no.', get: r => r.bill_no, cls: 'bill'},
      {label: 'Date', get: r => r.date, cls: 'date'},
      {label: 'FY', get: r => r.fy},
      {label: 'Slab', get: r => r.slab},
      {label: 'Qty (MT)', get: r => r.quantity != null ? qty(r.quantity) : '', cls: 'num'},
      {label: 'Rate', get: r => r.rate != null ? fmt(r.rate) : '', cls: 'num'},
      {label: 'Base value', get: r => fmt(r.base), cls: 'num'},
      {label: 'GST', get: r => fmt(r.gst), cls: 'num'},
      {label: 'Cess', get: r => fmt(r.cess), cls: 'num'},
      {label: 'Invoice total', get: r => fmt(r.gross), cls: 'num'},
      {label: 'Reversed by', get: r => r.reversed_by
        ? `<span class="pill bad">${r.reversed_by}</span>` : ''},
    ]);

    document.getElementById('cnt-s3n').textContent = s3.notes.length;
    renderTable('s3-notes-table', s3.notes, [
      {label: 'Note no.', get: r => r.bill_no ?? '', cls: 'bill'},
      {label: 'Date', get: r => r.date, cls: 'date'},
      {label: 'FY', get: r => r.fy},
      {label: 'Kind', get: r => r.kind === 'reversal'
        ? '<span class="pill bad">Goods reversal</span>'
        : '<span class="pill ok">Price adjustment</span>'},
      {label: 'Slab', get: r => r.slab ?? ''},
      {label: 'Acts on', get: r => r.reverses
      ? `${r.reverses}${r.extent === 'partial' ? ' <span class="variant">(part)</span>' : ''}` : '', cls: 'bill'},
      {label: 'Qty netted (MT)', get: r => r.quantity != null ? qty(r.quantity) : '', cls: 'num'},
      {label: 'Qty stated', get: r => r.stated_quantity != null ? qty(r.stated_quantity) : '', cls: 'num'},
      {label: 'Posts to', get: r => (r.against ?? []).join(', ')},
      {label: 'Base effect', get: r => fmt(r.base), cls: 'num'},
      {label: 'GST', get: r => fmt(r.gst), cls: 'num'},
      {label: 'Gross', get: r => fmt(r.gross), cls: 'num'},
    ]);

    document.getElementById('cnt-s3t').textContent = s3.tds_entries.length;
    renderTable('s3-booked-table', s3.tds_entries, [
      {label: 'Date', get: r => r.date, cls: 'date'},
      {label: 'FY', get: r => r.fy},
      {label: 'Voucher no.', get: r => r.voucher_no ?? '', cls: 'bill'},
      {label: 'Vch type', get: r => r.vch_type ?? ''},
      {label: 'Narration', get: r => r.narration ?? ''},
      {label: 'Amount', get: r => fmt(r.amount), cls: 'num'},
    ]);

    const passed = [
      `Invoice components rebuild the invoice total on all ${s3.invoices.length} invoices.`,
      `Compensation cess equals ₹${s3.summary.cess_per_unit} × quantity on every invoice that carries it.`,
      `Every register invoice total ties to the Delta ledger.`,
      `Credit notes are split by what they post to: a note hitting a goods ledger reverses tonnage, one hitting a difference ledger adjusts price only and leaves tonnage alone.`,
    ];
    document.getElementById('cnt-s3w').textContent = s3.warnings.length;
    document.getElementById('s3-checks-body').innerHTML = `<div class="checklist">`
      + passed.map(t => `<div class="check ok">${t}</div>`).join('')
      + s3.warnings.map(w => `<div class="check">${w}</div>`).join('')
      + `</div>`;
  }

  // step 3 is only available for years that had a register
  document.getElementById('nav-3').classList.toggle('disabled', !STEP3);
  if (!STEP3 && document.getElementById('panel-3').classList.contains('active')) showPanel('1');
}
function showPanel(step){
  document.querySelectorAll('.step-link').forEach(l => l.classList.toggle('active', l.dataset.step === String(step)));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + step).classList.add('active');
}

function setYear(fy, panel){
  ACTIVE = fy;
  document.getElementById('yearpick').value = fy;
  renderAll();
  renderTimeline();
  if (panel !== undefined) showPanel(panel);
}

const BUCKET_LABEL = {
  invoices: 'Invoices', notes: 'Credit / debit notes',
  payments: 'Receipts, payments & journals', other: 'Other',
};

function renderClosing(){
  const c = DATA.closing;
  if (!c) return;
  const o = c.overall, owed = o.delta_closing >= 0;
  document.getElementById('s4-stats').innerHTML = [
    [fmt(o.delta_closing), "Delta says Jindal owes"],
    [fmt(o.jindal_closing), "Jindal says it owes"],
    [fmt(o.difference), 'Unreconciled difference', o.difference !== 0],
  ].map(([v, label, warn]) => `<div class="stat${warn ? ' warn' : ''}"><b>${v}</b><span>${label}</span></div>`).join('');

  const rows = o.bridge.filter(b => b.delta_count || b.jindal_count);
  document.getElementById('s4-bridge').innerHTML = `
    <table><thead><tr><th>Bucket</th><th>Delta booked</th><th>Rows</th><th>Jindal booked</th><th>Rows</th><th>Gap</th></tr></thead>
    <tbody>
      <tr class="strong"><td class="metric">Delta&rsquo;s closing balance</td><td class="num">${fmt(o.delta_closing)}</td><td colspan="4"></td></tr>
      ${rows.map(b => `<tr>
        <td class="metric">${BUCKET_LABEL[b.bucket] ?? b.bucket}</td>
        <td class="num">${fmt(b.delta)}</td><td class="num">${b.delta_count}</td>
        <td class="num">${fmt(b.jindal)}</td><td class="num">${b.jindal_count}</td>
        <td class="num">${fmt(b.difference)}</td></tr>`).join('')}
      <tr class="strong rule-top"><td class="metric">Sum of gaps</td><td colspan="4"></td>
        <td class="num">${fmt(rows.reduce((a, b) => a + b.difference, 0))}</td></tr>
      <tr class="strong"><td class="metric">Jindal&rsquo;s closing balance</td><td colspan="4"></td><td class="num">${fmt(o.jindal_closing)}</td></tr>
    </tbody></table>`;

  const d = o.invoice_detail;
  const lines = [
    ['Bills Delta raised that Jindal has not booked', d.only_delta, d.only_delta_count, 'Jindal to book'],
    ['Bills Jindal booked that Delta has not raised', -d.only_jindal, d.only_jindal_count, 'Delta to book, or Jindal to reverse'],
    ['Amount differs on a bill both booked', d.mismatch, d.mismatch_count, 'Agree the correct value'],
    ['Delta bills with a reference outside the invoice series', d.unrecognised_delta, d.unrecognised_delta_count, 'Correct the reference'],
    ['Jindal bills with a reference outside the invoice series', -d.unrecognised_jindal, d.unrecognised_jindal_count, 'Correct the reference'],
  ].filter(l => l[2]);
  document.getElementById('s4-invoice').innerHTML = `
    <table><thead><tr><th>Cause</th><th>Effect on the gap</th><th>Bills</th><th>Who acts</th></tr></thead>
    <tbody>${lines.map(([label, amt, n, who]) => `<tr>
      <td class="metric">${label}</td><td class="num">${fmt(amt)}</td><td class="num">${n}</td><td>${who}</td></tr>`).join('')}
      <tr class="strong rule-top"><td class="metric">Invoice gap</td><td class="num">${fmt(d.subtotal)}</td><td colspan="2"></td></tr>
    </tbody></table>`;

  renderTable('s4-years', c.periods, [
    {label: 'FY', get: r => r.fy},
    {label: 'Delta movement', get: r => fmt(r.delta_movement), cls: 'num'},
    {label: 'Jindal movement', get: r => fmt(r.jindal_movement), cls: 'num'},
    {label: 'Delta closing', get: r => fmt(r.delta_closing), cls: 'num'},
    {label: 'Jindal closing', get: r => fmt(r.jindal_closing), cls: 'num'},
    {label: 'Difference', get: r => fmt(r.difference), cls: 'num'},
  ]);
}

function renderTimeline(){
  document.getElementById('timeline').innerHTML = DATA.order.map(fy => {
    const h = DATA.years[fy].headline, tds = h.tds;
    const clean = h.matched_diff === 0 && h.only_jindal === 0 && h.mismatched === 0;
    return `
    <div class="tl${fy === ACTIVE ? ' current' : ''}${h.sparse ? ' sparse' : ''}" data-fy="${fy}">
      <div class="tl-head">
        <span class="chev">&#9656;</span>
        <span class="tl-fy">${fy}<small>${h.from ?? '—'} to ${h.to ?? '—'}</small></span>
        <span class="tl-metric"><b>${h.matched}</b><span>Matched</span></span>
        <span class="tl-metric ${h.matched_diff === 0 ? 'good' : 'bad'}"><b>${fmt(h.matched_diff)}</b><span>Matched diff</span></span>
        <span class="tl-metric ${clean ? 'good' : 'bad'}"><b>${h.only_delta + h.only_jindal}</b><span>Unmatched</span></span>
      </div>
      <div class="tl-body">
        <div class="tl-grid">
          <div class="stat"><b>${fmt(h.matched_value)}</b><span>Matched value</span></div>
          <div class="stat"><b>${h.mismatched}</b><span>Amount differs</span></div>
          <div class="stat"><b>${h.only_delta}</b><span>Only in Delta</span></div>
          <div class="stat"><b>${h.only_jindal}</b><span>Only in Jindal</span></div>
          <div class="stat"><b>${fmt(h.unmatched_diff)}</b><span>Unmatched diff</span></div>
          ${tds ? `<div class="stat"><b>${fmt(tds.computed)}</b><span>194Q computed</span></div>
                   <div class="stat"><b>${fmt(tds.booked)}</b><span>TDS booked</span></div>
                   <div class="stat${tds.computed - tds.booked ? ' warn' : ''}"><b>${fmt(tds.booked - tds.computed)}</b><span>TDS difference</span></div>` : ''}
        </div>
        ${h.sparse ? '<p class="tl-note">No invoices in this financial year &mdash; these rows are the tail of an export whose period runs a few days past the year end.</p>' : ''}
        ${h.has_register ? '' : '<p class="tl-note">No register uploaded for this year, so Step 3 (base value and 194Q TDS) is unavailable.</p>'}
        <p class="tl-note">${h.delta_rows} Delta rows &middot; ${h.jindal_rows} Jindal rows.</p>
        <button class="tl-open-btn" data-open="${fy}">Open ${fy} in Steps 1&ndash;3 &rarr;</button>
      </div>
    </div>`;
  }).join('');

  document.querySelectorAll('#timeline .tl-head').forEach(head => {
    head.addEventListener('click', () => head.parentElement.classList.toggle('open'));
  });
  document.querySelectorAll('#timeline .tl-open-btn').forEach(btn => {
    btn.addEventListener('click', e => { e.stopPropagation(); setYear(btn.dataset.open, 1); });
  });
  const cur = document.querySelector(`#timeline .tl[data-fy="${ACTIVE}"]`);
  if (cur) cur.classList.add('open');
}

document.getElementById('yearpick').innerHTML =
  DATA.order.map(fy => `<option value="${fy}">${fy}</option>`).join('');
document.getElementById('yearpick').addEventListener('change', e => setYear(e.target.value));

renderClosing();
bindMatchedControls();
setYear(DATA.order[0], 0);

document.querySelectorAll('.tabgroup').forEach(group => {
  group.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      group.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      group.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === tab.dataset.target));
    });
  });
});

document.getElementById('s1-stats-head').addEventListener('click', () => {
  document.getElementById('s1-stats-head').classList.toggle('collapsed');
  document.getElementById('s1-stats').classList.toggle('collapsed');
});

document.querySelectorAll('.step-link').forEach(link => {
  link.addEventListener('click', () => {
    if (link.classList.contains('disabled')) return;
    showPanel(link.dataset.step);
  });
});
</script>
</body></html>
"""



def period_of(*row_lists):
    """Reporting period label from the data itself, so nothing is hardcoded to
    one export's date range."""
    dates = sorted(r["date"] for rows in row_lists for r in rows if r.get("date"))
    return f"{dates[0]} to {dates[-1]}" if dates else ""


def build(payload, period=""):
    """payload: {"order": [fy, ...], "years": {fy: {step1, step2, step3, headline}}}
    as produced by years.reconcile()."""
    return (TEMPLATE
            .replace("__DATA_JSON__", json.dumps(payload))
            .replace("__PERIOD__", period))


def main():
    """CLI path: render whatever the step scripts last wrote, as a single
    period. The server path builds a real multi-year payload instead."""
    with open(os.path.join(ROOT, "output", "step1_data.json")) as f:
        step1 = json.load(f)
    with open(os.path.join(ROOT, "output", "step2_data.json")) as f:
        step2 = json.load(f)
    step3 = None
    step3_path = os.path.join(ROOT, "output", "step3_data.json")
    if os.path.exists(step3_path):
        with open(step3_path) as f:
            step3 = json.load(f)
    period = period_of(step1["matched"], step1["only_delta"], step1["only_jindal"])
    label = period or "All years"
    payload = {"order": [label], "all_label": label, "years": {label: {
        "step1": step1, "step2": step2, "step3": step3,
        "headline": {"fy": label, "from": None, "to": None,
                     "delta_rows": 0, "jindal_rows": 0,
                     "matched": step1["summary"]["matched_count"],
                     "mismatched": step1["summary"]["matched_mismatch_count"],
                     "only_delta": step1["summary"]["only_delta_count"],
                     "only_jindal": step1["summary"]["only_jindal_count"],
                     "matched_diff": step1["totals"]["matched"]["diff"],
                     "unmatched_diff": step1["totals"]["unmatched"]["diff"],
                     "matched_value": step1["totals"]["matched"]["delta"],
                     "has_register": step3 is not None, "tds": None}}}}
    with open(OUT_FILE, "w") as f:
        f.write(build(payload, period))
    print(f"wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
