# OAS queue dashboard

A read-only dashboard for the [open-anesthesia-sim](https://github.com/stuthedew/open-anesthesia-sim) docket: items added against items cleared, by lane, plus the branches in flight. A scheduled GitHub Actions workflow rebuilds the data every 15 minutes and publishes it with GitHub Pages. An open tab checks for new data every 5 minutes, so it stays current without reloading.

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

## Preview locally

```sh
python3 extract.py                      # writes site/data/snapshot.json
python3 -m http.server -d site 8000     # then open http://localhost:8000
```

## How it counts

- **New**: items whose `added:` date falls in the range. **Cleared**: `done` or `dropped` items whose `closed:` date falls in it. **Open**: `untriaged`, `ready`, `needs-decision` or `blocked`.
- **Lanes** come from each item's `touches:` against `workflow_paths` in the project's `docket.toml`, the same test `docket next` uses.
- **Branch readings** are docket's own `bin/docket flight` and `stranded` output. Every run cross-checks the open count against `bin/docket digest`, and the page flags a mismatch.

## Notes

- The site is public, like the repository it reads. A `noindex` tag keeps it out of search results.
- GitHub switches off schedules in public repositories after 60 days without repository activity. The `keepalive` job makes an empty commit after 50 quiet days so that never happens.
