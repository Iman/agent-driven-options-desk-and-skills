"""The artifact directory as retrievable documents.

Artifacts are JSON, often large, and a language model reading one whole is
mostly reading strike ladders. This turns each into a short document that
carries what a question is usually about: what it is, when it was made,
whether it is degraded, and the handful of numbers a person would quote.

The full artifact is always one path away, and the path is in the document,
so nothing here prevents a caller from reading the detail when the detail
is the point.
"""

import json
from pathlib import Path

KINDS = ("chain", "greeks", "exposure", "strategy", "comparison",
         "simulation", "backtest")


def _load(path):
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (ValueError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _percent(value, digits=2):
    return "n/a" if value is None else "{:.{d}f}%".format(value * 100,
                                                          d=digits)


def _meta(payload):
    """The artifact's envelope, or an empty one.

    The envelope carries the degraded flag, so it is read on every path
    that describes an artifact and is the one part that cannot be allowed
    to fail. `payload.get("meta", {})` is not enough: it returns the value
    when the key is present and null, so the default never fires, and a
    meta that is present but is not an object fails the same way.
    """
    meta = payload.get("meta")
    return meta if isinstance(meta, dict) else {}


def _summarise(kind, payload, path):
    """One short paragraph per artifact, in the terms a person would use.

    Never raises for any JSON object, which is all _load lets through. What
    it cannot read it says it cannot read, because this runs over every
    file in the directory in one pass and an exception here costs the
    caller every other artifact as well.
    """
    meta = _meta(payload)
    header = "{} for {}{}, generated {}".format(
        kind, payload.get("underlying", "unknown"),
        " expiry {}".format(payload["expiry"]) if payload.get("expiry")
        else "", meta.get("generated_utc", "unknown"))
    lines = [header]

    if meta.get("degraded"):
        lines.append("DEGRADED: {}".format(meta.get("degraded_reason")))
    for note in (meta.get("notes") or [])[:3]:
        lines.append("note: {}".format(note))

    # The lines above are the ones the reporting rules turn on: what this
    # is, when it was made, and whether it is degraded. They are built
    # before this point and kept whatever happens next.
    #
    # Nothing validates an artifact on the way in. records() accepts any
    # JSON object whose filename prefix is a known kind, so a file written
    # by an older schema, or by something that is not the desk at all,
    # reaches here intact. Reading a field it does not have used to raise
    # through context_for, which summarises the whole directory in one
    # pass: one bad file and the model was told nothing about any
    # underlying. Losing this artifact's numbers is the smaller failure,
    # and saying so is what keeps it from reading as a clean artifact.
    try:
        if kind == "chain":
            counts = payload.get("counts", {})
            lines.append(
                "spot {} as of {}. {} contracts, {} with a usable implied "
                "volatility, {} without.".format(
                    payload.get("spot"), payload.get("spot_asof"),
                    len(payload.get("contracts", [])), counts.get("with_iv"),
                    counts.get("without_iv")))
        elif kind == "greeks":
            rows = payload.get("rows", [])
            skipped = payload.get("skipped") or {}
            lines.append(
                "{} contracts graded, {} skipped for having no implied "
                "volatility.".format(len(rows), skipped.get("no_iv")))
            if rows:
                spot = payload.get("spot")
                atm = min(rows, key=lambda r: abs(r["strike"] - spot))
                lines.append(
                    "at the money {} strike {}: iv {}, delta {:.4f}, gamma "
                    "{:.5f}, vega {:.2f}, theta {:.3f} per day.".format(
                        atm["type"], atm["strike"], _percent(atm.get("iv")),
                        atm.get("delta", 0), atm.get("gamma", 0),
                        atm.get("vega", 0), atm.get("theta", 0)))
        elif kind == "exposure":
            exposure = payload.get("exposure", {})
            smile = payload.get("smile") or {}
            pain = payload.get("max_pain") or {}
            lines.append(
                "net gamma exposure {:.0f} per one percent move, regime {}. "
                "call wall {}, put wall {}, flip {}. max pain {}. put to call "
                "open interest {}.".format(
                    exposure.get("net_gex", 0), exposure.get("regime"),
                    (exposure.get("call_wall") or {}).get("strike"),
                    (exposure.get("put_wall") or {}).get("strike"),
                    exposure.get("gamma_flip"), pain.get("strike"),
                    exposure.get("put_call_oi_ratio")))
            lines.append(
                "at the money volatility {}, 25 delta risk reversal {}, "
                "expected move {}.".format(
                    _percent(smile.get("atm_iv")),
                    _percent(smile.get("risk_reversal")),
                    smile.get("expected_move")))
            lines.append("assumption: {}".format(exposure.get("assumption")))
        elif kind == "strategy":
            analysis = payload.get("analysis", {})
            lines.append(
                "{} {}: net {}, breakevens {}, max gain {}, max "
                "loss {}.".format(
                    payload.get("strategy"), analysis.get("trade_type"),
                    analysis.get("net_cash"), analysis.get("breakevens"),
                    analysis.get("max_gain"), analysis.get("max_loss")))
            probability = payload.get("probability") or {}
            if probability.get("profit") is not None:
                lines.append("model probability of profit {}.".format(
                    _percent(probability["profit"], 1)))
            friction = payload.get("friction") or {}
            if friction.get("verdict"):
                lines.append("friction {}: {}".format(friction["verdict"],
                                                      friction.get("reason")))
        elif kind == "comparison":
            leader = payload.get("leader") or {}
            lines.append("{} structures ranked, {} excluded. Leader {} at {} "
                         "expected return on capital at risk.".format(
                             payload.get("rankable_count"),
                             payload.get("excluded_count"),
                             leader.get("strategy"),
                             _percent(
                                 leader.get("expected_return_on_risk"), 1)))
            lines.append("criterion: {}".format(payload.get("criterion")))
            lines.append("caveat: {}".format(payload.get("caveat")))
        elif kind == "simulation":
            posterior = payload.get("posterior", {})
            risk = payload.get("risk") or {}
            simulation = payload.get("simulation", {})
            lines.append(
                "horizon {} days, {} paths, converged {}. value at risk "
                "95 {}, expected shortfall 95 {}.".format(
                    simulation.get("horizon_days"), simulation.get("paths"),
                    posterior.get("converged"), _percent(risk.get("var_95")),
                    _percent(risk.get("es_95"))))
            for structure in (payload.get("structures") or [])[:5]:
                lines.append(
                    "{}: probability of profit {} under realised volatility "
                    "against {} under implied.".format(
                        structure.get("strategy"),
                        _percent(structure.get(
                            "realised_vol_probability_of_profit"), 1),
                        _percent(structure.get(
                            "implied_vol_probability_of_profit"), 1)))
        elif kind == "backtest":
            statistics = payload.get("statistics") or {}
            significance = payload.get("significance") or {}
            lines.append(
                "{} over {} trades: win rate {}, mean return on risk {}, "
                "p value {}.".format(
                    payload.get("strategy"), statistics.get("trades"),
                    _percent(statistics.get("win_rate"), 1),
                    _percent(statistics.get("mean_return")),
                    significance.get("p_value")))
            lines.append("honesty: {}".format(payload.get("honesty")))
    except Exception as exc:
        lines.append(
            "detail unavailable: this {} artifact does not match the "
            "current schema, so no number is quoted from it ({}: {}). "
            "Re-run the command that writes it."
            .format(kind, type(exc).__name__, exc))

    lines.append("full artifact: {}".format(path))
    return "\n".join(str(line) for line in lines)


class ArtifactStore:
    """Read only view of the artifact directory, as documents."""

    def __init__(self, directory=None):
        if directory is None:
            from optiondesk.artifacts import artifact_dir

            directory = artifact_dir()
        self.directory = Path(directory)

    def records(self, underlying=None, kinds=None):
        """Every artifact as (kind, payload, path), newest first.

        The sort key stats each file, and the directory is written to by
        the commands while this reads it, so a file can vanish between the
        glob and the stat. That raised FileNotFoundError out of here,
        which is a failure of the whole read rather than of one artifact,
        and it would land on whoever happened to be summarising while a
        refresh ran. A file that is gone sorts last and is then dropped by
        _load, which is what should happen to it.
        """
        if not self.directory.exists():
            return []

        def _age(path):
            try:
                return path.stat().st_mtime
            except OSError:
                return float("-inf")

        out = []
        for path in sorted(self.directory.glob("*.json"), key=_age,
                           reverse=True):
            kind = path.name.split("_")[0]
            if kind not in KINDS or (kinds and kind not in kinds):
                continue
            payload = _load(path)
            if payload is None:
                continue
            if underlying and str(payload.get("underlying", "")).upper() \
                    != underlying.upper():
                continue
            out.append((kind, payload, str(path)))
        return out

    def documents(self, underlying=None, kinds=None):
        """LangChain documents, one per artifact."""
        from langchain_core.documents import Document

        documents = []
        for kind, payload, path in self.records(underlying, kinds):
            documents.append(Document(
                page_content=_summarise(kind, payload, path),
                metadata={
                    "kind": kind,
                    "underlying": payload.get("underlying"),
                    "expiry": payload.get("expiry"),
                    "generated_utc": _meta(payload).get("generated_utc"),
                    "degraded": bool(_meta(payload).get("degraded")),
                    "path": path,
                },
            ))
        return documents

    def context_for(self, underlying=None, kinds=None, limit=12):
        """A single context string, newest first, ready for a prompt."""
        blocks = []
        for kind, payload, path in self.records(underlying, kinds)[:limit]:
            blocks.append(_summarise(kind, payload, path))
        if not blocks:
            return ("No artifacts are on disk for this request. Nothing can "
                    "be answered from data that has not been pulled.")
        return "\n\n".join(blocks)
