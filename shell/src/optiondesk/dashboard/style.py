"""Dashboard stylesheet, kept apart from the markup that uses it."""

STYLE = """
:root {
  --bg: #f6f7f9; --panel: #ffffff; --ink: #14161a; --muted: #666b76;
  --line: #e3e6ea; --accent: #2f6feb; --up: #12a150; --down: #d43a3a;
  --warn-bg: #fff8e6; --warn-line: #b45309; --warn-ink: #7c4a06;
  --grid: rgba(0,0,0,.06);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0c0d10; --panel: #15171b; --ink: #e8eaed; --muted: #939aa6;
    --line: #23262c; --accent: #6ea0ff; --up: #3ddc84; --down: #ff6b6b;
    --warn-bg: #241b0c; --warn-line: #d97706; --warn-ink: #fbbf24;
    --grid: rgba(255,255,255,.07);
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 13.5px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI",
             Roboto, sans-serif; -webkit-font-smoothing: antialiased; }
.wrap { max-width: 1480px; margin: 0 auto; padding: 0 22px 72px; }
header.top { position: sticky; top: 0; z-index: 20; background: var(--bg);
             border-bottom: 1px solid var(--line); padding: 16px 0 12px;
             margin-bottom: 20px; }
.title { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
h1 { font-size: 19px; margin: 0; letter-spacing: -.015em; }
.sym { font-size: 19px; font-weight: 650; color: var(--accent); }
.meta { color: var(--muted); font-size: 12px; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
       background: var(--up); margin-right: 5px; vertical-align: middle; }
.dot.stale { background: var(--warn-line); }
h2.section { font-size: 12px; text-transform: uppercase; letter-spacing: .09em;
             color: var(--muted); margin: 30px 0 12px; font-weight: 650; }
.tiles { display: grid; gap: 9px; margin-bottom: 14px;
         grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); }
.tile { background: var(--panel); border: 1px solid var(--line);
        border-radius: 9px; padding: 10px 12px; }
.tile .k { font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
           color: var(--muted); white-space: nowrap; overflow: hidden;
           text-overflow: ellipsis; }
.tile .v { font-size: 17.5px; margin-top: 2px; font-variant-numeric:
           tabular-nums; letter-spacing: -.02em; }
.tile .s { font-size: 10.5px; color: var(--muted); margin-top: 1px; }
.tile .v.pos { color: var(--up); } .tile .v.neg { color: var(--down); }
.panel { background: var(--panel); border: 1px solid var(--line);
         border-radius: 11px; padding: 14px 16px 10px; margin-bottom: 14px; }
.panel h3 { font-size: 13.5px; margin: 0 0 2px; font-weight: 600; }
.panel p.hint { color: var(--muted); font-size: 11.5px; margin: 0 0 10px;
                max-width: 92ch; }
.chart { width: 100%; height: 320px; }
.chart.tall { height: 400px; }
.chart.short { height: 250px; }
.grid2 { display: grid; gap: 14px;
         grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); }
.grid3 { display: grid; gap: 14px;
         grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); }
.picker { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 13px; }
.picker button { font: inherit; font-size: 12px; cursor: pointer;
                 background: var(--panel); color: var(--ink);
                 border: 1px solid var(--line); border-radius: 7px;
                 padding: 5px 11px; }
.picker button:hover { border-color: var(--accent); }
.picker button[aria-pressed="true"] { background: var(--accent);
                                      border-color: var(--accent);
                                      color: #fff; }
table { border-collapse: collapse; width: 100%; font-size: 12px;
        font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 5px 9px;
         border-bottom: 1px solid var(--line); white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--muted); font-weight: 600; font-size: 10px;
     text-transform: uppercase; letter-spacing: .05em; position: sticky;
     top: 0; background: var(--panel); }
.scroll { overflow: auto; max-height: 420px; }
.badge { display: inline-block; font-size: 10.5px; padding: 1px 8px;
         border-radius: 999px; border: 1px solid var(--line);
         color: var(--muted); }
.badge.ok { color: var(--up); border-color: var(--up); }
.badge.thin, .badge.unknown { color: var(--warn-line);
                              border-color: var(--warn-line); }
.badge.untradeable { color: var(--down); border-color: var(--down); }
.warn { background: var(--warn-bg); border-left: 3px solid var(--warn-line);
        color: var(--warn-ink); padding: 10px 13px; border-radius: 5px;
        margin-bottom: 14px; font-size: 12.5px; }
.notes { color: var(--muted); font-size: 11.5px; margin: 8px 0 0;
         padding-left: 17px; }
.assume { color: var(--muted); font-size: 11.5px; margin: 8px 0 0;
          border-left: 2px solid var(--line); padding-left: 10px;
          max-width: 96ch; }
.selector { display: flex; flex-direction: column; gap: 7px;
            background: var(--panel); border: 1px solid var(--line);
            border-radius: 11px; padding: 12px 14px; margin-bottom: 16px; }
.selector .row { display: flex; align-items: center; gap: 7px;
                 flex-wrap: wrap; }
.selector .lbl { font-size: 10px; text-transform: uppercase;
                 letter-spacing: .07em; color: var(--muted); width: 78px;
                 flex: none; }
.pill { font-size: 12px; text-decoration: none; color: var(--ink);
        background: var(--bg); border: 1px solid var(--line);
        border-radius: 7px; padding: 3px 10px; }
.pill:hover { border-color: var(--accent); }
.pill.on { background: var(--accent); border-color: var(--accent);
           color: #fff; }
tr.lead td { background: rgba(18,161,80,.09); }
tr.lead td:first-child { box-shadow: inset 2px 0 0 var(--up); }
tr.out td { opacity: .5; }
.lead-line { font-size: 12.5px; margin: 0 0 10px; }
.caveat { color: var(--muted); font-size: 11.5px; margin: 10px 0 2px;
          border-left: 2px solid var(--warn-line); padding-left: 10px;
          max-width: 100ch; }
pre.cmds { background: var(--bg); border: 1px solid var(--line);
           border-radius: 7px; padding: 11px 13px; font-size: 11.5px;
           overflow-x: auto; margin: 0 0 8px; line-height: 1.7; }
footer { color: var(--muted); font-size: 11.5px; margin-top: 34px;
         border-top: 1px solid var(--line); padding-top: 13px;
         max-width: 92ch; }
code { background: var(--bg); border: 1px solid var(--line);
       border-radius: 4px; padding: 1px 5px; font-size: 11.5px; }
.empty { color: var(--muted); }
"""
