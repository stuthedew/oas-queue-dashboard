# Instructions for agent sessions

This repository is the queue dashboard for open-anesthesia-sim. `README.md` says
what each panel counts and how to preview the page.

## Merging

Merge your own pull request yourself, without asking the owner, once the work
is checked (project owner, 2026-11-22). Before you merge:

1. Build a snapshot from the current open-anesthesia-sim main and preview the
   page, as `README.md` § "Preview locally" says. Check that `extract.py`
   reports a match between its open count and docket's.
2. Check the change in a browser at desktop width and at phone width.
3. Make sure the pull request has no merge conflict and that every check that
   ran on it passed.

Use a squash merge, with the pull request number at the end of the title, as
earlier merges have it. After merging, check that the refresh run on main
succeeded and that the live page serves the change. Then tell the owner it is
merged and what they will see.

This covers pull requests a session opened. A pull request opened by anyone
else, Dependabot included, still waits for the owner.
