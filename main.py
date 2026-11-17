"""Forecast the release-day Twitch audience of a game launch, hour by hour.

Written for the make.fun competition gta6-twitch-ccu-forecast-01. The grader
runs this program once per case inside a sandbox with no network: the case
file carries everything recorded up to the end of the release day's first
hour, and the program writes, for each of hours 2..24 of that day, five
quantiles (5%, 25%, 50%, 75%, 95%) of the hour's concurrent-viewer count in
the game's Twitch category. Scoring is the mean pinball loss on the log
scale, so the program's job is to state an honest predictive distribution
for each hour, not a single guessed curve.

Method: reference-class forecasting over the launches shipped inside the
case itself. Every case lists past big launches ("comparables"), each with
its full hourly viewer series from two weeks before its release day to two
days after. For each comparable the program builds its release-day profile:
the log ratio of each hour's viewers to that launch's own first-hour count.
A launch whose game was already playable around the world by 00:00 UTC
(a rolling midnight release) has a nearly flat profile that crests again in
the evening; a launch with one global unlock late in the UTC day has a
profile that sits near zero until the unlock and then jumps a hundredfold.
The target's first-hour count anchors the level; which profiles resemble
the target is judged from evidence available at the checkpoint:

  * the size of the first-hour count itself (log scale),
  * how busy the category already was in the last three hours before the
    day began, relative to the first hour (a rolling release is already
    drawing a crowd in New Zealand, Australia and Asia by then),
  * the busiest hour of the sixteen before the day began, relative to the
    first hour.

Each comparable is weighted by a Gaussian kernel over those three gaps
(bandwidths 0.9, 1.0 and 1.4 log units, with a small floor so no launch is
ever fully ignored). The forecast for an hour is the weighted empirical
quantiles of the reference log ratios at that hour, blended 25% toward a
weighted normal fit of the same ratios, then exponentiated back onto the
target's first-hour count. The kernel bandwidths and the blend were chosen
by leave-one-out validation over the 37 launches in the kit's practice
cases: scoring every launch with a forecaster that never sees it, this
method's mean pinball loss on the launches that were already live at their
first hour (the regime the final case belongs to) is about 0.21, against
about 0.25 for a flat-persistence forecast and about 0.42 for an
unweighted pool of every launch's profile scored the same way.

Only the Python standard library is used, the program is a pure function
of its input file, and it runs in well under a second per case.
"""

import json
import math
import os
from datetime import date, timedelta
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# Kernel bandwidths for the three similarity gaps, in log units, and the
# floor every reference launch keeps so the pool never collapses onto one
# or two launches.
BW_LEVEL = 0.9
BW_LATE3 = 1.0
BW_PREMAX = 1.4
WEIGHT_FLOOR = 0.005
# Share of the weighted normal fit blended into the empirical quantiles.
NORMAL_BLEND = 0.25
# Spread of the fallback forecast (used only if a case ships no usable
# reference launch): a log random walk around the first hour.
FALLBACK_SIGMA = 0.15


def round2(value):
    """Round to two decimals, half up, returning an int when whole so the
    JSON text matches the format the grader's examples use."""
    scaled = value * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    out = whole / 100.0
    return int(out) if out == int(out) else out


