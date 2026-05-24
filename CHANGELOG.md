
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.5.0] - 2026-05-24
### Added
- Added display of live token cost estimation during the run.

### Fixed
- Fixed the issue that Claude Code Chrome Extension harness cannot be build due to upstream changes and pinned to a fixed version.
- Fixed the issue that in TUI the color highlight is not moving properly with the selection arrow.

## [0.4.1] - 2026-05-23
### Fixed
- Fixed several mismatches in task definitions and the provided extra information.

## [0.4.0] - 2026-05-22
### Added
- Added scripts for rescoring and reproducing the benchmark results based on disclosed trajectories.

## [0.3.3] - 2026-05-19
### Changed
- More data are stored in the `run-meta.json` for better post-hoc analysis and reproducibility, including the hash of the configs, runtime info, and flags used.

### Fixed
- Fixed several compatibility issues on Windows platforms.

## [0.3.2] - 2026-05-15
### Added
- Added the logic to remove the `.log` files from the generated `data/` directory to remove noise.
- Added the handling to allow models with no visual capabilities to use the `claude-code-browser-extension` harness by skipping the screenshot steps.
- Added retry logic to the `claude-code-browser-extension` harness to handle temporary rate limits.

## [0.3.1] - 2026-05-13
### Fixed
- Removed v1-799 and v2-795 tasks since the current interception schemas have risk of leaking the agent's final action to the end server, which leads to unexpected disturbance of the end business.

## [0.3.0] - 2026-05-09
### Added
- Added support for the **pi** harness — [Pi coding agent](https://github.com/earendil-works/pi/tree/main/packages/coding-agent) + [`pi-browser-harness`](https://github.com/amankumarsingh77/pi-browser-harness)

## [0.2.2] - 2026-05-08
### Changed
- Migrated the PyPI package to `clawbench-eval` instead of `clawbenchmark`.

## [0.2.1] - 2026-05-08
### Fixed
- Included the `static/` directory in the package distribution, ensuring markdowns render properly on PyPI.

## [0.2.0] - 2026-05-08

### Added
- Added support for additional harnesses: `opencode`, `claude-code`,
  `claude-code-chrome-extension`, `codex`, `browser-use`, `claw-code`, and
  `hermes`, alongside the existing `openclaw` harness.
- Added the V2 suite under `test-cases/v2/`, with 130 new tasks.
- Added the V1-Lite suite under `test-cases/v1-lite/`, with 20 curated V1 tasks for faster testing.
- Added CI workflows for automated testings and release management.
- Published the package to PyPI as [`clawbenchmark`](https://pypi.org/project/clawbenchmark/).

### Changed
- Refactored the codebase into a package-oriented structure under
  `src/clawbench/` for better modularity and maintainability.
- Updated packaging so runtime harnesses, the Chrome extension, model templates,
  and V1/V2/V1-Lite task suites are bundled for installs without cloning the
  repository.
- Updated the FAQ and usage examples for the expanded harness and suite support.
- Switched to use `hatchling` as the build backend for better packaging and distribution management.

### Fixed
- Fixed packaging and building processes that previously generated malformed distributions.
