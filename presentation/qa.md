# Q&A prep sheet

Each member's two "be ready to answer" questions from the project brief, each answered in two sentences.

## Natalie King

**What is the difference between a bad record and a repeat failure?**
A bad record is a single row that cannot be trusted, such as a missing serial or the date `2026-13-05`, so the loader rejects it with its line number and it is never saved. A repeat failure is a pattern across good, saved visits: the same serial number reaching `repeat_failure_count` visits inside `repeat_failure_window_days`, which the rules flag in the report.

**What happens when a part number arrives in a new format?**
It fails the `part_number_pattern` check, so the row is rejected with a reason such as `part_number does not match ^P-\d{4}$ (PN-20310)` and nothing about it is saved. If the new format is genuine, a manager changes `part_number_pattern` in `data/settings.json` and re-runs the file, with no code change.

## Julian Marchington

<!-- TODO: Julian's two questions from the brief -->

## Shreyaa Lakshmivaragan

<!-- TODO: Shreyaa's two questions from the brief -->

## Harshitha Reddy Gundavarapu

<!-- TODO: Harshitha's two questions from the brief -->