def norm_ppf(p):
    """The standard normal's quantile at p (Acklam's rational fit)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    if p < 0.02425:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p > 1.0 - 0.02425:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


def day_before(day_text):
    """The ISO date (YYYY-MM-DD) of the day before the given one."""
    y, m, d = int(day_text[0:4]), int(day_text[5:7]), int(day_text[8:10])
    return (date(y, m, d) - timedelta(days=1)).isoformat()


def hourly_series(points):
    """Collapse a list of points to {(date, hour): mean viewers}.

    Points carry their timestamp under 'from' (hourly series) or 'at'
    (raw history); an hour's figure is the mean of the points inside it,
    which is the identity for series that are already hourly and the
    hour's mean of minute reads for the final case's recording.
    """
    sums = {}
    counts = {}
    for point in points or []:
        stamp = point.get("from") or point.get("at")
        if not stamp or len(stamp) < 13:
            continue
        key = (stamp[0:10], int(stamp[11:13]))
        sums[key] = sums.get(key, 0.0) + float(point.get("viewers") or 0)
        counts[key] = counts.get(key, 0) + 1
    return {key: sums[key] / counts[key] for key in sums}


def checkpoint_features(series, day_text, first_hour):
    """The three similarity features of a launch, from data at its checkpoint.

    series maps (date, hour) -> viewers for the days around the release;
    day_text is the release date; first_hour is the day's hour-1 count.
    Returns (log level, log late-evening ratio, log pre-window peak ratio),
    or None when the pre-window is missing entirely.
    """
    prev = day_before(day_text)
    pre = [series[(prev, h)] for h in range(8, 24) if (prev, h) in series]
    late3 = [series[(prev, h)] for h in (21, 22, 23) if (prev, h) in series]
    if not pre or not late3 or first_hour <= 0:
        return None
    return (
        math.log(max(1.0, first_hour)),
        math.log(max(0.02, (sum(late3) / len(late3)) / first_hour)),
        math.log((max(pre) + 1.0) / (first_hour + 1.0)),
    )


def reference_profiles(case):
    """Build (features, log-ratio profile) for every usable comparable.

    A comparable counts as a launch reference when its release day is
    (nearly) fully sampled; the target's own pre-release category entry,
    whose 'release day' is a trailer premiere with a handful of points,
    falls away on that rule, as does any entry named after the target
    game itself.
    """
    game_name = (case.get("game") or {}).get("name") or ""
    refs = []
    for comp in case.get("comparables") or []:
        name = comp.get("name") or ""
        if game_name and name.startswith(game_name):
            continue
        day_text = (comp.get("day_start") or "")[0:10]
        if len(day_text) != 10:
            continue
        series = hourly_series(comp.get("hourly"))
        day = {h + 1: series[(day_text, h)] for h in range(24) if (day_text, h) in series}
        if len(day) < 20 or day.get(1, 0) <= 0:
            continue
        feats = checkpoint_features(series, day_text, day[1])
        if feats is None:
            continue
        base = math.log(max(1.0, day[1]))
        profile = {h: math.log(max(1.0, day[h])) - base for h in range(2, 25) if h in day}
        if len(profile) >= 20:
            refs.append((feats, profile))
    return refs


def similarity_weights(target_feats, refs):
    """Gaussian kernel weights of the reference launches for this target."""
    weights = []
    for feats, _profile in refs:
        d_level = (target_feats[0] - feats[0]) / BW_LEVEL
        d_late3 = (target_feats[1] - feats[1]) / BW_LATE3
        d_premax = (target_feats[2] - feats[2]) / BW_PREMAX
        dist2 = d_level * d_level + d_late3 * d_late3 + d_premax * d_premax
        weights.append(max(WEIGHT_FLOOR, math.exp(-0.5 * dist2)))
    return weights


def weighted_quantile(pairs, tau):
    """The tau quantile of (value, weight) pairs, linearly interpolated."""
    ordered = sorted(pairs)
    total = sum(w for _v, w in ordered)
    goal = tau * total
    acc = 0.0
    prev_value, prev_acc = ordered[0][0], 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= goal:
            if acc == prev_acc:
                return value
            frac = (goal - prev_acc) / (acc - prev_acc)
            return prev_value + frac * (value - prev_value)
        prev_value, prev_acc = value, acc
    return ordered[-1][0]


def forecast_from_refs(hours, levels, refs, weights):
    """Weighted empirical log-ratio quantiles, blended toward a normal fit."""
    rows = []
    for hour in hours:
        pairs = [(profile[hour], w) for (_f, profile), w in zip(refs, weights) if hour in profile]
        total = sum(w for _v, w in pairs)
        mean = sum(v * w for v, w in pairs) / total
        var = sum(w * (v - mean) ** 2 for v, w in pairs) / total
        sd = math.sqrt(max(var, 1e-9))
        quantiles = []
        for tau in levels:
            emp = weighted_quantile(pairs, tau)
            fit = mean + norm_ppf(tau) * sd
            quantiles.append((1.0 - NORMAL_BLEND) * emp + NORMAL_BLEND * fit)
        rows.append((hour, quantiles))
    return rows


def forecast_fallback(hours, levels):
    """Flat level, log random-walk spread: used only when a case carries
    no usable reference launch at all."""
    rows = []
    for hour in hours:
        spread = FALLBACK_SIGMA * math.sqrt(hour - 1)
        rows.append((hour, [norm_ppf(tau) * spread for tau in levels]))
    return rows


def forecast_case(case):
    levels = [float(t) for t in case["levels"]]
    known = next((k for k in case.get("known") or [] if k.get("hour") == 1), None)
    if known is None:
        raise ValueError("case has no hour-1 print")
    first_hour = max(1.0, float(known.get("viewers") or 0))
    hours = [int(row["hour"]) for row in case["forecast"]]

    day_text = (case.get("day_start") or "")[0:10]
    series = hourly_series(case.get("history_hourly") or [])
    if not series:
        series = hourly_series(case.get("history"))
    # The known first hour belongs to the target's own series as well.
    series[(day_text, 0)] = first_hour
    target_feats = checkpoint_features(series, day_text, first_hour)

    refs = reference_profiles(case)
    if refs and target_feats is not None:
        weights = similarity_weights(target_feats, refs)
        log_rows = forecast_from_refs(hours, levels, refs, weights)
    else:
        log_rows = forecast_fallback(hours, levels)

    out_rows = []
    for hour, log_qs in log_rows:
        qs = []
        for log_q in log_qs:
            value = first_hour * math.exp(log_q)
            value = min(max(value, 0.01), 1e9)
            qs.append(round2(value))
        # The five quantiles must never decrease along the row.
        for i in range(1, len(qs)):
            if qs[i] < qs[i - 1]:
                qs[i] = qs[i - 1]
        out_rows.append({"hour": hour, "q": qs})
    return {"hours": out_rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        result = forecast_case(case)
        text = json.dumps(result, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / (path.stem + ".out")).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
