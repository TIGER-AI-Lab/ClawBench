# Environmental observation workflows

This proposed category contains 12 public-data browser workflows: two reviewed pilots and ten additions requested by maintainer Perry2004 for PR [#378](https://github.com/TIGER-AI-Lab/ClawBench/pull/378). Released V1/V2 are unchanged.

| Workflow | Requested product and key distinction | Current validation |
|---|---|---|
| `noaa_historical_observed_water_level` | Boston six-minute observed water levels; metres, MLLW, GMT. Observations, not predictions. | Pilot: official-base UI request verified |
| `usgs_water_year_daily_mean_discharge` | Charles River water-year 2025 daily mean discharge, cfs. Daily mean, not continuous data or field measurements. | Pilot: official-base UI request verified |
| `noaa_hourly_verified_height` | The Battery verified hourly observed water levels; metres, MLLW, GMT, Sep 12–13 2025. One-hour observations, not predictions or six-minute data. | Added: offline checks pass; official-base UI request verified |
| `noaa_observed_high_low` | San Francisco observed high/low tide events; metres, MLLW, GMT, Sep 12–13 2025. Observed extrema, not predicted tides or a time series. | Added: offline checks pass; official-base UI request verified |
| `noaa_hourly_wind` | Key West hourly observed wind speed, direction and gust; metric, GMT, Sep 12–13 2025. Other weather requests alone do not qualify. | Added: offline checks pass; official-base UI request verified |
| `usgs_continuous_gage_height` | Gage height in feet at USGS-01104500, Sep 12–13 2025 station-local dates (EDT). Continuous series, not daily discharge or field measurements. | Added: offline checks pass; official-base UI request verified |
| `usgs_daily_mean_water_temperature` | Daily mean water temperature in °C from the non-discontinued multiparameter-sonde series at USGS-01646500, Sep 12–13 2025. A Mean-series request is required; maximum/minimum requests alone do not qualify. | Added: offline checks pass; official-base UI request verified |
| `usgs_earthquake_rectangle_catalog` | USGS CSV catalog, Sep 2025, magnitude ≥3, specified geographic rectangle, newest first. No extra depth/count/offset filters. | Added: offline checks pass; official-base UI request verified |
| `ndbc_standard_meteorology_archive` | Boston buoy 44013 full-year 2025 standard meteorology, uncompressed text. Not spectral, supplemental, current-year monthly or real-time data. | Added: offline checks pass; official-base UI request verified |
| `nasa_power_daily_solar_temperature` | NASA POWER daily T2M and all-sky shortwave irradiance for Sep 12–13 2025, metric, LST, JSON. Gridded estimates, not station measurements. | Added: offline checks pass; official-base UI request verified |
| `open_meteo_era5_hourly_reanalysis` | ERA5-only hourly temperature and precipitation for Sep 12–13 2025, GMT, °C and mm, CSV. Reanalysis, not direct observations; no extra variables. | Added: offline checks pass; official-base UI request verified |
| `epa_daily_ozone_archive` | EPA nationwide 2025 daily ozone (44201) pre-generated zipped CSV archive. Not hourly/8-hour samples, annual summaries or AQI. | Added: offline checks pass; official-base UI request verified |

## Outcome and evidence boundaries

The evaluated outcome is initiation of the correctly configured request shown in the task. Request interception is intentional: it does not establish that a final CSV, ZIP or other file was saved, extracted or delivered. These results do not include a full runner CLI evaluation, Stage 2 judge, paid-model trial or human timing study.

The interceptor credits the first qualifying request; it does not penalize unrelated requests made earlier. Variable sets within a single NASA/Open-Meteo request and the single USGS series ID are constrained, but cross-request exclusivity is not claimed.

The official-base continuous-gage run converted the visibly selected September 12–13 dates to `2025-09-12T04:00:00.000Z/2025-09-14T03:59:59.999Z`, matching the requested station-local EDT days. Browser time zone was not separately recorded: this proves the observed container workflow, not invariant conversion under every locale. The temperature-page recording shows the selected multiparameter-sonde series through 2026-09-23, while the depth-specific alternatives are explicitly discontinued and end in 2019; daily Mean selection produced the required series request.

For NASA POWER, leave custom site elevation unset. The [official Daily API documentation](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) describes its pressure-correction effect. A paired API check found that adding `site-elevation=0.000` preserved the requested T2M/solar values but also added a third `PSC` pressure series. It is deliberately not an accepted optional field for this two-variable task.

All 12 workflows have Codex-operated official-base-runtime UI request evidence at pinned ClawBench commit `9dd9d442c8ec720ba4d6d4c95f2bbc0ff2a2d0df` (the server matcher also matches the reviewed upstream `187cd25`). Final offline validation passes 808/808 checks across all 12: 12 schema, 49 must-accept URL, 697 must-reject URL and 50 supplied-data checks. Data identities/shapes are checked for nine tasks; NDBC, Open-Meteo and EPA responses are not covered by those data checks. Offline predicates, recorded browser URLs and real UI interception are separate evidence.

Each addition has a successful recorded `eval_matched` run. Earthquake was entered as magnitude `3.0`; the UI serialized `3`, while the matcher also accepts equivalent `3.0` and `3.00` and rejects missing/duplicate/wrong magnitudes. The USGS `limit` and `f` constraints remain as explained in the existing review-thread response: they prevent a truncated default page or a JSON request being credited as the requested complete CSV download.

Failure history is retained: Open-Meteo attempt 1 timed out; attempt 2 passed within its unchanged 10-minute limit. NASA attempts 1–2 timed out at 600 seconds. NASA attempt 3 was manually stopped after requests included unwanted `site-elevation=0.000`; it did not intercept and is not a pass. Attempt 4 passed with no custom elevation. NASA's configured limit is now 30 minutes for the multi-control viewer; the other 11 limits remain 10 minutes. These are watchdog limits, not measured human completion times.

Raw request/action/video artifacts are retained locally, not included in this task-only repository diff. Run results verify initiation only. Existing successful schemas for the two pilots, NOAA additions and USGS water additions did not change during later instruction-only format/exclusion clarifications; those older runs are not mislabelled as new runs of an identical full task-file hash. EPA's full file hash also differs, but its captured instruction, schema and limit match the final values. The final schemas and captured qualifying requests were rechecked. An independent Claude Opus 5.5 review of the earlier draft informed these corrections; final verification was by Codex.

Codex performed the implementation and validation for Ziao Yang using public sources only; no private user data was used. The 12 workflows support proposing a new category under the official rules, but category acceptance is pending. A concrete paper and individual authorship invitation are also pending; authorship is not guaranteed. NCEI was replaced by Open-Meteo because its UI exported the full station dataset instead of the required date-and-variable subset.

## Running

Use the ordinary single-task or suite runner against this directory, for example:

```bash
uv run clawbench-run test-cases/environmental-observation/usgs_earthquake_rectangle_catalog --human
```

This full-runner command is the reproduction path, not a claim that it was executed in this validation. Human completion in under one minute has not been measured. Full runner and Stage 2 judge behavior remain unverified; the supplied evidence is for the official base runtime's request interception only.
