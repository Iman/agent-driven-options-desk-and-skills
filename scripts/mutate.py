#!/usr/bin/env python3
"""Break the code on purpose and check that the tests notice.

WHY THIS EXISTS. A passing suite proves the tests ran, not that they can
fail. This project has twice shipped tests that could not: a Greek suite
scaled by max(1, |expected|), which made the tolerance absolute and left
three Greeks effectively untested, and an earlier runtime-docs test that
regenerated the file it was asserting against. Both looked green for weeks.

The claim "mutation tested" was in the documentation before the harness
was, which is exactly the kind of unverifiable statement this project is
supposed to refuse. So here it is, in the tree, runnable:

    python3 scripts/mutate.py             every mutation
    python3 scripts/mutate.py --list      what it would try
    python3 scripts/mutate.py --only veta

Each mutation is applied to a copy of the file, the named tests are run,
and the mutation is DETECTED if they fail and SURVIVED if they pass. A
survivor is a hole in the suite, not a bug in the code.

Two traps this harness avoids, both hit in earlier attempts. Bytecode is
disabled with -B and PYTHONDONTWRITEBYTECODE, because two mutations of one
file that happen to produce identical byte counts within the same second
can otherwise reuse a stale pyc and run the wrong code. And the original
file is restored in a finally block, so an interrupted run does not leave
the tree mutated.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENGINE = "engine/src/optiondesk_engine"
DASHBOARD = "shell/src/optiondesk/dashboard/data.py"
PAGE = "shell/src/optiondesk/dashboard/page.py"
KEYS = "shell/src/optiondesk/cli/keys.py"
CONFIG = "shell/src/optiondesk/config.py"

# name, file, what to find, what to replace it with, which tests must fail
MUTATIONS = [
    ("delta-sign", ENGINE + "/pricing/greeks_full.py",
     '"delta": delta,', '"delta": -delta,',
     "engine/tests/test_greeks_full.py"),
    ("vega-scale", ENGINE + "/pricing/greeks_full.py",
     '"vega": vega,', '"vega": vega * 1.05,',
     "engine/tests/test_greeks_full.py"),
    ("veta-sign", ENGINE + "/pricing/greeks_full.py",
     '"veta": veta_year / DAYS_PER_YEAR,',
     '"veta": -veta_year / DAYS_PER_YEAR,',
     "engine/tests/test_greeks_full.py"),
    ("color-sign", ENGINE + "/pricing/greeks_full.py",
     '"color": color_year / DAYS_PER_YEAR,',
     '"color": -color_year / DAYS_PER_YEAR,',
     "engine/tests/test_greeks_full.py"),
    ("iv-guard-removed", ENGINE + "/pricing/black_scholes.py",
     "if abs(v) < MIN_VEGA:", "if abs(v) < -1.0:",
     "engine/tests/test_audit_regressions.py"),
    ("iv-seed-returned", ENGINE + "/pricing/black_scholes.py",
     "if abs(vega_raw(spot, strike, t, sigma, r, q)) < MIN_VEGA:",
     "if abs(vega_raw(spot, strike, t, sigma, r, q)) < -1.0:",
     "engine/tests/test_audit_regressions.py"),
    ("rhat-stuck-chain", ENGINE + "/simulation/garch.py",
     "        # Every draw identical: the chain is stuck, not converged.\n"
     "        return float(\"inf\")",
     "        return 1.0",
     "engine/tests/test_simulation.py"),
    ("max-pain-zero-oi", ENGINE + "/analytics/exposure.py",
     "    if sum(int(c[\"open_interest\"]) for c in priced) <= 0:\n"
     "        return None",
     "    if False:\n        return None",
     "engine/tests/test_exposure.py"),
    ("rank-non-finite", ENGINE + "/analytics/compare.py",
     "    finite_expectation = (expected is not None\n"
     "                          and math.isfinite(float(expected)))",
     "    finite_expectation = expected is not None",
     "engine/tests/test_compare.py"),
    ("backtest-compounding", ENGINE + "/backtest/stats.py",
     "total_return_on_risk", "total_return_on_risk_",
     "engine/tests/test_backtest.py"),
    ("degraded-dropped", "shell/src/optiondesk/cli/exposure.py",
     '        "degraded": bool(source_meta.get("degraded")),\n', "",
     "shell/tests/test_summary_degraded_contract.py"),
    ("runtime-docs-stale", "shell/tools/gen_runtime_docs.py",
     "## Skill: {}", "## Skill {}",
     "shell/tests/test_runtime_docs.py"),
    # The defects found and fixed on 2026-08-30. A fix without a mutation is
    # a fix nobody will notice being undone.
    ("mcp-answers-notifications", "shell/src/optiondesk/mcp/server.py",
     '    if "id" not in request:\n        return None\n',
     "",
     "shell/tests/test_mcp_server.py"),
    ("mcp-required-unenforced", "shell/src/optiondesk/mcp/server.py",
     "        missing = [key for key in (tool[\"inputSchema\"]"
     ".get(\"required\") or [])",
     "        missing = [key for key in ()",
     "shell/tests/test_mcp_server.py"),
    ("mcp-non-dict-arguments", "shell/src/optiondesk/mcp/server.py",
     "        if not isinstance(supplied, dict):",
     "        if not isinstance(supplied, (dict, str, list, int)):",
     "shell/tests/test_mcp_server.py"),
    ("house-rules-key-scan", "scripts/refresh.py",
     "(?=[A-Z0-9]*[0-9])", "",
     "shell/tests/test_house_rules.py"),
    ("summarise-uncontained", "agent/src/optiondesk_agent/artifacts.py",
     "    meta = payload.get(\"meta\")\n"
     "    return meta if isinstance(meta, dict) else {}",
     "    return payload.get(\"meta\", {})",
     "agent/tests/test_artifacts.py"),
    ("records-stat-race", "agent/src/optiondesk_agent/artifacts.py",
     '        for path in sorted(self.directory.glob("*.json"), key=_age,\n'
     "                           reverse=True):",
     '        for path in sorted(self.directory.glob("*.json"),\n'
     "                           key=lambda p: p.stat().st_mtime,\n"
     "                           reverse=True):",
     "agent/tests/test_artifacts.py"),
    ("archive-skipped", "shell/src/optiondesk/artifacts.py",
     "    if path.exists() and path.read_bytes() != tmp.read_bytes():\n"
     "        archive_existing(path)\n",
     "",
     "shell/tests/test_artifact_archive.py"),
    ("archive-eats-the-write", "shell/src/optiondesk/artifacts.py",
     "    except OSError:\n        return None\n\n\ndef write_json",
     "    except OSError:\n        raise\n\n\ndef write_json",
     "shell/tests/test_artifact_archive.py"),
    ("evidence-unpinned", "scripts/evidence.py",
     "    if generated_utc:\n"
     "        for candidate in candidates:\n"
     "            if _generated(candidate) == generated_utc:\n"
     "                return candidate\n"
     "        return None\n",
     "",
     "shell/tests/test_documented_evidence.py"),
    ("black76-carry-dropped", ENGINE + "/pricing/forwards.py",
     "    return bs_price(future, strike, t, sigma, kind, r, r)",
     "    return bs_price(future, strike, t, sigma, kind, r, 0.0)",
     "engine/tests/test_forwards.py"),
    ("fx-foreign-rate-dropped", ENGINE + "/pricing/forwards.py",
     "    return bs_price(spot, strike, t, sigma, kind, r_domestic, "
     "r_foreign)",
     "    return bs_price(spot, strike, t, sigma, kind, r_domestic, 0.0)",
     "engine/tests/test_forwards.py"),
    ("dividend-not-fetched", "shell/src/optiondesk/cli/chain.py",
     "            yield_provider, _ = resolve(CAP_DIVIDEND_YIELD, "
     "args.provider)\n"
     "            fetched_q = yield_provider.dividend_yield(args.symbol, "
     "spot=spot)",
     "            fetched_q = {\"dividend_yield\": None, \"note\": None}",
     "shell/tests/test_dividend_yield.py"),
    ("dividend-unit-guessed", "shell/src/optiondesk/providers/yahoo.py",
     "                published = float(raw) / 100.0",
     "                published = (float(raw) / 100.0 if raw > 1.0 "
     "else float(raw))",
     "shell/tests/test_dividend_yield.py"),
    ("band-fabricated", ENGINE + "/strategies/playbook.py",
     '    plan = _plan("iron_condor", legs, chain, band)',
     '    plan = _plan("iron_condor", legs, chain, reference)',
     "engine/tests/test_audit_regressions.py"),
    ("backtest-note-blames-trade-count",
     "shell/src/optiondesk/cli/backtest.py",
     "    if entered and not measurable:",
     "    if False:",
     "shell/tests/test_backtest_unbounded.py"),
    # The find string has to track the sentence in the document. It said
    # "Thirty-nine" while the document said "Forty", so this mutation was
    # reported SKIPPED, which is a mutation that proves nothing at all.
    ("dashboard-counts-unguarded", "docs/CAPABILITIES.md",
     "Forty-two panels and, at most, thirty-two chart canvases",
     "Thirty-five panels and, at most, twenty-eight chart canvases",
     "shell/tests/test_documented_counts.py"),
    ("installer-bare-repo-accepted", "install.sh",
     '  require_remote_repo "$REPO"\n',
     "",
     "shell/tests/test_installer.py"),
    ("packaging-drops-a-resource", "scripts/package.py",
     "            for item in sorted(skill.rglob(\"*\")):\n"
     "                if not _publishable(item):\n"
     "                    continue\n",
     "            for item in sorted(skill.glob(\"*\")):\n"
     "                if not _publishable(item):\n"
     "                    continue\n",
     "shell/tests/test_packaging.py"),
    ("strategy-not-built-degraded", "shell/src/optiondesk/cli/strategy.py",
     '            "built": False,\n'
     '            "degraded": bool(source_meta.get("degraded")),\n'
     '            "degraded_reason": source_meta.get("degraded_reason"),\n'
     '            "reason": ("no viable structure on this chain',
     '            "built": False,\n'
     '            "reason": ("no viable structure on this chain',
     "shell/tests/test_summary_degraded_contract.py"),
    # The cross-expiry collectors behind the surface, the premium and the
    # condor scatter. Each reaches past the selected group, which is
    # exactly where a per-group collector goes wrong quietly.
    ("surface-wrong-side", DASHBOARD,
     'if contract.get("type") != ("put" if strike < spot else "call"):',
     'if contract.get("type") != ("call" if strike < spot else "put"):',
     "shell/tests/test_dashboard_data.py"),
    ("surface-from-one-expiry", DASHBOARD,
     "    if len(expiries) < 2:\n        return None",
     "    if len(expiries) < 1:\n        return None",
     "shell/tests/test_dashboard_data.py"),
    ("premium-without-realised", DASHBOARD,
     "    if not simulation:\n        return None",
     "    if False:\n        return None",
     "shell/tests/test_dashboard_data.py"),
    ("premium-gap-inverted", DASHBOARD,
     '"gap": implied - realised})',
     '"gap": realised - implied})',
     "shell/tests/test_dashboard_data.py"),
    ("condor-width-from-wings", DASHBOARD,
     "            width = shorts[-1] - shorts[0]",
     "            width = longs[-1] - longs[0]",
     "shell/tests/test_dashboard_data.py"),
    ("condor-scored-across-expiries", DASHBOARD,
     '        comparison = group["artifacts"].get("comparison")',
     '        comparison = next(\n'
     '            (g["artifacts"].get("comparison") for g in groups\n'
     '             if g["artifacts"].get("comparison")), None)',
     "shell/tests/test_dashboard_data.py"),
    ("condor-one-short-admitted", DASHBOARD,
     "            if len(shorts) < 2:\n                continue",
     "            if len(shorts) < 1:\n                continue",
     "shell/tests/test_dashboard_data.py"),
    # And the markup side of the same four panels: a canvas emitted with no
    # artifact behind it, or an artifact with no canvas, are both invisible
    # in a page that renders perfectly well either way.
    ("surface-panel-dropped", PAGE,
     'sections.append(_surface_section(payload.get("surface")))',
     'sections.append("")',
     "shell/tests/test_dashboard_page.py"),
    ("premium-panel-dropped", PAGE,
     'sections.append(_premium_section(payload.get("variance_premium")))',
     'sections.append("")',
     "shell/tests/test_dashboard_page.py"),
    ("condor-panel-dropped", PAGE,
     'sections.append(_condor_section(payload.get("condors")))',
     'sections.append("")',
     "shell/tests/test_dashboard_page.py"),
    ("gamma-panel-without-an-overlay", PAGE,
     '    if not has_gamma and not plans:\n        return ""',
     '    if False:\n        return ""',
     "shell/tests/test_dashboard_page.py"),
    ("surface-missing-from-the-blob", PAGE,
     '        "surface": payload.get("surface"),',
     '        "surface": None,',
     "shell/tests/test_dashboard_page.py"),
    ("row-notes-not-folded", PAGE,
     '    notes = _grouped_notes(meta.get("notes") or [])',
     '    notes = [str(n) for n in (meta.get("notes") or [])]',
     "shell/tests/test_dashboard_page.py"),
    ("row-ranges-never-joined", PAGE,
     '        if runs and number == runs[-1][1] + 1:',
     '        if False:',
     "shell/tests/test_dashboard_page.py"),
    ("header-shows-the-full-path", PAGE,
     '''        path=html.escape(Path(str(payload.get("ladder_path")
                                  or payload["artifact_dir"])).name))''',
     '''        path=html.escape(str(payload.get("ladder_path")
                             or payload["artifact_dir"])))''',
     "shell/tests/test_dashboard_page.py"),
    ("key-mask-disabled", KEYS,
     "    if len(value) <= MASK_VISIBLE * 2:",
     "    if False:",
     "shell/tests/test_keys_cli.py"),
    ("key-file-left-world-readable", KEYS,
     "    os.chmod(USER_CONFIG, stat.S_IRUSR | stat.S_IWUSR)",
     "    pass",
     "shell/tests/test_keys_cli.py"),
    ("key-unset-keeps-the-line", KEYS,
     '            if not line.startswith(variable + "=")]',
     "            if True]",
     "shell/tests/test_keys_cli.py"),
    ("empty-key-written", KEYS,
     '        raise ValueError("no key given, nothing was written")',
     "        pass",
     "shell/tests/test_keys_cli.py"),
    ("piped-install-trusts-the-cwd", "install.sh",
     "  [ -f \"${BASH_SOURCE[0]}\" ] || return 1",
     "  true",
     "shell/tests/test_installer.py"),
    ("container-loses-artifacts-silently", "docker-entrypoint.sh",
     "            exit 64",
     "            :",
     "shell/tests/test_container.py"),
    ("sampler-runs-silently", "shell/src/optiondesk/cli/simulate.py",
     "          file=sys.stderr)",
     "          file=open(os.devnull, \"w\"))",
     "shell/tests/test_simulate_cli.py"),
    ("duration-estimate-is-a-constant",
     "shell/src/optiondesk/cli/simulate.py",
     "    seconds = iterations * observations * "
     "SECONDS_PER_ITERATION_OBSERVATION",
     "    seconds = 1.0",
     "shell/tests/test_simulate_cli.py"),
    ("graph-hides-degradation", "agent/src/optiondesk_agent/graph.py",
     "        if degraded:\n            body += [\"\", \"Degraded stages, "
     "which the figures above inherit:\"]",
     "        if False:\n            body += [\"\", \"Degraded stages, "
     "which the figures above inherit:\"]",
     "agent/tests/test_graph.py"),
    ("scan-boundary-never-flagged", ENGINE + "/strategies/timespread.py",
     "    gain_on_boundary = on_boundary(best_index)",
     "    gain_on_boundary = False",
     "engine/tests/test_timespread.py"),
    ("price-floor-flagged-as-a-window", ENGINE + "/strategies/timespread.py",
     "    lo_is_floor = lo <= 0.011",
     "    lo_is_floor = False",
     "engine/tests/test_timespread.py"),
    ("composite-outranks-the-comparison", ENGINE + "/analytics/ranking.py",
     "    if row.get(\"rankable\") is False:",
     "    if False:",
     "shell/tests/test_dashboard_page.py"),
    ("overlap-block-ignored", "shell/src/optiondesk/cli/backtest.py",
     "    significance = engine_backtest.permutation_p_value(\n"
     "        returns, block=overlap_block)",
     "    significance = engine_backtest.permutation_p_value(returns)",
     "shell/tests/test_backtest_overlap.py"),
    ("permutation-flips-single-trades", ENGINE + "/backtest/stats.py",
     "            signs.extend([sign] * block)",
     "            signs.extend([sign])",
     "engine/tests/test_backtest.py"),
    ("antithetic-flag-claims-true", ENGINE + "/simulation/paths.py",
     '        "antithetic": False,',
     '        "antithetic": True,',
     "engine/tests/test_simulation.py"),
    ("iv-solver-refuses-instead-of-bisecting",
     ENGINE + "/pricing/black_scholes.py",
     "            # volatility information is still refused there.\n"
     "            break",
     "            # volatility information is still refused there.\n"
     "            return None",
     "engine/tests/test_audit_regressions.py"),
    ("zero-rate-silently-replaced", "shell/src/optiondesk/cli/greeks.py",
     "    rate = 0.04 if rate_missing else float(snapshot[\"risk_free_rate\"])",
     "    rate = float(snapshot.get(\"risk_free_rate\") or 0.04)",
     "shell/tests/test_greeks_cli.py"),
    ("curve-priced-at-the-default-rate",
     "shell/src/optiondesk/cli/strategy.py",
     "        r=plan.get(\"risk_free_rate\", DEFAULT_CURVE_RATE),\n"
     "        q=plan.get(\"dividend_yield\", DEFAULT_CURVE_YIELD))",
     "        r=DEFAULT_CURVE_RATE, q=DEFAULT_CURVE_YIELD)",
     "shell/tests/test_strategy_cli.py"),
    ("exposure-skip-reason-collapsed",
     "shell/src/optiondesk/cli/exposure.py",
     "        if reasons.get(\"no_open_interest\"):",
     "        if reasons.get(\"no_gamma\"):",
     "shell/tests/test_exposure_cli.py"),
    ("ratio-quantity-check-removed", ENGINE + "/strategies/timespread.py",
     "    if long_qty <= short_qty:\n        return None",
     "    if False:\n        return None",
     "engine/tests/test_timespread.py"),
    ("ratio-tail-check-removed", ENGINE + "/strategies/timespread.py",
     "    if at_edge < inside:\n        return None",
     "    if False:\n        return None",
     "engine/tests/test_timespread.py"),
    ("bear-call-credit-guard-removed", ENGINE + "/strategies/playbook.py",
     "    plan = _plan(\"bear_call_spread\", legs, chain, band)\n"
     "    if plan[\"analysis\"][\"net_cash\"] <= 0:\n        return None",
     "    plan = _plan(\"bear_call_spread\", legs, chain, band)",
     "engine/tests/test_strategies.py"),
    ("timespread-rates-ignored", ENGINE + "/strategies/timespread.py",
     "    rate = chain.get(\"risk_free_rate\")\n"
     "    yield_ = chain.get(\"dividend_yield\")",
     "    rate = None\n    yield_ = None",
     "engine/tests/test_timespread.py"),
    ("ratio-guard-removed", ENGINE + "/strategies/timespread.py",
     "    if short_mass >= long_mass:\n        return None",
     "    if False:\n        return None",
     "engine/tests/test_timespread.py"),
    ("credit-vertical-pays-a-debit", ENGINE + "/strategies/playbook.py",
     "    plan = _plan(\"bull_put_spread\", legs, chain, band)\n"
     "    # A credit spread that pays a debit has its strikes the wrong way\n"
     "    # round or its quotes crossed. Either way it is not this structure.\n"
     "    if plan[\"analysis\"][\"net_cash\"] <= 0:\n        return None",
     "    plan = _plan(\"bull_put_spread\", legs, chain, band)",
     "engine/tests/test_strategies.py"),
    ("calendar-strike-from-near-chain-only",
     ENGINE + "/strategies/timespread.py",
     "    chosen = min(shared, key=lambda value: abs(value - target))",
     "    chosen = target",
     "engine/tests/test_timespread.py"),
    ("tooltip-prints-raw-floats", "shell/src/optiondesk/dashboard/charts.py",
     "      valueFormatter: function (v) {",
     "      valueFormatterDisabled: function (v) {",
     "shell/tests/test_dashboard_page.py"),
    ("payoff-axis-unformatted", "shell/src/optiondesk/dashboard/charts.py",
     "    axisLabel: { color: muted, fontSize: 10.5, formatter: axisNumber } },",
     "    axisLabel: { color: muted, fontSize: 10.5 } },",
     "shell/tests/test_dashboard_page.py"),
    ("engine-licence-hardcoded", "shell/src/optiondesk/engine_bridge.py",
     '        "license": engine_license if AVAILABLE else None,',
     '        "license": "AGPL-3.0-only" if AVAILABLE else None,',
     "shell/tests/test_license_claims.py"),
    ("key-created-world-readable", KEYS,
     "os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)",
     "os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)",
     "shell/tests/test_keys_cli.py"),
    ("settings-cache-not-invalidated", KEYS,
     "    config_module._DOTENV_CACHE = None",
     "    pass",
     "shell/tests/test_keys_cli.py"),
    ("source-matched-as-substring", KEYS,
     "        if name.strip() == variable:",
     "        if variable in line:",
     "shell/tests/test_keys_cli.py"),
    # The composite score. Both of these are silent: the module still
    # returns a plausible number out of 100 for every structure, and only
    # the rows where friction is worst, or where a volatility view has been
    # stated, come out wrong.
    ("ranking-thin-verdict-ignored", ENGINE + "/analytics/ranking.py",
     '    thin = THIN_MULTIPLIER if verdict == "thin" else 1.0',
     "    thin = 1.0",
     "engine/tests/test_ranking.py"),
    ("ranking-untradeable-is-scored", ENGINE + "/analytics/ranking.py",
     "    if verdict in EXCLUDING_VERDICTS:",
     "    if verdict in ():",
     "engine/tests/test_ranking.py"),
    ("credential-order-dotenv-before-environment", CONFIG,
     "    env = os.environ.get(name)\n"
     "    if env:\n"
     "        return env\n"
     "    dotenv = _load_dotenv_files().get(name)\n"
     "    if dotenv:\n"
     "        return dotenv",
     "    dotenv = _load_dotenv_files().get(name)\n"
     "    if dotenv:\n"
     "        return dotenv\n"
     "    env = os.environ.get(name)\n"
     "    if env:\n"
     "        return env",
     "shell/tests/test_keys_cli.py"),
]


# Mutants that provably cannot change behaviour. A survivor is normally a
# hole in the suite, but not when the mutated expression is redundant with
# another that still holds. Each one is recorded with the argument, so that
# "we could not kill it" is never quietly filed as "we chose not to".
EQUIVALENT = {
    "ratio-guard-removed": (
        "The entry-time delta bound cannot fire while the quantity check "
        "and the strike ordering both hold. Reaching it needs short_mass "
        "at or above long_mass, which with two longs against one short "
        "means the short's delta exceeding twice the long's, while the "
        "short is also required to be the further out of the money of the "
        "pair and therefore the lower delta one. No chain admits both. It "
        "is kept as defence in depth for a future shape that does not "
        "carry those two properties, and this entry has to be revisited "
        "the day one appears."),
    "ratio-quantity-check-removed": (
        "The quantity check and the tail check cover each other exactly, "
        "for a two-leg structure, and neither can be killed while the "
        "other stands. Past the far strike both legs are deep in the "
        "money, so the profit slope at the edge of the scan is long_qty "
        "minus short_qty. With the quantity check removed, any shape it "
        "would have refused has a slope of zero or less there and is "
        "refused by the tail check instead. They are kept as two checks "
        "because they say different things to a reader and because the "
        "coverage argument holds only for two legs: a future builder with "
        "three would break it, and then this entry has to go."),
    "ratio-tail-check-removed": (
        "The same argument from the other side. With the quantity check "
        "in place a two-leg structure always has a positive slope at the "
        "edge in its own direction, so the tail check can never fire and "
        "removing it changes nothing measurable. It is kept because it is "
        "the only one of the three that reads the payoff rather than the "
        "contracts, which is what would catch a shape the other two were "
        "never designed for."),
    "rank-non-finite": (
        "rankable also requires math.isfinite(expected_return), and "
        "expected_return is expected divided by a finite risk, so a "
        "non-finite expectation always produces a non-finite return and is "
        "excluded by the second test whatever the first one says. The "
        "mutated line is redundant on purpose, as defence in depth against "
        "a future change to how expected_return is derived."),
}


def interpreter():
    for candidate in (ROOT / "shell" / ".venv" / "bin" / "python",
                      ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def run_tests(target, python):
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    finished = subprocess.run(
        [python, "-B", "-m", "pytest", target, "-q", "--no-header",
         "-p", "no:cacheprovider", "-x"],
        cwd=str(ROOT), capture_output=True, text=True, env=environment,
        timeout=900)
    return finished.returncode == 0, finished.stdout.strip().splitlines()


def apply_one(name, relative, find, replace, tests, python):
    path = ROOT / relative
    original = path.read_text(encoding="utf-8")
    if find not in original:
        return "SKIPPED", "pattern not present: {}".format(find[:40])
    mutated = original.replace(find, replace, 1)
    if mutated == original:
        return "SKIPPED", "replacement changed nothing"
    try:
        path.write_text(mutated, encoding="utf-8")
        passed, output = run_tests(tests, python)
    finally:
        path.write_text(original, encoding="utf-8")
        # Belt and braces: a stale pyc from the mutated file would let the
        # next mutation run code that no longer exists on disk.
        for cache in ROOT.rglob("__pycache__"):
            if ".venv" not in str(cache):
                for item in cache.glob("*.pyc"):
                    item.unlink(missing_ok=True)
    if not passed:
        return "DETECTED", output[-1] if output else "tests failed"

    # The named file is the fast check and the one that ought to catch it.
    # Before calling anything a survivor, run the whole suite that file
    # belongs to, because "this test file does not catch it" and "nothing
    # catches it" are different claims and only the second is a hole.
    suite = tests.split("/")[0] + "/tests"
    if suite != tests:
        try:
            path.write_text(mutated, encoding="utf-8")
            passed_suite, suite_output = run_tests(suite, python)
        finally:
            path.write_text(original, encoding="utf-8")
            for cache in ROOT.rglob("__pycache__"):
                if ".venv" not in str(cache):
                    for item in cache.glob("*.pyc"):
                        item.unlink(missing_ok=True)
        if not passed_suite:
            return "ELSEWHERE", (suite_output[-1] if suite_output
                                 else "caught by the wider suite")
    if name in EQUIVALENT:
        return "EQUIVALENT", EQUIVALENT[name][:60]
    return "SURVIVED", output[-1] if output else "tests passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--list", action="store_true",
                        help="print the mutations and exit")
    parser.add_argument("--only", help="run mutations whose name contains this")
    args = parser.parse_args()

    if args.list:
        for name, relative, find, _, tests in MUTATIONS:
            print("{:22} {:52} {}".format(name, relative, tests))
        return 0

    python = interpreter()
    chosen = [m for m in MUTATIONS
              if not args.only or args.only in m[0]]
    print("mutating with {}".format(python))
    print("{} mutations\n".format(len(chosen)))

    results = []
    for name, relative, find, replace, tests in chosen:
        started = time.time()
        verdict, detail = apply_one(name, relative, find, replace, tests,
                                    python)
        results.append((name, verdict))
        print("{:22} {:9} {:>6.1f}s  {}".format(
            name, verdict, time.time() - started, detail[:60]))

    survived = [name for name, verdict in results if verdict == "SURVIVED"]
    skipped = [name for name, verdict in results if verdict == "SKIPPED"]
    detected = [name for name, verdict in results if verdict == "DETECTED"]
    elsewhere = [name for name, verdict in results if verdict == "ELSEWHERE"]
    equivalent = [name for name, verdict in results
                  if verdict == "EQUIVALENT"]
    print()
    print("{} detected by the named file, {} detected elsewhere in the "
          "suite, {} survived, {} skipped".format(
              len(detected), len(elsewhere), len(survived), len(skipped)))
    if elsewhere:
        print("caught, but not by the test file named for them, which is "
              "worth knowing when that file is the documented guard: "
              "{}".format(", ".join(elsewhere)))
    if skipped:
        print("skipped mutations no longer match the source, which means "
              "the code moved: {}".format(", ".join(skipped)))
    if equivalent:
        print("{} equivalent mutant(s), which cannot be killed because they "
              "change no behaviour:".format(len(equivalent)))
        for name in equivalent:
            print("  {}: {}".format(name, EQUIVALENT[name]))
    if survived:
        print("SURVIVORS, each one a hole in the suite: {}".format(
            ", ".join(survived)))
        return 1
    return 0 if not skipped else 2


if __name__ == "__main__":
    raise SystemExit(main())
