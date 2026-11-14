"""Offline checks for the research-artifacts suite.

Each task's interceptor predicate must accept the requests a correct
completion issues and reject the near-miss requests listed below.
Matching follows the runtime server: ``re.search`` on the full request URL,
then an exact method check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parents[1] / "test-cases" / "research-artifacts"
CAPTURES = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "research_artifacts_live_captures.json"
)

HF = "https://huggingface.co"
QWEN3_PARENT = "d3e258980a49b060055ea9038dad99d75923f7c4"
QWEN3_UPDATE = "0ecc654158dd093daab47fd37c5f122925d93983"
NUMPY_PATH = (
    "https://files.pythonhosted.org/packages/9e/3e/"
    "3757f304c704f2f0294a6b8340fcf2be244038be07da4cccf390fa678a9f/"
)
NEURIPS_2023 = "https://proceedings.neurips.cc/paper_files/paper/2023/file/"
NEURIPS = NEURIPS_2023 + "1feb87871436031bdc0f2beaa62a049b"
DPO_SUPPLEMENT = (
    NEURIPS_2023 + "a85b405ed65c6477a4fe8302b5e06ce7-Supplemental-Conference.pdf"
)

CASES: dict[str, dict[str, list[str]]] = {
    "github_release_linux_arm64_tarball": {
        "accept": [
            "https://github.com/jgm/pandoc/releases/download/3.1.11/pandoc-3.1.11-linux-arm64.tar.gz",
        ],
        "reject": [
            "https://github.com/jgm/pandoc/releases/download/3.1.11/pandoc-3.1.11-1-arm64.deb",
            "https://github.com/jgm/pandoc/releases/download/3.1.11/pandoc-3.1.11-linux-amd64.tar.gz",
            "https://github.com/jgm/pandoc/releases/download/3.1.11/pandoc-3.1.11-arm64-macOS.zip",
            "https://github.com/jgm/pandoc/releases/download/3.1.12/pandoc-3.1.12-linux-arm64.tar.gz",
            "https://github.com/jgm/pandoc/archive/refs/tags/3.1.11.tar.gz",
        ],
    },
    "arxiv_tex_source_dated_version": {
        "accept": [
            "https://arxiv.org/src/2305.18290v2",
            "https://www.arxiv.org/src/2305.18290v2",
        ],
        "reject": [
            "https://arxiv.org/src/2305.18290",
            "https://arxiv.org/src/2305.18290v1",
            "https://arxiv.org/src/2305.18290v3",
            "https://arxiv.org/pdf/2305.18290v2",
            "https://arxiv.org/html/2305.18290v2",
        ],
    },
    "arxiv_first_version_pdf": {
        "accept": [
            "https://arxiv.org/pdf/1706.03762v1",
            "https://arxiv.org/pdf/1706.03762v1.pdf",
        ],
        "reject": [
            "https://arxiv.org/pdf/1706.03762",
            "https://arxiv.org/pdf/1706.03762v7",
            "https://arxiv.org/pdf/1706.03762v10",
            "https://arxiv.org/abs/1706.03762v1",
            "https://arxiv.org/src/1706.03762v1",
        ],
    },
    "hf_model_file_parent_revision": {
        "accept": [
            f"{HF}/Qwen/Qwen3-1.7B/resolve/{QWEN3_PARENT}/tokenizer_config.json?download=true",
            f"{HF}/Qwen/Qwen3-1.7B/resolve/{QWEN3_PARENT}/tokenizer_config.json",
            f"{HF}/Qwen/Qwen3-1.7B/resolve/{QWEN3_PARENT[:7]}/tokenizer_config.json",
        ],
        "reject": [
            f"{HF}/Qwen/Qwen3-1.7B/resolve/main/tokenizer_config.json?download=true",
            f"{HF}/Qwen/Qwen3-1.7B/resolve/{QWEN3_UPDATE}/tokenizer_config.json?download=true",
            f"{HF}/Qwen/Qwen3-1.7B/resolve/{QWEN3_PARENT[:6]}/tokenizer_config.json",
            f"{HF}/Qwen/Qwen3-1.7B/resolve/{QWEN3_PARENT[:7]}0/tokenizer_config.json",
            f"{HF}/Qwen/Qwen3-1.7B/resolve/{QWEN3_PARENT}/tokenizer.json?download=true",
            f"{HF}/Qwen/Qwen3-1.7B/raw/{QWEN3_PARENT}/tokenizer_config.json",
            f"{HF}/Qwen/Qwen3-4B/resolve/{QWEN3_PARENT}/tokenizer_config.json",
        ],
    },
    "hf_dataset_config_split_parquet": {
        "accept": [
            f"{HF}/datasets/openai/gsm8k/resolve/main/socratic/test-00000-of-00001.parquet?download=true",
            f"{HF}/datasets/openai/gsm8k/resolve/main/socratic/test-00000-of-00001.parquet",
            f"{HF}/datasets/openai/gsm8k/resolve/{'e' * 40}/socratic/test-00000-of-00001.parquet",
        ],
        "reject": [
            f"{HF}/datasets/openai/gsm8k/resolve/main/main/test-00000-of-00001.parquet?download=true",
            f"{HF}/datasets/openai/gsm8k/resolve/main/socratic/train-00000-of-00001.parquet?download=true",
            f"{HF}/datasets/openai/gsm8k/resolve/refs%2Fconvert%2Fparquet/socratic/test/0000.parquet",
            f"{HF}/datasets/openai/gsm8k/resolve/main/socratic/test-00000-of-00001.parquet?download=true&x=1",
        ],
    },
    "hf_gguf_quantization_second_part": {
        "accept": [
            f"{HF}/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf?download=true",
            f"{HF}/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf",
        ],
        "reject": [
            f"{HF}/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf?download=true",
            f"{HF}/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q5_k_m-00002-of-00002.gguf?download=true",
            f"{HF}/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf?download=true",
        ],
    },
    "pypi_platform_wheel": {
        "accept": [
            NUMPY_PATH
            + "numpy-2.1.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
        ],
        "reject": [
            NUMPY_PATH + "numpy-2.1.3-cp312-cp312-musllinux_1_1_x86_64.whl",
            NUMPY_PATH
            + "numpy-2.1.3-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
            NUMPY_PATH
            + "numpy-2.1.3-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
            NUMPY_PATH + "numpy-2.1.3.tar.gz",
            "https://files.pythonhosted.org/packages/00/00/"
            + "0" * 60
            + "/numpy-2.1.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
        ],
    },
    "pytorch_cuda_wheel": {
        "accept": [
            "https://download-r2.pytorch.org/whl/cu121/torch-2.2.1%2Bcu121-cp311-cp311-linux_x86_64.whl",
            "https://download.pytorch.org/whl/cu121/torch-2.2.1%2Bcu121-cp311-cp311-linux_x86_64.whl",
            "https://download.pytorch.org/whl/cu121/torch-2.2.1+cu121-cp311-cp311-linux_x86_64.whl",
        ],
        "reject": [
            "https://download.pytorch.org/whl/cpu/torch-2.2.1%2Bcpu-cp311-cp311-linux_x86_64.whl",
            "https://download.pytorch.org/whl/cu118/torch-2.2.1%2Bcu118-cp311-cp311-linux_x86_64.whl",
            "https://download.pytorch.org/whl/cu121/torch-2.2.1%2Bcu121-cp310-cp310-linux_x86_64.whl",
            "https://download.pytorch.org/whl/cu121/torch-2.2.2%2Bcu121-cp311-cp311-linux_x86_64.whl",
            "https://download.pytorch.org/whl/cu121/torch-2.2.1%2Bcu121-cp311-cp311-win_amd64.whl",
        ],
    },
    "zenodo_versioned_software_archive": {
        "accept": [
            "https://zenodo.org/records/8098905/files/scikit-learn/scikit-learn-1.3.0.zip?download=1",
            "https://zenodo.org/records/8098905/files/scikit-learn/scikit-learn-1.3.0.zip",
        ],
        "reject": [
            "https://zenodo.org/records/8363803/files/scikit-learn/scikit-learn-1.3.1.zip?download=1",
            "https://zenodo.org/records/10039710/files/scikit-learn/scikit-learn-1.3.2.zip?download=1",
            "https://zenodo.org/records/7711792/files/scikit-learn/scikit-learn-1.2.2.zip?download=1",
        ],
    },
    "neurips_supplemental_material": {
        "accept": [
            NEURIPS + "-Supplemental-Conference.pdf",
        ],
        "reject": [
            NEURIPS + "-Paper-Conference.pdf",
            DPO_SUPPLEMENT,
        ],
    },
    "cran_archived_source_package": {
        "accept": [
            "https://cran.r-project.org/src/contrib/Archive/ggplot2/ggplot2_3.4.2.tar.gz",
            "https://cloud.r-project.org/src/contrib/Archive/ggplot2/ggplot2_3.4.2.tar.gz",
        ],
        "reject": [
            "https://cran.r-project.org/src/contrib/Archive/ggplot2/ggplot2_3.4.1.tar.gz",
            "https://cran.r-project.org/src/contrib/Archive/ggplot2/ggplot2_3.4.20.tar.gz",
            "https://cran.r-project.org/src/contrib/ggplot2_4.0.1.tar.gz",
            "https://cran.r-project.org/bin/windows/contrib/4.3/ggplot2_3.4.2.zip",
        ],
    },
    "dblp_standard_bibtex_export": {
        "accept": [
            "https://dblp.org/rec/conf/nips/SchickDDRLHZCS23.bib?param=1",
            "https://dblp.org/rec/conf/nips/SchickDDRLHZCS23.bib",
            "https://dblp.uni-trier.de/rec/conf/nips/SchickDDRLHZCS23.bib?param=1",
        ],
        "reject": [
            "https://dblp.org/rec/conf/nips/SchickDDRLHZCS23.bib?param=0",
            "https://dblp.org/rec/conf/nips/SchickDDRLHZCS23.bib?param=2",
            "https://dblp.org/rec/conf/nips/SchickDDRLHZCS23.html?view=bibtex",
            "https://dblp.org/rec/journals/corr/abs-2302-04761.bib?param=1",
        ],
    },
}


def load(name: str) -> dict:
    return json.loads((SUITE / name / "task.json").read_text())


def matches(task: dict, url: str, method: str = "GET") -> bool:
    schema = task["eval_schema"]
    return bool(re.search(schema["url_pattern"], url)) and method == schema["method"]


def test_every_task_has_cases() -> None:
    assert sorted(p.name for p in SUITE.iterdir() if p.is_dir()) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_task_shape(name: str) -> None:
    task = load(name)
    assert set(task) == {"instruction", "eval_schema", "time_limit"}
    assert set(task["eval_schema"]) == {"url_pattern", "method"}
    assert task["eval_schema"]["method"] == "GET"
    assert 5 <= task["time_limit"] <= 30


@pytest.mark.parametrize("name", sorted(CASES))
def test_accepts_correct_requests(name: str) -> None:
    task = load(name)
    for url in CASES[name]["accept"]:
        assert matches(task, url), url


@pytest.mark.parametrize("name", sorted(CASES))
def test_rejects_near_misses(name: str) -> None:
    task = load(name)
    for url in CASES[name]["reject"]:
        assert not matches(task, url), url
    assert not matches(task, CASES[name]["accept"][0], method="POST")


def test_live_captures_still_match() -> None:
    captures = json.loads(CAPTURES.read_text())
    assert sorted(captures) == sorted(CASES)
    for name, cap in captures.items():
        assert matches(load(name), cap["url"], cap["method"]), name
