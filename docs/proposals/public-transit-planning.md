# Proposal: public transit and accessible journey planning

[Documentation index](../README.md) · [Contribution guide](../../CONTRIBUTING.md)

Status: draft for maintainer feedback. This document proposes 12 workflows and
specifies two initial pilots. No runnable tasks, observed endpoint matchers,
human reference runs, container validation, or model results are included yet.

## Purpose

Evaluate whether a browser agent preserves a traveller's constraints while
using public transit websites: accessibility, arrival time, walking limits,
permitted transport modes, connections, and the correct timetable product.
The proposed category is `public-transit-planning`.

The existing travel tasks include flights, intercity booking, and accommodation.
An initial review of the task directories and issue proposals at commit
`c840962` found no dedicated public-transit-planning category. Maintainers should
confirm overlap and category eligibility before the full set is implemented.

The first implementation would evaluate initiation of a correctly configured
search or retrieval request. A matching search request does not establish that
the returned itinerary is accessible or satisfies the constraints. Likewise, a
matching timetable request does not establish that a file was saved. Tasks
requiring either outcome need additional evidence and an agreed scoring path.

## Candidate workflows

Each row is a candidate, subject to browser inspection and scoring feasibility.
Task IDs and corpus placement have not been assigned.

| Candidate | Service | Requested workflow | Distinction to validate |
| --- | --- | --- | --- |
| T01, pilot | TfL | Request a full step-free journey with an arrival deadline | Arrival versus departure time; full step-free versus platform-only access |
| T02 | TfL | Request a least-walking journey with a walking limit | Route preference and walking limit must both be retained |
| T03 | TfL | Request a journey using only specified transport modes | The permitted mode set must be exact |
| T04 | TfL | Request a journey via an intermediate location, preferring fewer changes | Via location and route preference must survive submission |
| T05, pilot | BART | Request a one-way fare for a station pair and date | Station identity, direction, one-way selection, and date |
| T06 | BART | Request a specified line's weekend timetable | Weekend versus weekday product; correct line |
| T07 | BART | Request the BART–Caltrain connection timetable | Connection timetable versus a single-agency timetable |
| T08 | HSL | Request a car plus public transport Park & Ride journey | Car-to-transit combination and parking transfer |
| T09 | HSL | Request a bicycle plus public transport journey | Bike parking plus transit versus cycling the entire journey |
| T10 | Nysse | Request an accessible journey with adjusted walking settings | Wheelchair setting and walking configuration |
| T11 | Nysse | Request a line timetable for a weekday, direction, and stop segment | Line identity, direction, weekday, and segment |
| T12 | Nysse | Request a specified stop's planned weekly timetable | Planned schedule versus live departures; correct stop ID |

Source pages establishing the candidate controls and products:

