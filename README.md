# OAS queue dashboard

A read-only dashboard for the [open-anesthesia-sim](https://github.com/stuthedew/open-anesthesia-sim) docket: the open queue day by day with what was added and cleared on each of them, by lane, plus the branches in flight. A scheduled GitHub Actions workflow rebuilds the data every 15 minutes and publishes it with GitHub Pages. An open tab checks for new data every 5 minutes, so it stays current without reloading.

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
- **The y scale** starts at zero whenever the drawn band comes near it, and floats up off zero only when anchoring there would flatten a short range's bands into a sliver. The value at each end of the line is labeled, so the level reads without the axis.
- **Filed** in the items table is how many times an issue has come up: the item itself, plus each capture `bin/docket new` matched to it and a session let stand, read from the item's `recurrences:` field. This mirrors docket's `model.live_recurrences` and `model.recurrence_count`: an entry reads `DATE PL-XXXX`, a match a session later judged wrong carries a `withdrawn DATE PL-XXXX` tail and counts for nothing, a tail that does not read as exactly those three words leaves the entry live, and one capture recorded twice counts once. The item is itself the first filing, so a field with two live entries reads `3×`.
- **Branch readings** are docket's own `bin/docket flight` and `stranded` output. Every run cross-checks the open count against `bin/docket digest`, and the page flags a mismatch.

## Notes

- The site is public, like the repository it reads. A `noindex` tag keeps it out of search results.
- GitHub switches off schedules in public repositories after 60 days without repository activity. The `keepalive` job makes an empty commit after 50 quiet days so that never happens.
