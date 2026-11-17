[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/0xnici/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/0xnici/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

# GTA VI Twitch CCU forecast — make.fun entry

Entry for the make.fun competition **gta6-twitch-ccu-forecast-01**: a program
that forecasts, for each of hours 2–24 of Grand Theft Auto VI's release day
(2026-11-19, UTC), five quantiles (5/25/50/75/95%) of the concurrent viewers
in the game's Twitch category. Scoring is the mean pinball loss on the log
scale against the recorded day; a paid place needs a lower loss than the
best house entry.

## How it works

`main.py` (Python 3.13, standard library only, no network) reads one case
file and writes one forecast file, in the format the competition specifies.

The method is **reference-class forecasting over the launches shipped
inside the case itself**. Every case lists past big launches
("comparables") with their full hourly Twitch series (SullyGnome hourly
category averages, per the kit's data notice). For each comparable the
program builds its release-day profile — the log ratio of each hour's
viewers to that launch's own first-hour count — and then weights the
profiles by how much each launch resembled the target *at the checkpoint*,
using only evidence available by then:

- the size of the first-hour count (log scale),
- the category's average viewers over the last three hours before the
  release day, relative to the first hour,
- the busiest of the sixteen hours before the release day, relative to
  the first hour.

Those three numbers separate the two shapes a launch day takes: a rolling
midnight release (already playable across New Zealand, Australia, Asia and
Europe by 00:00 UTC — Grand Theft Auto VI's pattern, per the kit's own
comparable notes: New Zealand first, 2026-11-18T11:00Z) has a high,
evening-cresting profile, while a single global unlock late in the UTC day
sits near zero until the unlock hour. A Gaussian kernel over the three
gaps (bandwidths 0.9 / 1.0 / 1.4 log units, floor 0.005) turns the gaps
into weights; each hour's forecast is the weighted empirical quantiles of
the reference log ratios, blended 25% toward a weighted normal fit, and
exponentiated back onto the target's first-hour count.

## Validation

There is no local grade for this competition (the server grades), so the
method was validated by leave-one-out over the 37 launch comparables in
the kit's practice cases: each launch was forecast by the same program
with itself removed from the reference set, and scored with the
competition's pinball loss.

| reference set | this program | flat-persistence baseline |
| --- | --- | --- |
| launches already live at hour 1 (n=22) | **0.213** | 0.251 |
| all launches (n=37) | **0.424** | 0.930 |

The bandwidths and blend sit on a flat optimum of that validation (the
top dozen configurations span 0.210–0.214 on the live subset), rather
than on a tuned spike. Free-text unlock descriptions and the hour-1
channel count were also tried as extra signals; neither improved the
validation, so both were left out.

## Data sources

- Case data (comparables, histories, the final case's recording): the
  competition kit, `gta6-twitch-ccu-forecast-01` (make.fun). Viewer
  figures are SullyGnome's hourly Twitch category averages as quoted in
  the kit's `input/NOTICE.txt`; the final case is make.fun's own
  minute-level recording of Twitch's public directory count for the
  Grand Theft Auto VI category (Twitch game id 1867279146).
- Release pattern of the target: the kit's comparable entry for the
  Grand Theft Auto VI category ("releases 2026-11-19, rolling midnight
  local (New Zealand first, 2026-11-18T11:00Z)"), consistent with
  Rockstar's launches of Red Dead Redemption 2 and Grand Theft Auto V
  (rolling midnight local) — the former is itself one of the kit's
  practice cases.

## Layout

- `main.py` — the entry program.
- `LICENSE` — MIT, from the competition kit's starter.
- `.makefun/owner.json` — the account wallet that signs the entry.