- [TfL Journey Planner](https://tfl.gov.uk/plan-a-journey/) and
  [accessible journey guidance](https://tfl.gov.uk/help-with-travel/accessible-and-step-free-travel/plan-an-accessible-journey).
- [BART Fare Calculator](https://www.bart.gov/tickets/calculator),
  [PDF timetables](https://www.bart.gov/schedules/pdfs), and
  [transit connections](https://www.bart.gov/guide/transit).
- [HSL Park & Ride browser instructions](https://www.hsl.fi/en/travelling/park--ride).
- [Nysse Journey Planner manual](https://www.nysse.fi/en/journey-planner-manual.html).

HSL and Nysse share the Digitransit platform. Their proposed workflows therefore
exercise different capabilities; domain count alone is not evidence of interface
diversity. If two candidates reduce to the same interaction and scoring pattern,
replace one rather than counting a station or date substitution as a new workflow.

## Pilot T01: TfL accessible journey request

Entry page: <https://tfl.gov.uk/plan-a-journey/>.

Proposed instruction, with the date filled in before creating `task.json`:

> Request a public transport journey from Westminster Underground Station to
> Stratford Underground Station on the specified date, arriving by 10:00 London
> local time, with full step-free access. Complete the journey search.

Before implementation, verify that both locations can be selected unambiguously
and that the date is within the planner's supported window. Record the exact
date and `Europe/London` time zone in the task evidence. The date policy below
must be resolved before treating this as a maintained benchmark task.

Capture the request produced by completing the form, and map its observed fields
to origin, destination, date, time, arrival/departure mode, public transport, and
full step-free access. Determine the URL, HTTP method, and parameter/body encoding
from that capture. No endpoint or field name is assumed in this proposal.

The matcher should accept the correct request and reject requests with a wrong
station, reversed direction, wrong date/time, departure mode instead of arrival,
or absent/platform-only accessibility. Test the default page load and incomplete
form states to establish that they cannot trigger success early.

## Pilot T05: BART fare request

Entry page: <https://www.bart.gov/tickets/calculator>.

Proposed instruction, with the date filled in before creating `task.json`:

> Use BART's Fare Calculator to request a one-way fare from Embarcadero to
> San Francisco International Airport for the specified travel date.

Verify the selectable station identities and supported date range in a fresh
browser session. Capture the actual fare request and determine how origin,
destination, one-way selection, and date are represented. The terminal outcome
is the configured fare request; extracting a correct price is a separate outcome.

Negative cases should include the other airport, reversed direction, round-trip
selection, a wrong date, and a request missing a required choice. If the website
calculates the fare entirely in the browser without a suitable request, report
that limitation and replace the pilot or agree on another scoring mechanism.

## Date and timetable maintenance

Transit search windows, schedules, and accessibility availability change.
For the initial pilots, choose an explicit supported date and record the capture
time, browser time zone, task hash, and repository commit. Do not use an unanchored
instruction such as "tomorrow".

Before publishing the suite, agree with maintainers on a date policy: explicitly
version and refresh dated tasks, or implement a supported run-date mechanism that
records the resolved date for judging and rescoring. A rolling-date mechanism is
not part of this proposal and must not be assumed to exist. Pin timetable product
identity and record its validity period; mark expired tasks for revalidation.

## Implementation and evidence checklist

For each pilot, then for each accepted expansion task:

1. Complete the website workflow in a fresh browser through the official
   ClawBench runtime. Record the selected controls, terminal request, and any
   site or browser limitations. Separate human operation from scripted operation.
2. Create a task conforming to the shared
   [task schema](../../test-cases/task.schema.json), including metadata, a precise
   instruction, an observed `eval_schema`, and a time limit in minutes. Add
   `extra_info/` files only when the workflow needs them.
3. Validate the JSON and supporting file references. Exercise the runtime's
   matcher with the captured request and meaningful near misses, including wrong
   method/host/path, missing constraints, and duplicate/conflicting parameters
   where applicable. Confirm no preload or intermediate request passes early.
4. Retain a reproducible positive browser run and a negative run with a key choice
   changed. Capture sanitized request fixtures and their provenance. Keep secrets
   and unrelated traffic out of published evidence.
5. Record human completion time if measured. Keep watchdog limits, scripted
   durations, human timing, and model performance separate.
6. Agree on any required agent and Stage 2 judge runs, then report their actual
   results and failures. A `--no-judge` run establishes only Stage 1 evidence.
7. Update the category README with task coverage, evidence, limitations, and the
   date-maintenance policy, and add an Unreleased changelog entry.

The [getting started guide](../getting-started.md) lists Python 3.11+, `uv`, and
a running Docker or Podman engine. Human validation can use
`uv run clawbench-run <case-directory> --human --no-judge --no-upload`
after a real task directory exists. This skips model judging and uploads;
ordinary runtime setup, including disposable-mail setup, still applies.
See the [CLI reference](../cli.md) for agent and judge configuration and the
[trace cookbook](../trace-cookbook.md) for output artifacts.

## Scope and maintainer questions

1. Does this count as a distinct new category under the contribution policy,
   given its relationship to the existing travel tasks?
2. Is request-initiation scoring appropriate for these workflows, or should any
   require itinerary/price/file outcome validation?
3. Where should accepted tasks live: V1 as the contribution guide directs, V2,
   or an isolated suite such as `test-cases/public-transit-planning/`?
4. What date policy, evidence, human timing, model runs, and ongoing maintenance
   should be required before the category is ready for review?
5. If at least ten distinct reviewed tasks are accepted, which publication and
   additional research, writing, review, or maintenance expectations apply to
   co-author consideration? The [README](../../README.md#contributing) refers to
   the next paper revision, while
   [CONTRIBUTING.md](../../CONTRIBUTING.md#recognition-for-contributors) refers to
   a relevant follow-up paper or workshop submission. Authorship and category
   acceptance remain maintainer decisions.

The proposed sequence is scope feedback, two validated pilots, then expansion
to the agreed full category in the same draft PR. The reviewed
[environmental-observation contribution](https://github.com/TIGER-AI-Lab/ClawBench/pull/378)
provides a precedent for reviewing pilots and adding the rest together.

Research and proposal drafting used Codex assistance. The website controls and
official documentation were inspected; no human timing, live ClawBench
interception, completed task implementation, or model evaluation is claimed.
