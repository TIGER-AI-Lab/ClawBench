# Research artifact retrieval

This proposed category contains 12 browser workflows in which the agent fetches one exact research artifact from public scholarly and ML infrastructure: a paper version, a supplement, a citation record, a model or dataset file, or a software build. Released V1/V2 and framework code are unchanged.

Researchers do this many times a week, and it is easy to get subtly wrong. Each site lists the target next to near-identical alternatives: other versions, revisions, platforms, formats or entries for the same work. The agent must pick the one the instruction describes.

| Workflow | Target | Near misses that do not qualify |
|---|---|---|
| `arxiv_tex_source_dated_version` | TeX source of the DPO paper version that was newest on 2024-01-01 (v2) | v1, v3, PDF, HTML |
| `arxiv_first_version_pdf` | PDF of v1 of "Attention Is All You Need" | the default latest version (v7) |
| `neurips_supplemental_material` | NeurIPS 2023 supplemental PDF of QLoRA | main paper PDF, BibTeX |
| `dblp_standard_bibtex_export` | dblp standard-format `.bib` of the NeurIPS 2023 Toolformer entry | CoRR preprint entry, condensed and crossref formats |
| `hf_model_file_parent_revision` | `tokenizer_config.json` of Qwen/Qwen3-1.7B at the parent of the commit "update tokenizer_config.json" | current file, the update commit itself |
| `hf_dataset_config_split_parquet` | openai/gsm8k `socratic` test-split Parquet file | `main` configuration, train split, converted Parquet branch |
| `hf_gguf_quantization_second_part` | second part of the Q4_K_M split in Qwen/Qwen2.5-7B-Instruct-GGUF | first part, Q5_K_M and other quantizations |
| `pypi_platform_wheel` | numpy 2.1.3 wheel for CPython 3.12 on glibc x86-64 Linux | musllinux, aarch64, macOS, Windows, other Python versions, sdist |
| `pytorch_cuda_wheel` | torch 2.2.1 wheel for CUDA 12.1, CPython 3.11, x86-64 Linux | CPU and other CUDA builds, other Python and torch versions |
| `github_release_linux_arm64_tarball` | pandoc 3.1.11 `linux-arm64` tarball | `.deb`, macOS and amd64 builds, other releases |
| `zenodo_versioned_software_archive` | scikit-learn 1.3.0 source archive on Zenodo | records of 1.3.1, 1.3.2 and other versions |
| `cran_archived_source_package` | ggplot2 3.4.2 source package from the CRAN archive | current release, binaries, other versions |

All targets are pinned to versions, revisions or records that already exist and are not expected to change. Instructions name the site and the artifact but not the final URL.

## Outcome

The evaluated outcome is initiation of the GET request that downloads the correct artifact. The interceptor blocks that request, so no file is saved. Each predicate is a URL regex with method `GET`. Where a site serves the same file under more than one equivalent URL, the predicate accepts each form:

- with or without `?download=true` on Hugging Face;
- full or abbreviated commit hashes (7 or more characters) for the Hugging Face revision task;
- `download.pytorch.org` or its `download-r2` mirror, with `+` written as `+` or `%2B`;
- the `cran` and `cloud` CRAN hosts;
- dblp's `.bib` link with or without `?param=1`, which return the same standard record.

The interceptor credits the first qualifying request. It does not penalize unrelated requests made earlier.

## Validation

- **Offline:** [`tests/test_research_artifacts_suite.py`](../../tests/test_research_artifacts_suite.py) checks the task shape, 25 must-accept URLs and 52 must-reject near-miss URLs, and rejects the right URL sent with the wrong method.
- **Live:** each of the 12 workflows was run in the official `clawbench-base` image, built from commit `c840962`, on 2026-11-14 in human mode. A scripted operator connected to the container's Chromium over CDP and completed the task through the site UI. Each task has two successful runs, the second on the final task files, and in each the runtime's own interceptor wrote `interception.json`. Four earlier attempts failed before reaching the target because the operator script used a stale selector: arXiv's new homepage search box twice, arXiv search ranking once, and the Hugging Face commit-page links once. No attempt reached the target request without the predicate firing. The captured URLs of the final runs and the task-file hashes are in [`tests/fixtures/research_artifacts_live_captures.json`](../../tests/fixtures/research_artifacts_live_captures.json), and the test suite checks that they still match.
- **Runtime deviation:** the container ran under rootless Podman with host networking, because the validation host has no TUN device for `slirp4netns`. The image and the runtime server were otherwise unmodified.

## Limits

- **Some predicates rely on fixed values:**
  - the PyPI wheel path contains its content hash;
  - the NeurIPS file name contains the proceedings hash;
  - the Zenodo task targets record `8098905`.

  If a site re-hosts the file, the predicate needs updating.
- **Bot checks:** dblp serves a JavaScript proof-of-work check that headless HTTP clients fail. The container's Chromium passed it.
- **Not yet run:** agent runs and Stage 2 judging. The live runs establish that each predicate fires on the real UI request; they are not agent results.

## Running

```bash
uv run clawbench-run test-cases/research-artifacts/pypi_platform_wheel --human
```
