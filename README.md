# OAS queue dashboard

A read-only dashboard for the [open-anesthesia-sim](https://github.com/stuthedew/open-anesthesia-sim) docket: the open queue day by day with what was added and cleared on each of them, by lane and for defects alone, plus the branches in flight. A scheduled GitHub Actions workflow rebuilds the data every 15 minutes and publishes it with GitHub Pages. An open tab checks for new data every 5 minutes, so it stays current without reloading.

Nothing in open-anesthesia-sim refers to this repository. The workflow only clones it.

## Set up (once)

```sh
git init -b main && git add . && git commit -m "Queue dashboard"
gh repo create oas-queue-dashboard --public --source . --push
gh api -X POST "repos/{owner}/{repo}/pages" -f build_type=workflow
gh workflow run refresh.yml
```

The site appears at `https://<your-username>.github.io/oas-queue-dashboard/` when the run finishes, usually within two minutes. If the first run's deploy job failed because Pages was not switched on yet, run the workflow again. Without `gh`, switch Pages on at Settings > Pages > Build and deployment > Source: GitHub Actions.

## Change the cadence

Edit the first `cron` line in `.github/workflows/refresh.yml`, and set `INTERVAL_MINUTES` in the same file to match; the page uses it to decide when data is late. GitHub's shortest schedule is every 5 minutes, and scheduled runs are best effort: they can start late, especially near the top of the hour.

## Change the report's time zone

Days on this page are calendar days in `REPORT_TIMEZONE` in `.github/workflows/refresh.yml`, which defaults to `America/Chicago`. Set it to any IANA zone name (`--timezone` does the same when running `extract.py` by hand); a name the zone database does not know stops the run before it clones anything. The page shows the zone in its footer.

The workflow runs on UTC, so without this the report's "today" would start mid-evening Central and a day's column would open before that day began here. Item `added:` and `closed:` dates are bare calendar dates carrying no zone of their own, so this setting decides only which day is the last one on the chart and in the header, not how an individual item is dated.

## Preview locally

```sh
python3 extract.py                      # writes site/data/snapshot.json
python3 -m http.server -d site 8000     # then open http://localhost:8000
```

## How it counts

- **Days**: calendar days in the report's time zone (see above), so the newest column is today here, not today in UTC.
- **New**: items whose `added:` date falls in the range. **Cleared**: `done` or `dropped` items whose `closed:` date falls in it. **Open**: `untriaged`, `ready`, `needs-decision` or `blocked`.
- **Lanes** come from each item's `touches:` against `workflow_paths` in the project's `docket.toml`, the same test `docket next` uses.
- **The open line** on each chart is the queue itself, not a running total: how many items stood open at the end of that day, counted from the item files rather than accumulated, so the last point is always the headline open count. The band above it is what was filed that day and the band below is what was cleared, so the line steps up wherever the upper band is thicker. An item with no `added:` date sits in the line from the first day of any range; one cleared without a `closed:` date, or carrying a status this page does not know, is left out of the line altogether, because an arrival whose departure cannot be placed in time would shift every earlier day by one. The banner flags unknown statuses when they appear.
- **Defects**: the product and workflow defect charts hold only items whose `classes:` include `defect`, docket's label for a bug, whatever else they carry. `defect, safety` counts; `safety` or `science` alone does not, and neither does `housekeeping`, `feature` or any other class without `defect`. Everything else about them follows the lane charts' rules, over each item's current classes. A capture carries no classes until it is triaged, so a new defect joins these charts on its `added:` date once triage classes it, and the latest days can rise after the fact. Crossing and unplaced defects are counted in the line beneath the two charts.
- **The y scale** starts at zero whenever the drawn band comes near it, and floats up off zero only when anchoring there would flatten a short range's bands into a sliver. The value at each end of the line is labeled, so the level reads without the axis.
- **Added per cleared**, the bar chart under each chart, is one day's new count divided by that day's cleared count, both counted as above. Above 1 the queue grew that day; below 1 it shrank. The scale is logarithmic and centered on 1, so adding twice what was cleared sits as far above the line as clearing twice what was added sits below it; each gridline doubles or halves, out to at most 16 or 1/16, and a day beyond that is pinned to the edge. A day that added items but cleared none has no finite ratio: its bar runs to the top and reads ∞. A day that added nothing but cleared something reads 0 and runs to the bottom. A day with neither has no bar. The "Last N days" line above each chart gives the same ratio over that window.
- **Running totals**, the third chart on each defect panel, count that lane's defects added and cleared since the store began, up to each day, so the gap between the two lines is how many stood open at the end of that day: the same items and the same count as the open line above it. An item with no `added:` date counts as added before any range; one cleared without a `closed:` date, or carrying an unknown status, is left out of both lines, as it is left out of the open line. The slope of the added line is how fast new defects arrive, whatever clearing is doing. Like the charts above, the scale starts at zero unless that would squeeze a short range into a sliver.
- **Defects by feature** counts defects (as above, all lanes) whose `added:` date falls in the range, grouped by the item's `feature:` field, with items that carry none grouped as "no feature set". The ten largest groups are listed, most first; the running percentage is each row's share of all the range's new defects, added up down the list. The week columns split each row's count into whole seven-day weeks ending on the range's last day, at most eight; a range's leading odd days count in the totals but in no column.
- **Filed** in the items table is how many times an issue has come up: the item itself, plus each capture `bin/docket new` matched to it and a session let stand, read from the item's `recurrences:` field. This mirrors docket's `model.live_recurrences` and `model.recurrence_count`: an entry reads `DATE PL-XXXX`, a match a session later judged wrong carries a `withdrawn DATE PL-XXXX` tail and counts for nothing, a tail that does not read as exactly those three words leaves the entry live, and one capture recorded twice counts once. The item is itself the first filing, so a field with two live entries reads `3×`.
- **Tags** in the items table are the item's `classes:` field, shown with `defect` first and the rest A-Z. Sorting on it puts items carrying `defect` ahead of all others, then orders by that same list, with untagged items (untriaged captures, mostly) last either way; rows with the same tags keep the tab's own order. It changes no count.
- **Branch readings** are docket's own `bin/docket flight` and `stranded` output. Every run cross-checks the open count against `bin/docket digest`, and the page flags a mismatch.

## Notes

- The site is public, like the repository it reads. A `noindex` tag keeps it out of search results.
- GitHub switches off schedules in public repositories after 60 days without repository activity. The `keepalive` job makes an empty commit after 50 quiet days so that never happens.
