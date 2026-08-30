"""The dashboard's client-side chart code.

Apache ECharts, served from a vendored copy, driven by one JSON blob the
server embeds. Kept as a Python string in its own module so the markup
module stays readable.

Conventions, held across every panel so a reader learns them once: spot is a
dotted grey line, breakevens are dashed amber, the expected move is a shaded
band, profit is green and loss is red measured from zero, and reference-line
labels alternate between the top and bottom of the plot so they never
collide.
"""

SCRIPT = r"""
const D = window.__OPTIONDESK__;
const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const ink = dark ? '#e8eaed' : '#14161a';
const muted = dark ? '#939aa6' : '#666b76';
const line = dark ? '#23262c' : '#e3e6ea';
const grid = dark ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.06)';
const panel = dark ? '#15171b' : '#ffffff';
const UP = dark ? '#3ddc84' : '#12a150';
const DOWN = dark ? '#ff6b6b' : '#d43a3a';
const CALL = dark ? '#6ea0ff' : '#2f6feb';
const PUT = dark ? '#ffa94d' : '#c2670c';
const AMBER = dark ? '#fbbf24' : '#b45309';

const registry = {};
function mount(id, option) {
  const el = document.getElementById(id);
  if (!el) return null;
  const existing = echarts.getInstanceByDom(el);
  if (existing) existing.dispose();
  const chart = echarts.init(el, null, { renderer: 'canvas' });
  chart.setOption(option);
  registry[id] = chart;
  return chart;
}
window.addEventListener('resize', () => {
  Object.values(registry).forEach(c => { if (c && !c.isDisposed()) c.resize(); });
});

const axis = {
  axisLine: { lineStyle: { color: line } },
  axisTick: { show: false },
  axisLabel: { color: muted, fontSize: 10.5 },
  splitLine: { lineStyle: { color: grid } },
  nameTextStyle: { color: muted, fontSize: 10.5 },
  nameLocation: 'middle'
};
function xAxis(name, extra) {
  return Object.assign({}, axis, { type: 'value', name: name, nameGap: 26,
    scale: true, min: 'dataMin', max: 'dataMax' }, extra || {});
}
function yAxis(name, extra) {
  return Object.assign({}, axis, { type: 'value', name: name, nameGap: 46,
    scale: true }, extra || {});
}
function zoomWindow(fraction) {
  // Explicit values, not percentages. Percentages are resolved against an
  // extent that is not always the one you think, and the first version of
  // this put the initial view on empty strikes six hundred points above
  // spot. Values cannot be misread.
  const half = D.spot ? D.spot * fraction : null;
  return half ? { startValue: D.spot - half, endValue: D.spot + half } : {};
}

function zoom(fraction) {
  const w = zoomWindow(fraction === undefined ? 0.12 : fraction);
  return [
    Object.assign({ type: 'inside', xAxisIndex: 0 }, w),
    Object.assign({
      type: 'slider', xAxisIndex: 0, height: 16, bottom: 6,
      borderColor: line, backgroundColor: 'transparent',
      fillerColor: dark ? 'rgba(110,160,255,.10)' : 'rgba(47,111,235,.08)',
      handleStyle: { color: muted }, moveHandleSize: 4,
      textStyle: { color: muted, fontSize: 9 },
      dataBackground: { lineStyle: { color: line },
        areaStyle: { color: grid } }
    }, w)
  ];
}

function frame(extra) {
  return Object.assign({
    backgroundColor: 'transparent',
    animationDuration: 320,
    textStyle: { color: ink, fontFamily: 'ui-sans-serif, system-ui, sans-serif' },
    grid: { left: 68, right: 24, top: 30, bottom: 62, containLabel: false },
    tooltip: { trigger: 'axis', backgroundColor: panel, borderColor: line,
      borderWidth: 1, textStyle: { color: ink, fontSize: 11.5 },
      axisPointer: { type: 'cross', label: { backgroundColor: muted,
        color: dark ? '#000' : '#fff' } } },
    legend: { top: 0, right: 0, textStyle: { color: muted, fontSize: 10.5 },
      itemWidth: 13, itemHeight: 7, icon: 'roundRect' }
  }, extra || {});
}

// Reference lines alternate between top and bottom so their labels cannot
// overlap, which is what made the first version of this dashboard unreadable
// wherever spot sat between two breakevens.
function refLines(marks) {
  return {
    symbol: 'none', silent: true,
    data: marks.map(function (m, i) {
      return {
        xAxis: m.x,
        lineStyle: { color: m.color || muted, type: m.type || 'dotted',
                     width: 1.3 },
        label: { formatter: m.label, color: m.color || muted, fontSize: 10,
                 position: i % 2 === 0 ? 'insideEndTop' : 'insideStartBottom',
                 distance: 3 }
      };
    })
  };
}

function fmt(v, d) {
  if (v === null || v === undefined) return 'n/a';
  if (typeof v === 'string') return v;
  return v.toFixed(d === undefined ? 2 : d);
}
function compact(v) {
  if (v === null || v === undefined) return 'n/a';
  const abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toFixed(2) + 'bn';
  if (abs >= 1e6) return (v / 1e6).toFixed(1) + 'm';
  if (abs >= 1e3) return (v / 1e3).toFixed(1) + 'k';
  return v.toFixed(2);
}

/* ---------------------------------------------------------------- payoff */

function splitSign(data) {
  const pos = [], neg = [];
  for (let i = 0; i < data.length; i++) {
    const x = data[i][0], y = data[i][1];
    pos.push([x, y >= 0 ? y : null]);
    neg.push([x, y <= 0 ? y : null]);
    if (i + 1 < data.length) {
      const x2 = data[i + 1][0], y2 = data[i + 1][1];
      if ((y > 0 && y2 < 0) || (y < 0 && y2 > 0)) {
        const cross = x + (0 - y) * (x2 - x) / (y2 - y);
        pos.push([cross, 0]); neg.push([cross, 0]);
      }
    }
  }
  return { pos: pos, neg: neg };
}

function payoffChart(plan) {
  if (!plan) return;
  const curve = plan.payoff_curve;
  const data = curve.prices.map((p, i) => [p, curve.pnl[i]]);
  const split = splitSign(data);
  const marks = [{ x: plan.spot, label: 'spot ' + fmt(plan.spot), type: 'dotted' }];
  (plan.analysis.breakevens || []).forEach(function (be) {
    marks.push({ x: be, label: 'be ' + fmt(be), type: 'dashed', color: AMBER });
  });

  mount('payoff', frame({
    legend: { show: false },
    grid: { left: 74, right: 26, top: 22, bottom: 48 },
    xAxis: xAxis('underlying at expiry'),
    yAxis: yAxis('profit and loss'),
    tooltip: { trigger: 'axis', backgroundColor: panel, borderColor: line,
      textStyle: { color: ink, fontSize: 11.5 },
      formatter: function (ps) {
        const p = ps.find(z => z.data && z.data[1] !== null);
        if (!p) return '';
        return 'underlying ' + fmt(p.data[0]) + '<br/>P/L ' +
               (p.data[1] >= 0 ? '+' : '') + fmt(p.data[1]);
      } },
    series: [
      { name: 'profit', type: 'line', showSymbol: false, connectNulls: false,
        data: split.pos, lineStyle: { width: 2.2, color: UP },
        areaStyle: { color: UP, opacity: 0.15, origin: 'start' },
        markLine: refLines(marks),
        markArea: plan.band ? { silent: true, itemStyle: { color: dark ?
          'rgba(110,160,255,.07)' : 'rgba(47,111,235,.055)' },
          label: { show: true, position: 'insideBottom', color: muted,
                   fontSize: 10, formatter: 'expected move' },
          data: [[{ xAxis: plan.band[0] }, { xAxis: plan.band[1] }]] } : undefined },
      { name: 'loss', type: 'line', showSymbol: false, connectNulls: false,
        data: split.neg, lineStyle: { width: 2.2, color: DOWN },
        areaStyle: { color: DOWN, opacity: 0.15, origin: 'start' } }
    ]
  }));
}

/* ------------------------------------------------------------ positioning */

function exposureCharts() {
  const e = D.exposure;
  if (!e) return;
  const rows = e.exposure.rows;
  const spot = D.spot;
  const marks = [{ x: spot, label: 'spot', type: 'dotted' }];
  if (e.exposure.gamma_flip) marks.push({ x: e.exposure.gamma_flip,
    label: 'flip ' + fmt(e.exposure.gamma_flip), type: 'dashed', color: AMBER });
  if (e.max_pain) marks.push({ x: e.max_pain.strike,
    label: 'max pain ' + fmt(e.max_pain.strike), type: 'dashed', color: muted });

  mount('gex', frame({
    dataZoom: zoom(0.15),
    xAxis: xAxis('strike'),
    yAxis: yAxis('exposure per 1% move', {
      axisLabel: { color: muted, fontSize: 10.5,
        formatter: function (v) { return compact(v); } } }),
    tooltip: { trigger: 'axis', backgroundColor: panel, borderColor: line,
      textStyle: { color: ink, fontSize: 11.5 },
      formatter: function (ps) {
        let out = 'strike ' + fmt(ps[0].axisValue);
        ps.forEach(p => { out += '<br/>' + p.seriesName + ' ' +
          compact(p.data[1]); });
        return out;
      } },
    series: [
      // Not stacked: stacking is defined against a category axis, and on a
      // value axis it silently dropped the put series entirely. Two
      // independent series, calls positive and puts negative, is also how
      // this profile is conventionally drawn.
      { name: 'call gamma', type: 'bar', barMaxWidth: 7,
        itemStyle: { color: CALL },
        data: rows.map(r => [r.strike, r.call_gex]),
        markLine: refLines(marks) },
      { name: 'put gamma', type: 'bar', barMaxWidth: 7,
        itemStyle: { color: PUT },
        data: rows.map(r => [r.strike, r.put_gex]) }
    ]
  }));

  const cum = rows.map(r => [r.strike, r.cumulative_gex]);
  mount('gexcum', frame({
    legend: { show: false },
    dataZoom: zoom(0.15),
    xAxis: xAxis('strike'),
    yAxis: yAxis('cumulative exposure', {
      axisLabel: { color: muted, fontSize: 10.5,
        formatter: function (v) { return compact(v); } } }),
    series: [{ name: 'cumulative', type: 'line', showSymbol: false,
      data: cum, lineStyle: { width: 2, color: CALL },
      areaStyle: { opacity: .12, color: CALL },
      markLine: refLines(marks) }]
  }));

  mount('oi', frame({
    dataZoom: zoom(0.15),
    xAxis: xAxis('strike'),
    yAxis: yAxis('open interest', {
      axisLabel: { color: muted, fontSize: 10.5,
        formatter: function (v) { return compact(v); } } }),
    series: [
      { name: 'calls', type: 'bar', barMaxWidth: 9, itemStyle: { color: CALL },
        data: rows.map(r => [r.strike, r.call_oi]),
        markLine: refLines([{ x: spot, label: 'spot' }]) },
      { name: 'puts', type: 'bar', barMaxWidth: 9, itemStyle: { color: PUT },
        data: rows.map(r => [r.strike, -r.put_oi]) }
    ]
  }));

  if (e.max_pain && e.max_pain.profile) {
    const profile = e.max_pain.profile.map(p => [p.strike, p.payout]);
    mount('pain', frame({
      legend: { show: false },
      dataZoom: zoom(0.15),
      xAxis: xAxis('settlement price'),
      yAxis: yAxis('total payout to holders', {
        axisLabel: { color: muted, fontSize: 10.5,
          formatter: function (v) { return compact(v); } } }),
      series: [{ type: 'line', showSymbol: false, data: profile,
        lineStyle: { width: 2, color: PUT },
        areaStyle: { opacity: .10, color: PUT },
        markLine: refLines([
          { x: e.max_pain.strike, label: 'min ' + fmt(e.max_pain.strike),
            type: 'dashed', color: AMBER },
          { x: spot, label: 'spot', type: 'dotted' }]) }]
    }));
  }
}

/* -------------------------------------------------------------- the smile */

function smileChart() {
  const s = D.series;
  if (!s.calls.length && !s.puts.length) return;
  const marks = [{ x: D.spot, label: 'spot', type: 'dotted' }];
  const smile = D.exposure && D.exposure.smile;
  if (smile && smile.put_wing) marks.push({ x: smile.put_wing.strike,
    label: '25d put', type: 'dashed', color: PUT });
  if (smile && smile.call_wing) marks.push({ x: smile.call_wing.strike,
    label: '25d call', type: 'dashed', color: CALL });

  const pick = (rows) => rows.filter(r => r.iv).map(r => [r.strike, r.iv]);
  const allIv = pick(s.calls).concat(pick(s.puts)).map(p => p[1]).sort(
    (a, b) => a - b);
  // Clip the view at the 95th percentile with a little headroom. The
  // outliers are real quotes on contracts nobody trades, and letting them
  // set the scale hides the shape of the entire smile.
  const clip = allIv.length ? allIv[Math.floor(allIv.length * 0.95)] * 1.25
                            : null;
  mount('smile', frame({
    dataZoom: zoom(0.12),
    xAxis: xAxis('strike'),
    yAxis: yAxis('implied volatility', {
      max: clip,
      axisLabel: { color: muted, fontSize: 10.5,
        formatter: function (v) { return (v * 100).toFixed(0) + '%'; } } }),
    tooltip: { trigger: 'axis', backgroundColor: panel, borderColor: line,
      textStyle: { color: ink, fontSize: 11.5 },
      formatter: function (ps) {
        let out = 'strike ' + fmt(ps[0].axisValue);
        ps.forEach(p => { out += '<br/>' + p.seriesName + ' ' +
          (p.data[1] * 100).toFixed(2) + '%'; });
        return out;
      } },
    series: [
      { name: 'calls', type: 'line', smooth: true, showSymbol: false,
        data: pick(s.calls), lineStyle: { width: 2, color: CALL },
        markLine: refLines(marks) },
      { name: 'puts', type: 'line', smooth: true, showSymbol: false,
        data: pick(s.puts), lineStyle: { width: 2, color: PUT } }
    ]
  }));
}

function greekChart(id, key, yName) {
  const s = D.series;
  const pick = (rows) => rows.filter(r => r[key] !== null &&
    r[key] !== undefined).map(r => [r.strike, r[key]]);
  mount(id, frame({
    grid: { left: 66, right: 20, top: 28, bottom: 44 },
    dataZoom: [Object.assign({ type: 'inside', xAxisIndex: 0 },
      zoomWindow(0.12))],
    xAxis: xAxis('strike'),
    yAxis: yAxis(yName),
    series: [
      { name: 'calls', type: 'line', smooth: true, showSymbol: false,
        data: pick(s.calls), lineStyle: { width: 1.9, color: CALL },
        markLine: refLines([{ x: D.spot, label: 'spot' }]) },
      { name: 'puts', type: 'line', smooth: true, showSymbol: false,
        data: pick(s.puts), lineStyle: { width: 1.9, color: PUT } }
    ]
  }));
}

/* ------------------------------------------------------------- simulation */

function simulationCharts() {
  const sim = D.simulation;
  if (!sim) return;
  const fan = sim.simulation.fan;
  const days = fan.map(r => r.day);
  // Stacked pairs: an invisible base at the lower quantile, then the
  // spread to the upper one filled. The edges are drawn as faint lines
  // too, because a low-opacity fill on a dark background is nearly
  // invisible and a reader cannot tell where the interval actually ends.
  const band = (lo, hi, colour, opacity) => ([
    { type: 'line', stack: 'band' + lo, showSymbol: false, silent: true,
      lineStyle: { color: colour, opacity: 0.45, width: 1, type: 'dashed' },
      data: fan.map(r => r['p' + lo]), areaStyle: { opacity: 0 } },
    { type: 'line', stack: 'band' + lo, showSymbol: false, silent: true,
      lineStyle: { color: colour, opacity: 0.45, width: 1, type: 'dashed' },
      data: fan.map(r => r['p' + hi] - r['p' + lo]),
      areaStyle: { color: colour, opacity: opacity } }
  ]);

  mount('fan', frame({
    legend: { show: false },
    grid: { left: 70, right: 24, top: 24, bottom: 44 },
    xAxis: Object.assign({}, axis, { type: 'category', data: days,
      name: 'business days ahead', nameGap: 26 }),
    yAxis: yAxis('price'),
    tooltip: { trigger: 'axis', backgroundColor: panel, borderColor: line,
      textStyle: { color: ink, fontSize: 11.5 },
      formatter: function (ps) {
        const day = ps[0].axisValue;
        const row = fan[day - 1];
        return 'day ' + day + '<br/>p95 ' + fmt(row.p95) + '<br/>p75 ' +
               fmt(row.p75) + '<br/>median ' + fmt(row.p50) + '<br/>p25 ' +
               fmt(row.p25) + '<br/>p5 ' + fmt(row.p5);
      } },
    series: band(5, 95, CALL, 0.20)
      .concat(band(25, 75, CALL, 0.30))
      .concat([
        { name: 'median', type: 'line', showSymbol: false,
          data: fan.map(r => r.p50), lineStyle: { width: 2, color: CALL },
          markLine: { symbol: 'none', silent: true,
            data: [{ yAxis: sim.spot, lineStyle: { color: muted,
              type: 'dotted', width: 1.3 },
              label: { formatter: 'spot ' + fmt(sim.spot), color: muted,
                       fontSize: 10 } }] } }
      ])
  }));

  const hist = sim.simulation.terminal_histogram || [];
  if (hist.length) {
    mount('terminal', frame({
      legend: { show: false },
      grid: { left: 62, right: 24, top: 24, bottom: 44 },
      xAxis: xAxis('price at horizon'),
      yAxis: yAxis('paths'),
      series: [{ type: 'bar', barMaxWidth: 12, itemStyle: { color: CALL },
        data: hist.map(b => [(b.lo + b.hi) / 2, b.count]),
        markLine: { symbol: 'none', silent: true, data: [
          { xAxis: sim.spot, lineStyle: { color: muted, type: 'dotted' },
            label: { formatter: 'spot', color: muted, fontSize: 10 } }
        ] } }]
    }));
  }
}

/* --------------------------------------------------------------- backtest */

function backtestCharts() {
  const tests = D.backtests || [];
  if (!tests.length) return;
  const series = tests.map(function (t, i) {
    const curve = (t.settings && t.settings.equity_curve) || [];
    return { name: t.strategy.replace(/_/g, ' '), type: 'line',
      showSymbol: false, smooth: false,
      lineStyle: { width: 1.9 },
      data: curve.map((v, idx) => [idx + 1, v]) };
  });
  mount('equity', frame({
    grid: { left: 66, right: 24, top: 30, bottom: 46 },
    xAxis: xAxis('trade number', { min: 1 }),
    yAxis: yAxis('cumulative risk units'),
    series: series
  }));
}

/* --------------------------------------------------------- term structure */

function termCharts() {
  const term = D.term_structure || [];
  if (term.length < 2) return;
  const days = term.map(r => r.days);

  mount('term', frame({
    grid: { left: 68, right: 60, top: 30, bottom: 46 },
    xAxis: xAxis('days to expiry'),
    yAxis: [
      yAxis('at-the-money volatility', {
        axisLabel: { color: muted, fontSize: 10.5,
          formatter: v => (v * 100).toFixed(0) + '%' } }),
      Object.assign({}, axis, { type: 'value', name: 'expected move',
        nameGap: 42, position: 'right', scale: true,
        splitLine: { show: false } })
    ],
    series: [
      { name: 'atm volatility', type: 'line', smooth: true, symbol: 'circle',
        symbolSize: 7, data: term.map(r => [r.days, r.atm_iv]),
        lineStyle: { width: 2.2, color: CALL },
        itemStyle: { color: CALL } },
      { name: 'expected move', type: 'line', yAxisIndex: 1, smooth: true,
        symbol: 'circle', symbolSize: 6,
        data: term.map(r => [r.days, r.expected_move]),
        lineStyle: { width: 1.8, color: PUT, type: 'dashed' },
        itemStyle: { color: PUT } }
    ]
  }));

  const skew = term.filter(r => r.risk_reversal !== null &&
                                r.risk_reversal !== undefined);
  if (skew.length >= 2) {
    mount('skewterm', frame({
      grid: { left: 68, right: 24, top: 30, bottom: 46 },
      xAxis: xAxis('days to expiry'),
      yAxis: yAxis('vol points', {
        axisLabel: { color: muted, fontSize: 10.5,
          formatter: v => (v * 100).toFixed(1) } }),
      series: [
        { name: '25d risk reversal', type: 'line', smooth: true,
          symbol: 'circle', symbolSize: 6,
          data: skew.map(r => [r.days, r.risk_reversal]),
          lineStyle: { width: 2, color: PUT }, itemStyle: { color: PUT } },
        { name: '25d butterfly', type: 'line', smooth: true,
          symbol: 'circle', symbolSize: 6,
          data: skew.map(r => [r.days, r.butterfly]),
          lineStyle: { width: 2, color: CALL }, itemStyle: { color: CALL } }
      ]
    }));
  }
}

/* ------------------------------------------------------------ chain depth */

function depthCharts() {
  const chain = D.chain_series;
  if (!chain || (!chain.calls.length && !chain.puts.length)) return;
  mount('volume', frame({
    dataZoom: zoom(0.15),
    xAxis: xAxis('strike'),
    yAxis: yAxis('contracts traded', {
      axisLabel: { color: muted, fontSize: 10.5,
        formatter: v => compact(Math.abs(v)) } }),
    series: [
      { name: 'calls', type: 'bar', barMaxWidth: 7,
        itemStyle: { color: CALL },
        data: chain.calls.map(r => [r.strike, r.volume]),
        markLine: refLines([{ x: D.spot, label: 'spot' }]) },
      { name: 'puts', type: 'bar', barMaxWidth: 7, itemStyle: { color: PUT },
        data: chain.puts.map(r => [r.strike, -r.volume]) }
    ]
  }));
}

/* ------------------------------------------- structures, seen together */

function structureOverlay() {
  if (!D.plans.length) return;
  const palette = [CALL, PUT, UP, DOWN, AMBER,
                   dark ? '#c084fc' : '#7c3aed',
                   dark ? '#22d3ee' : '#0891b2',
                   dark ? '#f472b6' : '#db2777'];
  const series = D.plans.map(function (plan, i) {
    const curve = plan.payoff_curve;
    return {
      name: plan.strategy.replace(/_/g, ' '),
      type: 'line', showSymbol: false, smooth: false,
      lineStyle: { width: 1.7, color: palette[i % palette.length] },
      itemStyle: { color: palette[i % palette.length] },
      data: curve.prices.map((p, j) => [p, curve.pnl[j]]),
      markLine: i === 0 ? refLines([{ x: D.spot, label: 'spot' }]) : undefined
    };
  });
  mount('overlay', frame({
    legend: { top: 0, right: 0, type: 'scroll', textStyle: { color: muted,
      fontSize: 10 }, itemWidth: 13, itemHeight: 7, icon: 'roundRect' },
    grid: { left: 70, right: 24, top: 46, bottom: 46 },
    dataZoom: zoom(0.18),
    xAxis: xAxis('underlying at expiry'),
    yAxis: yAxis('profit and loss'),
    series: series
  }));
}

function riskRewardScatter() {
  const comparison = D.comparison;
  if (!comparison || !comparison.rows) return;
  const points = comparison.rows.filter(r =>
    r.probability_of_profit !== null && r.expected_return_on_risk !== null &&
    r.capital_at_risk);
  if (!points.length) return;
  const maxRisk = Math.max.apply(null, points.map(p => p.capital_at_risk));
  mount('riskreward', frame({
    legend: { show: false },
    grid: { left: 72, right: 30, top: 26, bottom: 48 },
    xAxis: xAxis('model probability of profit', {
      min: null, max: null,
      axisLabel: { color: muted, fontSize: 10.5,
        formatter: v => (v * 100).toFixed(0) + '%' } }),
    yAxis: yAxis('expected return on risk', {
      axisLabel: { color: muted, fontSize: 10.5,
        formatter: v => (v * 100).toFixed(0) + '%' } }),
    tooltip: { trigger: 'item', backgroundColor: panel, borderColor: line,
      textStyle: { color: ink, fontSize: 11.5 },
      formatter: function (p) {
        const row = p.data[3];
        return '<strong>' + row.strategy.replace(/_/g, ' ') + '</strong><br/>' +
          'P(profit) ' + (row.probability_of_profit * 100).toFixed(1) + '%<br/>' +
          'return on risk ' + (row.expected_return_on_risk * 100).toFixed(1) + '%<br/>' +
          'capital at risk ' + fmt(row.capital_at_risk) + '<br/>' +
          'friction ' + row.friction_verdict;
      } },
    series: [{
      type: 'scatter',
      symbolSize: function (d) {
        return 12 + 26 * Math.sqrt((d[2] || 0) / maxRisk);
      },
      itemStyle: {
        color: function (p) {
          const row = p.data[3];
          if (row.friction_verdict === 'untradeable') return DOWN;
          return row.expected_return_on_risk >= 0 ? UP : muted;
        },
        opacity: 0.75
      },
      label: { show: true, position: 'top', color: muted, fontSize: 10,
        formatter: p => p.data[3].strategy.replace(/_/g, ' ') },
      data: points.map(r => [r.probability_of_profit,
                             r.expected_return_on_risk,
                             r.capital_at_risk, r]),
      markLine: { symbol: 'none', silent: true,
        lineStyle: { color: muted, type: 'dashed', width: 1 },
        data: [{ yAxis: 0 }] }
    }]
  }));
}

/* ------------------------------------------ distributions per structure */

function structureDistributions() {
  const sim = D.simulation;
  if (!sim || !(sim.structures || []).length) return;
  const rows = sim.structures.filter(s => (s.histogram || []).length);
  rows.slice(0, 6).forEach(function (row, i) {
    const id = 'dist' + i;
    if (!document.getElementById(id)) return;
    const bars = row.histogram.map(b => [(b.lo + b.hi) / 2, b.count]);
    mount(id, frame({
      legend: { show: false },
      grid: { left: 58, right: 18, top: 34, bottom: 40 },
      title: { text: row.strategy.replace(/_/g, ' '), left: 0, top: 0,
        textStyle: { color: ink, fontSize: 12, fontWeight: 600 } },
      xAxis: xAxis('profit and loss'),
      yAxis: yAxis('paths'),
      series: [{ type: 'bar', barMaxWidth: 10,
        data: bars,
        itemStyle: { color: function (p) {
          return p.data[0] >= 0 ? UP : DOWN; } },
        markLine: { symbol: 'none', silent: true, data: [
          { xAxis: 0, lineStyle: { color: muted, type: 'dotted' } },
          { xAxis: row.median, lineStyle: { color: AMBER, type: 'dashed' },
            label: { formatter: 'median', color: AMBER, fontSize: 9 } }
        ] } }]
    }));
  });
}

/* ---------------------------------------------------- backtest detail */

function backtestDetail() {
  const tests = D.backtests || [];
  if (!tests.length) return;

  // Drawdown from the running peak, per structure.
  const drawdowns = tests.map(function (t) {
    const curve = (t.settings && t.settings.equity_curve) || [];
    let peak = 0;
    const dd = curve.map(function (v, i) {
      peak = Math.max(peak, v);
      return [i + 1, v - peak];
    });
    return { name: t.strategy.replace(/_/g, ' '), type: 'line',
             showSymbol: false, data: dd, lineStyle: { width: 1.7 },
             areaStyle: { opacity: 0.10 } };
  });
  mount('drawdown', frame({
    grid: { left: 68, right: 24, top: 30, bottom: 46 },
    xAxis: xAxis('trade number', { min: 1 }),
    yAxis: yAxis('drawdown, risk units'),
    series: drawdowns
  }));

  // Per-trade outcome distribution for the first structure with trades.
  const withTrades = tests.find(t => (t.trades || []).length);
  if (!withTrades) return;
  const returns = withTrades.trades
    .map(t => t.return_on_risk)
    .filter(v => v !== null && v !== undefined)
    .sort((a, b) => a - b);
  if (returns.length < 5) return;
  const lo = returns[0], hi = returns[returns.length - 1];
  const bins = 30, width = (hi - lo) / bins || 1;
  const counts = new Array(bins).fill(0);
  returns.forEach(v => {
    counts[Math.min(bins - 1, Math.floor((v - lo) / width))] += 1;
  });
  mount('tradehist', frame({
    legend: { show: false },
    grid: { left: 60, right: 20, top: 34, bottom: 44 },
    title: { text: withTrades.strategy.replace(/_/g, ' ') + ', per trade',
      left: 0, top: 0, textStyle: { color: ink, fontSize: 12,
        fontWeight: 600 } },
    xAxis: xAxis('return on risk', {
      axisLabel: { color: muted, fontSize: 10.5,
        formatter: v => (v * 100).toFixed(0) + '%' } }),
    yAxis: yAxis('trades'),
    series: [{ type: 'bar', barMaxWidth: 14,
      data: counts.map((c, i) => [lo + (i + 0.5) * width, c]),
      itemStyle: { color: p => p.data[0] >= 0 ? UP : DOWN },
      markLine: { symbol: 'none', silent: true,
        data: [{ xAxis: 0, lineStyle: { color: muted, type: 'dotted' } }] } }]
  }));
}

/* ------------------------------------------------------------- strategies */

function renderPlan(index) {
  const plan = D.plans[index];
  if (!plan) return;
  document.querySelectorAll('.picker button').forEach((b, i) =>
    b.setAttribute('aria-pressed', String(i === index)));

  const a = plan.analysis, prob = plan.probability || {},
        g = plan.net_greeks || {}, f = plan.friction || {};
  const tiles = [
    ['Structure', plan.strategy.replace(/_/g, ' '), ''],
    [a.trade_type === 'credit' ? 'Net credit' : 'Net debit',
     fmt(Math.abs(a.net_cash)), a.trade_type === 'credit' ? 'pos' : 'neg'],
    ['Max gain', fmt(a.max_gain), 'pos'],
    ['Max loss', fmt(a.max_loss), 'neg'],
    ['Reward to risk', a.reward_risk ? fmt(a.reward_risk) + ' to 1' : 'n/a', ''],
    ['Breakevens', (a.breakevens || []).map(b => fmt(b)).join('  ') || 'none', ''],
    ['Model P(profit)', prob.profit != null ?
      (prob.profit * 100).toFixed(1) + '%' : 'n/a', ''],
    ['Model expected P/L', fmt(prob.expected_pnl),
     (prob.expected_pnl || 0) >= 0 ? 'pos' : 'neg'],
    ['Net delta', fmt(g.delta, 3), ''],
    ['Net theta per day', fmt(g.theta, 3), (g.theta || 0) >= 0 ? 'pos' : 'neg'],
    ['Net vega', fmt(g.vega, 2), ''],
    ['Net gamma', fmt(g.gamma, 4), '']
  ];
  document.getElementById('plan-tiles').innerHTML = tiles.map(t =>
    '<div class="tile"><div class="k">' + t[0] + '</div><div class="v ' +
    t[2] + '">' + t[1] + '</div></div>').join('');
  document.getElementById('plan-when').textContent = plan.when_to_use || '';
  document.getElementById('plan-friction').innerHTML = f.verdict ?
    '<span class="badge ' + f.verdict + '">friction ' + f.verdict + '</span> ' +
    '<span class="empty">' + f.reason + '</span>' : '';
  document.getElementById('plan-legs').innerHTML = plan.legs.map(l =>
    '<tr><td>' + l.side + ' ' + l.kind + '</td><td>' +
    (l.strike == null ? '' : fmt(l.strike)) + '</td><td>' + fmt(l.qty) +
    '</td><td>' + fmt(l.price) + '</td><td>' + fmt(l.bid) + '</td><td>' +
    fmt(l.ask) + '</td><td>' + (l.iv ? (l.iv * 100).toFixed(1) + '%' : 'n/a') +
    '</td><td>' + (l.open_interest == null ? 'n/a' : l.open_interest) +
    '</td></tr>').join('');
  payoffChart(plan);
}

/* ------------------------------------------------------------------ start */

exposureCharts();
termCharts();
depthCharts();
structureOverlay();
riskRewardScatter();
simulationCharts();
structureDistributions();
backtestCharts();
backtestDetail();
smileChart();
greekChart('delta', 'delta', 'delta');
greekChart('gamma', 'gamma', 'gamma');
greekChart('vega', 'vega', 'vega');
greekChart('theta', 'theta', 'theta per day');
greekChart('vanna', 'vanna', 'vanna');
greekChart('charm', 'charm', 'charm per day');
if (D.plans.length) {
  document.querySelectorAll('.picker button').forEach((b, i) =>
    b.addEventListener('click', () => renderPlan(i)));
  renderPlan(0);
}
"""
