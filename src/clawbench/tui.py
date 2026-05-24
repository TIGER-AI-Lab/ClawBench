"""Interactive TUI for ClawBench — select mode, models, and cases with rich UI."""

import importlib
import inspect
import json
import multiprocessing
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import questionary
import yaml
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.text import Text

from clawbench.runner.run_support.harness_registry import HARNESS_REGISTRY
from clawbench.utils.paths import ASSET_ROOT, WORKSPACE_ROOT, ensure_workspace_templates

HARNESSES = HARNESS_REGISTRY.harnesses
DEFAULT_HARNESS = HARNESS_REGISTRY.default


def _patch_questionary_defaults() -> None:
    """Patch questionary's baked-in defaults.

    1. Remove the ``?`` qmark prefix from every prompt type.
    2. Replace the instruction hint with ``(↑↓)`` for select/checkbox only.
    """
    # Pass 1: strip qmark on all prompt functions
    for name in dir(questionary):
        fn = getattr(questionary, name, None)
        if not callable(fn) or not hasattr(fn, "__defaults__"):
            continue
        defaults = fn.__defaults__
        if not defaults:
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        params_with_defaults = [
            p
            for p in sig.parameters.values()
            if p.default is not inspect.Parameter.empty
        ]
        if len(params_with_defaults) != len(defaults):
            continue
        new = list(defaults)
        changed = False
        for i, p in enumerate(params_with_defaults):
            if p.name == "qmark":
                new[i] = ""
                changed = True
        if changed:
            fn.__defaults__ = tuple(new)

    # Pass 2: set instruction=(↑↓) on select and checkbox only
    for name in ("select", "checkbox"):
        fn = getattr(questionary, name, None)
        if fn is None or not hasattr(fn, "__defaults__"):
            continue
        defaults = fn.__defaults__
        if not defaults:
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        params_with_defaults = [
            p
            for p in sig.parameters.values()
            if p.default is not inspect.Parameter.empty
        ]
        if len(params_with_defaults) != len(defaults):
            continue
        new = list(defaults)
        changed = False
        for i, p in enumerate(params_with_defaults):
            if p.name == "instruction" and new[i] is None:
                new[i] = "(↑↓)"
                changed = True
        if changed:
            fn.__defaults__ = tuple(new)

    # In questionary 2.1.x, select(default=...) both places the cursor and
    # marks the default row as "selected". That makes the visual highlight
    # look stuck on the original row after the cursor moves. Keep default as
    # the initial cursor only; checkbox prompts still use the normal control.
    select_prompt = importlib.import_module("questionary.prompts.select")
    base_control = getattr(select_prompt, "InquirerControl")
    if getattr(base_control, "__name__", "") != "_SelectInquirerControl":

        class _SelectInquirerControl(base_control):
            def _is_selected(self, choice):
                return False

        setattr(select_prompt, "InquirerControl", _SelectInquirerControl)


_patch_questionary_defaults()

MODELS_YAML = WORKSPACE_ROOT / "models" / "models.yaml"
DEFAULT_DATASET = "v1"
DATASETS = {
    "v1": {
        "label": "V1 dataset  (test-cases/v1)",
        "summary": "V1 (test-cases/v1)",
        "cases_dir": "test-cases/v1",
    },
    "v2": {
        "label": "V2 dataset  (test-cases/v2)",
        "summary": "V2 (test-cases/v2)",
        "cases_dir": "test-cases/v2",
    },
    "v1-lite": {
        "label": "V1 Lite dataset  (test-cases/v1-lite)",
        "summary": "V1 Lite (test-cases/v1-lite)",
        "cases_dir": "test-cases/v1-lite",
    },
    "claw-eval": {
        "label": "Claw-Eval port  (test-cases/claw-eval)",
        "summary": "Claw-Eval port (test-cases/claw-eval)",
        "cases_dir": "test-cases/claw-eval",
    },
}

API_TYPES = [
    "openai-completions",
    "openai-responses",
    "anthropic-messages",
    "google-generative-ai",
]
THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "adaptive"]

# Provider presets for the "Add a new model" flow. Selecting a provider
# fills in base_url + api_type automatically and shows a handful of
# example model names so the user doesn't have to remember the exact
# string for each vendor.
PROVIDER_PRESETS: dict[str, dict] = {
    "anthropic": {
        "label": "Anthropic  (Claude)",
        "base_url": "https://api.anthropic.com",
        "api_type": "anthropic-messages",
        # Native Anthropic API uses hyphens ("claude-opus-4-6"), NOT
        # the dotted form ("claude-opus-4.6") that OpenRouter uses.
        "examples": [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ],
    },
    "openai": {
        "label": "OpenAI     (GPT / o-series)",
        "base_url": "https://api.openai.com/v1",
        "api_type": "openai-completions",
        "examples": [
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "o3-mini",
        ],
    },
    "google": {
        "label": "Google     (Gemini)",
        "base_url": "https://generativelanguage.googleapis.com",
        "api_type": "google-generative-ai",
        # 3.x is still in -preview as of April 2026; 2.5 is the
        # current stable tier. We show both so users can pick.
        "examples": [
            "gemini-3.1-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ],
    },
    "openrouter": {
        "label": "OpenRouter (multi-provider gateway)",
        "base_url": "https://openrouter.ai/api/v1",
        "api_type": "openai-completions",
        # OpenRouter normalizes some vendor ids — Claude uses DOTS
        # here ("claude-sonnet-4.6"), not the hyphens of the native
        # Anthropic API. When in doubt, paste the id exactly as
        # listed on https://openrouter.ai/models.
        "examples": [
            "anthropic/claude-sonnet-4.6",
            "openai/gpt-5.4",
            "google/gemini-3-flash-preview",
            "qwen/qwen3.5-plus-02-15",
        ],
    },
}

console = Console()

# ---------------------------------------------------------------------------
# Theme — picked at startup, persisted per user, applied to all questionary
# prompts. Dark and light variants use explicit hex colors rather than ANSI
# names so the contrast is correct regardless of what ANSI palette the
# user's terminal happens to have.
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".config" / "clawbench"
CONFIG_FILE = CONFIG_DIR / "tui.json"


def _make_style(theme: str) -> Style:
    """Build a questionary Style from Apple HIG system colors.

    Light appearance uses deeper tones for legibility on white;
    dark appearance uses brighter tones for dark backgrounds.

    Reference — Apple Human Interface Guidelines system colors:
        Light                       Dark
        Blue    #007AFF             Blue    #0A84FF
        Indigo  #5856D6             Indigo  #5E5CE6
        Green   #34C759             Green   #30D158
        Gray    #8E8E93             Gray    #8E8E93
    """
    if theme == "light":
        return Style(
            [
                ("qmark", "fg:#5856D6 bold"),  # Apple Indigo (light)
                ("question", "fg:#000000 bold"),
                ("answer", "fg:#34C759 bold"),  # Apple Green (light)
                ("pointer", "fg:#5856D6 bold"),
                ("highlighted", "fg:#5856D6 bold"),
                ("selected", "fg:#34C759"),
                ("separator", "fg:#8E8E93"),  # Apple Gray
                ("instruction", "fg:#8E8E93"),
                ("text", "fg:#000000"),
            ]
        )
    # dark (default)
    return Style(
        [
            ("qmark", "fg:#5E5CE6 bold"),  # Apple Indigo (dark)
            ("question", "fg:#ffffff bold"),
            ("answer", "fg:#30D158 bold"),  # Apple Green (dark)
            ("pointer", "fg:#5E5CE6 bold"),
            ("highlighted", "fg:#5E5CE6 bold"),
            ("selected", "fg:#30D158"),
            ("separator", "fg:#8E8E93"),  # Apple Gray
            ("instruction", "fg:#8E8E93"),
            ("text", "fg:#ffffff"),
        ]
    )


# Neutral style for the very first prompt (theme picker itself).
#
# This runs BEFORE we know whether the user's terminal is dark or light,
# so we can't commit to any color choice — a bright cyan that looks fine
# on a black background is painfully neon on a white one, and vice versa.
# The trick: use ``reverse`` (swaps foreground and background) for the
# highlighted row, which gives strong contrast on any terminal without
# picking a single RGB value. Everything else is plain ``bold`` or the
# terminal's own default foreground.
_NEUTRAL_STYLE = Style(
    [
        ("qmark", ""),
        ("question", "bold"),
        ("answer", "bold"),
        ("pointer", "bold"),
        ("highlighted", "reverse bold"),
        ("selected", "bold"),
        ("separator", "fg:ansibrightblack"),
        ("instruction", "fg:ansibrightblack"),
        ("text", ""),
    ]
)


def _load_saved_theme() -> str | None:
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    theme = data.get("theme")
    return theme if theme in ("dark", "light") else None


def _save_theme(theme: str) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps({"theme": theme}, indent=2))
    except OSError:
        pass  # best-effort persistence; not worth crashing the TUI


def _pick_theme() -> str:
    """Prompt for dark/light terminal. Returns the chosen theme string."""
    console.print()
    console.print(
        "  [dim]Pick the color theme that matches your terminal background.[/]"
    )
    theme = questionary.select(
        "Terminal theme:",
        choices=[
            questionary.Choice("Dark   (dark background, light text)", value="dark"),
            questionary.Choice("Light  (light background, dark text)", value="light"),
        ],
        style=_NEUTRAL_STYLE,
    ).ask()
    if theme is None:
        sys.exit(0)
    _save_theme(theme)
    console.print(
        f"  [dim]Saved theme={theme} to {CONFIG_FILE} — use "
        f"'Change theme' in the menu to switch later.[/]"
    )
    console.print()
    return theme


# Module-level STYLE: starts as the neutral fallback, gets replaced in main()
# once we know the user's theme preference. All prompt call sites read
# ``STYLE`` at call time, so rebinding it via ``global`` inside main() works.
STYLE: Style = _NEUTRAL_STYLE

# Rich markup accent colors, updated alongside STYLE in main().
# ACCENT  — section headers ("--- Select Model ---"), panel borders.
# ACCENT2 — inline values, secondary highlights.
#
# Apple HIG system colors (light / dark):
#   Indigo  #5856D6 / #5E5CE6
#   Blue    #007AFF / #0A84FF
#   Green   #34C759 / #30D158
ACCENT = "#5E5CE6"  # Apple Indigo dark; replaced in main()
ACCENT2 = "#0A84FF"  # Apple Blue dark;   replaced in main()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_models_data() -> dict:
    if not MODELS_YAML.exists():
        return {}
    return yaml.safe_load(MODELS_YAML.read_text()) or {}


def save_models(data: dict) -> None:
    MODELS_YAML.parent.mkdir(parents=True, exist_ok=True)
    MODELS_YAML.write_text(yaml.safe_dump(data, sort_keys=False))


def load_models() -> list[str]:
    return sorted(load_models_data().keys())


def _dataset_cases_dir_name(dataset: str) -> str:
    return DATASETS[dataset]["cases_dir"]


def _dataset_summary(dataset: str) -> str:
    return DATASETS[dataset]["summary"]


def _case_name_match(case: str) -> re.Match[str] | None:
    return re.match(r"^(?:v\d+-)?(\d+)([a-z]?)(?=-|$)", case, re.IGNORECASE)


def _case_numeric_id(case: str) -> int | None:
    match = _case_name_match(case)
    if not match:
        return None
    return int(match.group(1))


def _case_sort_key(case: str) -> tuple[int, int, str]:
    cid = _case_numeric_id(case)
    return (0, cid, case) if cid is not None else (1, sys.maxsize, case)


def load_cases(cases_dir_name: str = "test-cases") -> list[str]:
    cases_dir = ASSET_ROOT / cases_dir_name
    flat_cases = [
        p.stem
        for p in cases_dir.glob("*.json")
        if p.name not in {"eligibility-report.json"}
    ]
    cases = sorted(
        [*(p.parent.name for p in cases_dir.glob("*/task.json")), *flat_cases],
        key=_case_sort_key,
    )
    if not cases:
        console.print(f"[red bold]ERROR:[/] No test cases found in {cases_dir_name}/")
        sys.exit(1)
    return cases


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _windows_physical_memory_gb() -> float | None:
    try:
        import ctypes
    except ImportError:
        return None

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(status)
    try:
        ok = windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    except (AttributeError, OSError):
        return None
    if not ok:
        return None
    return status.ullTotalPhys / (1024**3)


def _physical_memory_gb() -> float:
    if platform.system() == "Windows":
        mem_gb = _windows_physical_memory_gb()
        if mem_gb is not None:
            return mem_gb
    try:
        mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        return mem_bytes / (1024**3)
    except (AttributeError, ValueError, OSError):
        return 8


def _recommend_concurrent() -> int:
    cpus = multiprocessing.cpu_count()
    mem_gb = _physical_memory_gb()
    by_cpu = cpus // 2
    by_ram = int(mem_gb // 2)
    recommended = max(1, min(by_cpu, by_ram))
    console.print(
        f"  System: [{ACCENT2}]{cpus}[/] CPUs, [{ACCENT2}]{mem_gb:.0f}[/] GB RAM "
        f"— recommended max: [green bold]{recommended}[/]"
    )
    return recommended


def _case_display(case: str) -> str:
    """Format a case name for display: '886  886-entertainment-hobbies-...'"""
    match = _case_name_match(case)
    prefix = f"{match.group(1)}{match.group(2)}" if match else case.split("-", 1)[0]
    return f"{prefix:>5}  {case}"


def _parse_range_input(raw: str, cases: list[str]) -> list[str]:
    """Parse comma-separated IDs, ranges (e.g. 1-50), or * into case names."""
    if raw.strip() == "*":
        return list(cases)

    # Build token map: V1 accepts '001' and '1'; V2 accepts 'v2-1065b',
    # '1065b', and numeric '1065' for range-like selection.
    id_map: dict[str, list[str]] = {}
    for c in cases:
        tokens = {c.lower()}
        match = _case_name_match(c)
        if match:
            num, suffix = match.group(1), match.group(2)
            label = f"{num}{suffix}".lower()
            tokens.update({num, num.lstrip("0") or "0", label})
            if c.lower().startswith("v"):
                tokens.add(f"v2-{label}")
        for token in tokens:
            id_map.setdefault(token, []).append(c)

    selected: list[str] = []

    def add_case(case: str) -> None:
        if case not in selected:
            selected.append(case)

    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if re.fullmatch(r"\d+\s*-\s*\d+", part):
            lo_s, hi_s = re.split(r"\s*-\s*", part, maxsplit=1)
            lo, hi = int(lo_s), int(hi_s)
            if lo > hi:
                continue
            for c in cases:
                cid = _case_numeric_id(c)
                if cid is not None and lo <= cid <= hi:
                    add_case(c)
        else:
            for c in id_map.get(part.lower(), []):
                add_case(c)
    return selected


def run_cmd(cmd: list[str], *, hint: str | None = None) -> None:
    console.print()
    console.print(Panel(" ".join(cmd), title="[bold]Command[/]", border_style="green"))
    if hint:
        console.print()
        console.print(hint)
    console.print()
    os.execvp(cmd[0], cmd)


def _confirm_launch(summary: dict) -> bool:
    """Show a summary panel and ask for confirmation."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style=f"bold {ACCENT}")
    table.add_column()
    for key, val in summary.items():
        table.add_row(key, str(val))
    console.print()
    console.print(Panel(table, title="[bold]Launch Summary[/]", border_style=ACCENT))
    console.print()
    return questionary.confirm("Launch?", default=True, style=STYLE).ask()


def _show_models_table(data: dict) -> None:
    """Print a rich table of configured models."""
    if not data:
        console.print("  [dim]No models configured yet.[/]\n")
        return
    table = Table(title="Configured Models", border_style="dim")
    table.add_column("Name", style="bold green")
    table.add_column("API Type", style=ACCENT2)
    table.add_column("Base URL")
    table.add_column("Thinking", style="yellow")
    for name, cfg in sorted(data.items()):
        table.add_row(
            name,
            cfg.get("api_type", "—"),
            cfg.get("base_url", "—"),
            cfg.get("thinking_level", "—"),
        )
    console.print(table)
    console.print()


def _pick_dataset(default: str = DEFAULT_DATASET) -> str | None:
    console.print(f"\n[bold {ACCENT}]--- Select Dataset ---[/]\n")
    return questionary.select(
        "Dataset:",
        choices=[
            questionary.Choice(cfg["label"], value=key) for key, cfg in DATASETS.items()
        ],
        default=default,
        style=STYLE,
    ).ask()


def _show_header(models: list[str], cases: list[str], dataset: str) -> None:
    title = Text("ClawBench", style="bold")
    subtitle = Text(
        f"{len(models)} models configured  |  "
        f"{_dataset_summary(dataset)}  |  "
        f"{len(cases)} test cases available",
        style="dim",
    )
    console.print()
    console.print(Panel(Text.assemble(title, "\n", subtitle)))
    console.print()


# ---------------------------------------------------------------------------
# Mode: Single run
# ---------------------------------------------------------------------------


def mode_single(
    models: list[str],
    cases: list[str],
    cases_dir_name: str,
    dataset_summary: str,
) -> None:
    _ADD_NEW = "+ Add new model"
    while True:
        console.print(f"\n[bold {ACCENT}]--- Select Model ---[/]\n")
        model = questionary.select(
            "Model:",
            choices=models + [questionary.Choice(_ADD_NEW, value=_ADD_NEW)],
            style=STYLE,
        ).ask()
        if model is None:
            return
        if model != _ADD_NEW:
            break
        _add_model(load_models_data())
        models = load_models()
        if not models:
            return

    console.print(f"\n[bold {ACCENT}]--- Select Harness ---[/]\n")
    harness = questionary.select(
        "Harness:",
        choices=list(HARNESSES),
        default=DEFAULT_HARNESS,
        style=STYLE,
    ).ask()
    if harness is None:
        return

    console.print(f"\n[bold {ACCENT}]--- Select Test Case ---[/]\n")
    case = questionary.select(
        "Case (arrow keys, or type to filter):",
        choices=cases,
        style=STYLE,
        use_search_filter=True,
        use_jk_keys=False,
    ).ask()
    if case is None:
        return

    ok = _confirm_launch(
        {
            "Mode": "Single run",
            "Dataset": dataset_summary,
            "Model": model,
            "Harness": harness,
            "Case": case,
        }
    )
    if not ok:
        return

    run_cmd(
        [
            sys.executable,
            "-m",
            "clawbench.runner.run",
            f"{cases_dir_name}/{case}",
            model,
            "--harness",
            harness,
        ],
        hint=(
            "  [dim]Tip: once the container starts, open the noVNC URL\n"
            "  printed below to watch the agent operate the browser\n"
            "  in real-time.[/]"
        ),
    )


# ---------------------------------------------------------------------------
# Mode: Batch run
# ---------------------------------------------------------------------------


def mode_batch(
    models: list[str],
    cases: list[str],
    cases_dir_name: str,
    dataset_summary: str,
    cases_suite: str,
) -> None:
    _ADD_NEW = "+ Add new model"
    while True:
        console.print(f"\n[bold {ACCENT}]--- Select Models ---[/]\n")
        selected_models = questionary.checkbox(
            "Models (space to select, enter to confirm):",
            choices=models + [questionary.Choice(_ADD_NEW, value=_ADD_NEW)],
            style=STYLE,
            validate=lambda x: len(x) > 0 or "Select at least one model",
        ).ask()
        if not selected_models:
            return
        if _ADD_NEW in selected_models:
            _add_model(load_models_data())
            models = load_models()
            continue  # re-show checkbox with updated list
        break

    console.print(f"\n[bold {ACCENT}]--- Select Harness ---[/]\n")
    harness = questionary.select(
        "Harness:",
        choices=list(HARNESSES),
        default=DEFAULT_HARNESS,
        style=STYLE,
    ).ask()
    if harness is None:
        return

    console.print(f"\n[bold {ACCENT}]--- Case Selection ---[/]\n")
    case_mode = questionary.select(
        "How to select cases?",
        choices=[
            questionary.Choice("All cases", value="all"),
            questionary.Choice("Case range (e.g. 1-50)", value="range"),
            questionary.Choice("Pick specific cases", value="pick"),
        ],
        style=STYLE,
    ).ask()
    if case_mode is None:
        return

    case_args: list[str] = []

    if case_mode == "all":
        case_args = ["--cases-suite", cases_suite, "--all-cases"]
        case_summary = f"All ({len(cases)})"
    elif case_mode == "range":
        raw = questionary.text(
            "Range (e.g. 1-50, 100-200):",
            style=STYLE,
            validate=lambda x: bool(x.strip()) or "Enter a range",
        ).ask()
        if raw is None:
            return
        # Validate and show what matched
        matched = _parse_range_input(raw, cases)
        if not matched:
            console.print("[red]No cases matched that range.[/]")
            return
        console.print(f"  Matched [green]{len(matched)}[/] cases")
        case_args = ["--cases-suite", cases_suite, "--case-range", raw.strip()]
        case_summary = f"Range {raw.strip()} ({len(matched)} cases)"
    else:
        # Interactive checkbox with all cases
        selected_cases = questionary.checkbox(
            "Cases (space to select):",
            choices=[questionary.Choice(_case_display(c), value=c) for c in cases],
            style=STYLE,
            validate=lambda x: len(x) > 0 or "Select at least one case",
        ).ask()
        if not selected_cases:
            return
        case_args = ["--cases"] + [f"{cases_dir_name}/{c}" for c in selected_cases]
        case_summary = f"{len(selected_cases)} selected"

    recommended = _recommend_concurrent()
    concurrent = questionary.text(
        "Max concurrent jobs:",
        default=str(recommended),
        style=STYLE,
        validate=lambda x: x.isdigit() and int(x) > 0 or "Enter a positive number",
    ).ask()
    if concurrent is None:
        return

    dry = questionary.confirm("Dry run first?", default=False, style=STYLE).ask()
    if dry is None:
        return

    ok = _confirm_launch(
        {
            "Mode": "Batch run",
            "Dataset": dataset_summary,
            "Models": ", ".join(selected_models),
            "Harness": harness,
            "Cases": case_summary,
            "Concurrent": concurrent,
            "Dry run": "Yes" if dry else "No",
        }
    )
    if not ok:
        return

    cmd = [
        sys.executable,
        "-m",
        "clawbench.runner.batch",
        "--models",
        *selected_models,
        *case_args,
        "--max-concurrent",
        concurrent,
        "--harness",
        harness,
    ]
    if dry:
        cmd.append("--dry-run")

    run_cmd(cmd)


# ---------------------------------------------------------------------------
# Mode: Human
# ---------------------------------------------------------------------------


def mode_human(cases: list[str], cases_dir_name: str, dataset_summary: str) -> None:
    console.print(f"\n[bold {ACCENT}]--- Select Test Case ---[/]\n")
    case = questionary.select(
        "Case (arrow keys, or type to filter):",
        choices=cases,
        style=STYLE,
        use_search_filter=True,
        use_jk_keys=False,
    ).ask()
    if case is None:
        return

    ok = _confirm_launch(
        {"Mode": "Human mode", "Dataset": dataset_summary, "Case": case}
    )
    if not ok:
        return

    run_cmd(
        [
            sys.executable,
            "-m",
            "clawbench.runner.run",
            f"{cases_dir_name}/{case}",
            "--human",
        ],
        hint=(
            "  [dim]Tip: open the noVNC URL printed below to\n"
            "  control the browser directly.[/]"
        ),
    )


# ---------------------------------------------------------------------------
# Mode: Configure models
# ---------------------------------------------------------------------------


def mode_configure() -> None:
    while True:
        data = load_models_data()
        _show_models_table(data)

        actions = ["Add a new model"]
        if data:
            actions.extend(["Edit a model", "Delete a model", "Back to main menu"])
        else:
            actions.append("Back to main menu")

        action = questionary.select(
            "What would you like to do?",
            choices=actions,
            style=STYLE,
        ).ask()
        if action is None or action == "Back to main menu":
            return

        if action == "Add a new model":
            _add_model(data)
        elif action == "Edit a model":
            _edit_model(data)
        elif action == "Delete a model":
            _delete_model(data)


def _add_model(data: dict) -> None:
    # -- Step 1: Pick provider ----------------------------------------------
    # Selecting one of the presets auto-fills base_url + api_type and shows
    # a handful of example model names. "Custom" falls back to the old
    # flow where the user types everything by hand.
    provider_choices = [
        questionary.Choice(preset["label"], value=key)
        for key, preset in PROVIDER_PRESETS.items()
    ]
    provider_choices.append(
        questionary.Choice(
            "Custom     (enter base URL + API type by hand)", value="custom"
        )
    )

    console.print(f"\n[bold {ACCENT}]--- Step 1: Provider ---[/]\n")
    provider = questionary.select(
        "Which provider?",
        choices=provider_choices,
        style=STYLE,
    ).ask()
    if provider is None:
        return

    preset = PROVIDER_PRESETS.get(provider)

    # -- Step 2: Model name (with per-provider examples) --------------------
    console.print(f"\n[bold {ACCENT}]--- Step 2: Model name ---[/]\n")
    if preset:
        console.print(f"  [dim]Examples for {preset['label'].strip()}:[/]")
        for ex in preset["examples"]:
            console.print(f"    [{ACCENT2}]{ex}[/]")
        console.print(
            "  [dim](This string is passed verbatim to the provider as "
            "the model id, and used as the key in models.yaml.)[/]\n"
        )
    else:
        console.print("  [dim]Enter the exact model id your custom API expects.[/]\n")

    name = questionary.text(
        "Model name:",
        style=STYLE,
        validate=lambda x: (
            "Name cannot be empty"
            if not x.strip()
            else f"'{x.strip()}' already exists"
            if x.strip() in data
            else True
        ),
    ).ask()
    if name is None:
        return
    name = name.strip()

    # -- Step 3: base_url + api_type (preset or manual) ---------------------
    if preset:
        base_url = preset["base_url"]
        api_type = preset["api_type"]
        console.print(
            f"  [dim]Using preset: base_url={base_url}  api_type={api_type}[/]"
        )
    else:
        console.print(f"\n[bold {ACCENT}]--- Step 3: Endpoint ---[/]\n")
        base_url = questionary.text(
            "Base URL:",
            style=STYLE,
            validate=lambda x: bool(x.strip()) or "URL cannot be empty",
        ).ask()
        if base_url is None:
            return
        api_type = questionary.select(
            "API type:",
            choices=API_TYPES,
            default="openai-completions",
            style=STYLE,
        ).ask()
        if api_type is None:
            return
        base_url = base_url.strip()

    # -- Step 4: API key ----------------------------------------------------
    console.print(f"\n[bold {ACCENT}]--- Step 4: API key ---[/]\n")
    api_key = questionary.text(
        "API key:",
        style=STYLE,
        validate=lambda x: bool(x.strip()) or "API key cannot be empty",
    ).ask()
    if api_key is None:
        return

    # -- Step 5: Thinking level --------------------------------------------
    console.print(f"\n[bold {ACCENT}]--- Step 5: Thinking level ---[/]\n")
    thinking_level = questionary.select(
        "Thinking level:",
        choices=THINKING_LEVELS,
        default="medium",
        style=STYLE,
    ).ask()
    if thinking_level is None:
        return

    data[name] = {
        "api_key": api_key.strip(),
        "base_url": base_url,
        "api_type": api_type,
        "thinking_level": thinking_level,
    }
    save_models(data)
    console.print(f"\n  [green bold]Saved[/] {name} to {MODELS_YAML}\n")


def _edit_model(data: dict) -> None:
    name = questionary.select(
        "Which model to edit?",
        choices=sorted(data.keys()),
        style=STYLE,
    ).ask()
    if name is None:
        return

    cfg = data[name]
    console.print(f"\n  Editing [bold]{name}[/] — press Enter to keep current value.\n")

    base_url = questionary.text(
        "Base URL:",
        default=cfg.get("base_url", ""),
        style=STYLE,
    ).ask()
    if base_url is None:
        return

    api_type = questionary.select(
        "API type:",
        choices=API_TYPES,
        default=cfg.get("api_type", "openai-completions"),
        style=STYLE,
    ).ask()
    if api_type is None:
        return

    api_key = questionary.text(
        "API key:",
        default=cfg.get("api_key", ""),
        style=STYLE,
    ).ask()
    if api_key is None:
        return

    thinking_level = questionary.select(
        "Thinking level:",
        choices=THINKING_LEVELS,
        default=cfg.get("thinking_level", "medium"),
        style=STYLE,
    ).ask()
    if thinking_level is None:
        return

    data[name] = {
        "api_key": api_key.strip(),
        "base_url": base_url.strip(),
        "api_type": api_type,
        "thinking_level": thinking_level,
    }
    save_models(data)
    console.print(f"\n  [green bold]Updated[/] {name}\n")


def _delete_model(data: dict) -> None:
    name = questionary.select(
        "Which model to delete?",
        choices=sorted(data.keys()),
        style=STYLE,
    ).ask()
    if name is None:
        return

    confirm = questionary.confirm(f"Delete '{name}'?", default=False, style=STYLE).ask()
    if not confirm:
        return

    del data[name]
    save_models(data)
    console.print(f"\n  [red bold]Deleted[/] {name}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _require_tty() -> None:
    """Bail out with a friendly message when stdin/stdout is not a real TTY.

    questionary/prompt_toolkit crash with a cryptic ``OSError: [Errno 22]
    Invalid argument`` when stdin is not a terminal (piped input, non-tty
    IDE terminals, CI, or calls from tools that don't allocate a pty).
    Detect this up-front and point the user at the non-interactive
    entrypoints instead.
    """
    if sys.stdin.isatty() and sys.stdout.isatty():
        return

    console.print()
    console.print("[yellow bold]![/] This TUI needs an interactive terminal.")
    console.print()
    console.print("  stdin/stdout is not a TTY (piped input, CI, some IDE terminals,")
    console.print(
        f"  or tool-based invocations). The underlying [{ACCENT2}]questionary[/]"
    )
    console.print("  library requires a real terminal to render prompts.")
    console.print()
    console.print("  For non-interactive use, call the Python entrypoints directly:")
    console.print()
    console.print(f"    [{ACCENT2}]clawbench-run[/] \\")
    console.print(
        f"        [{ACCENT2}]test-cases/v1/001-daily-life-food-uber-eats claude-sonnet-4-6[/]"
    )
    console.print()
    console.print(f"    [{ACCENT2}]clawbench-batch[/] \\")
    console.print(
        f"        [{ACCENT2}]--all-models --cases-suite v1 --case-range 1-50 --max-concurrent 3[/]"
    )
    console.print()
    console.print(f"  See [{ACCENT2}]src/README.md[/] for full CLI usage.")
    console.print()
    sys.exit(1)


# ---------------------------------------------------------------------------
# Container engine health check
# ---------------------------------------------------------------------------
#
# Every ClawBench run (including Human mode) launches a container via
# docker or podman. If the CLI binary is installed but the daemon /
# Linux VM isn't running, the user would otherwise only find out after
# picking a model, picking a case, confirming Launch, and waiting for a
# cryptic "unable to connect to Podman socket" error deep inside the
# build step.
#
# We short-circuit that by probing the engine at TUI startup and
# offering a one-click fix for the common cases:
#
#   * podman with no machine initialized  -> `podman machine init`
#                                            + `podman machine start`
#   * podman machine exists but stopped    -> `podman machine start`
#   * docker daemon not running on macOS   -> `open -a Docker`
#
# If the fix succeeds, we continue; if the user declines or it fails,
# we let them into the TUI anyway (they may want to Configure models or
# Change theme before fixing the engine), but flag that run modes will
# fail until the engine is up.


def _engine_from_env_or_path() -> str | None:
    """Same detection logic as run.py / batch.py: env var wins, else
    prefer docker then podman on PATH."""
    env = os.environ.get("CONTAINER_ENGINE", "").strip().lower()
    if env in ("docker", "podman") and shutil.which(env):
        return env
    for cmd in ("docker", "podman"):
        if shutil.which(cmd):
            return cmd
    return None


def _check_engine() -> tuple[str | None, str, str]:
    """Probe the container engine and classify the result.

    Returns ``(engine, status, detail)`` where ``status`` is one of:

    * ``ready``                — engine installed and daemon responsive.
    * ``not_installed``        — neither docker nor podman on PATH.
    * ``podman_no_machine``    — podman installed, no VM initialized (mac/win).
    * ``podman_machine_stopped`` — VM exists but is not currently running.
    * ``docker_not_running``   — docker CLI works but daemon unreachable.
    * ``podman_low_memory``    — VM has < 4 GB RAM; agent will OOM.
    * ``unknown_error``        — something else; ``detail`` has stderr.
    """
    engine = _engine_from_env_or_path()
    if engine is None:
        return None, "not_installed", ""

    if engine == "podman":
        # On macOS/Windows, podman needs a helper VM. Inspect it directly.
        if platform.system() in ("Darwin", "Windows"):
            try:
                r = subprocess.run(
                    ["podman", "machine", "list", "--format", "json"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                return engine, "unknown_error", str(e)
            if r.returncode != 0:
                return engine, "unknown_error", r.stderr.strip()
            try:
                machines = json.loads(r.stdout or "[]")
            except json.JSONDecodeError:
                machines = []
            if not machines:
                return engine, "podman_no_machine", ""
            if not any(m.get("Running") for m in machines):
                return engine, "podman_machine_stopped", ""
            # Machine is supposed to be running — verify the socket works.

        try:
            r = subprocess.run(
                ["podman", "ps"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return engine, "unknown_error", str(e)
        if r.returncode != 0:
            err = r.stderr.strip()
            # Linux rootless: same socket error pattern, different cause.
            if "unable to connect to Podman socket" in err:
                return engine, "podman_machine_stopped", err
            return engine, "unknown_error", err

        # Check VM memory — ClawBench needs ≥ 4 GB (Chrome + gateway + agent).
        if platform.system() in ("Darwin", "Windows"):
            try:
                mi = subprocess.run(
                    [
                        "podman",
                        "machine",
                        "inspect",
                        "--format",
                        "{{.Resources.Memory}}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                mem_mb = int(mi.stdout.strip())
                if mem_mb < 4096:
                    return engine, "podman_low_memory", str(mem_mb)
            except (ValueError, subprocess.TimeoutExpired):
                pass  # non-critical — skip if we can't read it

        return engine, "ready", ""

    # engine == "docker"
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return engine, "unknown_error", str(e)
    if r.returncode != 0:
        return engine, "docker_not_running", r.stderr.strip()
    return engine, "ready", ""


def _diagnose_fix_failure(buf: list[str]) -> str | None:
    """Scan captured command output for known failure patterns and
    return a friendly hint, or None if we don't recognize the error.

    These run AFTER a fix command (``podman machine init`` etc.) has
    failed, so we have the full output buffer to pattern-match.
    """
    blob = "\n".join(buf).lower()

    # Proxy misconfiguration: users in regions that need an HTTP proxy
    # to reach quay.io often have a stale HTTPS_PROXY pointing at a
    # port that isn't currently listening. The error looks like:
    #   proxyconnect tcp: dial tcp 127.0.0.1:7891: connect: connection refused
    if "proxyconnect" in blob and "connection refused" in blob:
        # Pull out the port we couldn't reach, if visible.
        import re as _re

        m = _re.search(r"dial tcp \S+?:(\d+)", blob)
        port = m.group(1) if m else "?"
        return (
            "Your HTTP(S)_PROXY env var points at a proxy on "
            f"port {port}, but nothing is listening there right now.\n\n"
            "Either start the proxy tool on that port, or update your "
            "shell profile (.zshrc/.bashrc) to point at the proxy port "
            "that is actually running, then open a fresh terminal and "
            "re-run ./run.sh.\n\n"
            "If you are behind the Great Firewall, you need a working "
            "proxy to reach quay.io — you can't just unset HTTPS_PROXY."
        )

    # DNS / generic connectivity failure (no proxy involved)
    if "no such host" in blob or "could not resolve" in blob:
        return (
            "Network lookup failed while reaching a container registry. "
            "Check your DNS / VPN / proxy settings and try again."
        )

    # Registry unreachable but no proxy error — probably GFW without a
    # proxy configured at all.
    if "quay.io" in blob and ("timeout" in blob or "i/o timeout" in blob):
        return (
            "Couldn't reach quay.io (the podman machine image registry). "
            "If you are behind a restrictive network, set HTTPS_PROXY "
            "to a working proxy and re-run."
        )

    return None


def _run_streamed(cmd: list[str], *, status_msg: str) -> int:
    """Run a long-running command under a Rich Status spinner.

    We stream stderr/stdout to a buffer so the spinner stays clean, then
    dump the last ~20 lines on failure — plus a diagnostic hint if we
    recognize the error pattern. Returns the process exit code.
    """
    buf: list[str] = []
    with Status(status_msg, console=console):
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            buf.append(line.rstrip())
        rc = proc.wait()
    if rc != 0:
        console.print()
        console.print(f"  [red]Command failed:[/] {' '.join(cmd)}")
        for line in buf[-20:]:
            console.print(f"    [dim]{line}[/]")
        hint = _diagnose_fix_failure(buf)
        if hint:
            console.print()
            console.print(
                Panel(
                    Text(hint, style="dim"),
                    title="[bold]Likely cause[/]",
                )
            )
        console.print()
    return rc


def _fix_engine(engine: str | None, status: str, detail: str) -> bool:
    """Show an actionable panel for the engine problem and offer a fix.

    Returns True if the engine is now usable, False otherwise. Safe to
    call with any combination — no-op for ``ready``.
    """
    if status == "ready":
        return True

    is_mac = platform.system() == "Darwin"

    if status == "not_installed":
        console.print()
        console.print(
            Panel(
                Text.assemble(
                    Text("No container engine found.\n\n", style="bold"),
                    Text(
                        "ClawBench runs every task inside a container, so you "
                        "need either Docker or Podman installed before any mode "
                        "(including Human mode) can work.\n\n"
                        "macOS:   brew install --cask docker\n"
                        "         — or —\n"
                        "         brew install podman && podman machine init && podman machine start\n\n"
                        "Linux:   sudo apt install podman   (or docker.io)\n\n"
                        "Windows: winget install Docker.DockerDesktop\n"
                        "         — or —\n"
                        "         winget install RedHat.Podman && podman machine init && podman machine start",
                        style="dim",
                    ),
                ),
                title="[bold]Container engine not installed[/]",
            )
        )
        console.print()
        return False

    if engine == "podman" and status == "podman_no_machine":
        console.print()
        console.print(
            Panel(
                Text.assemble(
                    Text("Podman needs a Linux VM on this platform.\n\n", style="bold"),
                    Text(
                        "On macOS and Windows, podman runs Linux containers "
                        "inside a small helper VM. You don't have one yet. "
                        "I can run these two commands for you now:\n\n"
                        "    podman machine init\n"
                        "    podman machine start\n\n"
                        "The first one downloads a ~1 GB VM image, so it "
                        "takes a few minutes.",
                        style="dim",
                    ),
                ),
                title="[bold]Podman machine not initialized[/]",
            )
        )
        console.print()
        ok = questionary.confirm(
            "Run `podman machine init && podman machine start` now?",
            default=True,
            style=STYLE,
        ).ask()
        if not ok:
            return False
        if (
            _run_streamed(
                ["podman", "machine", "init"],
                status_msg="Running podman machine init (downloads VM image, may take a few minutes)...",
            )
            != 0
        ):
            return False
        if (
            _run_streamed(
                ["podman", "machine", "start"],
                status_msg="Starting podman machine...",
            )
            != 0
        ):
            return False
        # Re-verify
        _, new_status, _ = _check_engine()
        if new_status == "ready":
            console.print("  [green]✓[/] Podman is now running.")
            return True
        return False

    if engine == "podman" and status == "podman_machine_stopped":
        console.print()
        console.print(
            Panel(
                Text.assemble(
                    Text("Podman machine is not running.\n\n", style="bold"),
                    Text(
                        "The Linux VM that podman uses to run containers is "
                        "currently stopped. I can start it for you with:\n\n"
                        "    podman machine start",
                        style="dim",
                    ),
                ),
                title="[bold]Podman machine stopped[/]",
            )
        )
        console.print()
        ok = questionary.confirm(
            "Run `podman machine start` now?",
            default=True,
            style=STYLE,
        ).ask()
        if not ok:
            return False
        if (
            _run_streamed(
                ["podman", "machine", "start"],
                status_msg="Starting podman machine...",
            )
            != 0
        ):
            return False
        _, new_status, _ = _check_engine()
        if new_status == "ready":
            console.print("  [green]✓[/] Podman is now running.")
            return True
        return False

    if engine == "podman" and status == "podman_low_memory":
        mem_mb = int(detail) if detail.isdigit() else 0
        console.print()
        console.print(
            Panel(
                Text.assemble(
                    Text(f"Podman machine has only {mem_mb} MB RAM.\n\n", style="bold"),
                    Text(
                        "ClawBench runs Chrome + an AI agent gateway inside "
                        "the container, which needs at least 4 GB RAM. With "
                        f"the current {mem_mb} MB the agent process will be "
                        "killed by the OOM killer.\n\n"
                        "I can stop the VM, increase its memory to 4 GB, and "
                        "restart it:\n\n"
                        "    podman machine stop\n"
                        "    podman machine set --memory 4096\n"
                        "    podman machine start",
                        style="dim",
                    ),
                ),
                title="[bold]Podman machine: not enough memory[/]",
            )
        )
        console.print()
        ok = questionary.confirm(
            "Resize podman machine to 4 GB RAM now?",
            default=True,
            style=STYLE,
        ).ask()
        if not ok:
            return False
        for cmd, msg in [
            (["podman", "machine", "stop"], "Stopping podman machine..."),
            (
                ["podman", "machine", "set", "--memory", "4096"],
                "Setting memory to 4096 MB...",
            ),
            (["podman", "machine", "start"], "Starting podman machine..."),
        ]:
            if _run_streamed(cmd, status_msg=msg) != 0:
                return False
        _, new_status, _ = _check_engine()
        if new_status == "ready":
            console.print("  [green]✓[/] Podman machine now has 4 GB RAM.")
            return True
        return False

    if engine == "docker" and status == "docker_not_running":
        console.print()
        console.print(
            Panel(
                Text.assemble(
                    Text("Docker daemon is not running.\n\n", style="bold"),
                    Text(
                        "The `docker` CLI is installed but can't reach the "
                        "daemon. On macOS/Windows this usually means Docker "
                        "Desktop isn't launched.",
                        style="dim",
                    ),
                ),
                title="[bold]Docker daemon unreachable[/]",
            )
        )
        console.print()
        if is_mac:
            ok = questionary.confirm(
                "Open Docker Desktop now? (you'll still need to wait "
                "for it to finish starting)",
                default=True,
                style=STYLE,
            ).ask()
            if ok:
                subprocess.run(["open", "-a", "Docker"])
                console.print(
                    "  [dim]Docker Desktop is starting — re-run ./run.sh "
                    "once its menu-bar icon stops animating.[/]"
                )
        else:
            console.print(
                "  [dim]Start the Docker daemon / Docker Desktop, then "
                "re-run ./run.sh.[/]"
            )
        return False

    # unknown_error — nothing to automate
    console.print()
    console.print(
        Panel(
            Text.assemble(
                Text("Container engine probe failed.\n\n", style="bold"),
                Text(
                    f"Engine: {engine}\n\n{detail or '(no details)'}",
                    style="dim",
                ),
            ),
            title="[bold]Engine check error[/]",
        )
    )
    console.print()
    return False


def main() -> None:
    global STYLE, ACCENT, ACCENT2

    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        console.print("Usage: clawbench")
        console.print()
        console.print("Launch the interactive ClawBench TUI.")
        console.print("For non-interactive runs, use clawbench-run or clawbench-batch.")
        return

    _require_tty()
    ensure_workspace_templates()
    os.chdir(WORKSPACE_ROOT)

    # Theme: load saved preference, or prompt on first run.
    # Everything rendered BEFORE _pick_theme() has to look OK on both
    # light and dark terminals, so we avoid cyan/blue accents here —
    # plain bold + the terminal's default foreground is the only safe
    # combination. Once the user picks a theme, we can use accent colors
    # again via the chosen STYLE.
    #
    # We treat "no models configured" as a first-run condition too — if
    # the user hasn't finished setup yet, we want them to confirm their
    # terminal theme before we show any colored onboarding UI, even if
    # they happen to have a stale saved theme from an earlier session.
    theme = _load_saved_theme()
    models = load_models()
    first_run = (theme is None) or (not models)
    if first_run:
        console.print()
        console.print("[bold]Welcome to ClawBench.[/]")
        theme = _pick_theme()
    assert theme is not None
    STYLE = _make_style(theme)
    # Apple HIG: Indigo for headers, Blue for inline accents
    if theme == "light":
        ACCENT, ACCENT2 = "#5856D6", "#007AFF"
    else:
        ACCENT, ACCENT2 = "#5E5CE6", "#0A84FF"

    dataset = _pick_dataset(DEFAULT_DATASET)
    if dataset is None:
        sys.exit(0)
    cases_dir_name = _dataset_cases_dir_name(dataset)
    cases = load_cases(cases_dir_name)
    dataset_summary = _dataset_summary(dataset)

    # Engine health check: every mode (including Human) needs a working
    # docker/podman. If it's broken, offer to fix it right now rather
    # than letting the user discover the problem after picking a model
    # and waiting through the build step.
    engine, engine_status, engine_detail = _check_engine()
    if engine_status != "ready":
        _fix_engine(engine, engine_status, engine_detail)
        # Re-probe so the menu knows whether run-modes are viable.
        engine, engine_status, engine_detail = _check_engine()

    # Onboarding: if there are no models configured, this is almost
    # certainly a fresh install (or someone who copied the example yaml
    # without editing it). Don't force the user to discover the
    # "Configure models" menu item — walk them into _add_model() right
    # now. They can still skip it and fall through to Human mode, which
    # doesn't need any LLM to run.
    if not models:
        _onboard_no_models()
        models = load_models()

    _show_header(models, cases, dataset)

    while True:
        mode = questionary.select(
            "Select mode:",
            choices=[
                questionary.Choice(
                    "Single run  (one model x one case)", value="single"
                ),
                questionary.Choice("Batch run   (models x cases)", value="batch"),
                questionary.Choice("Human mode  (no agent, noVNC)", value="human"),
                questionary.Choice("Change dataset", value="dataset"),
                questionary.Choice("Configure models", value="configure"),
                questionary.Choice("Change theme", value="theme"),
                questionary.Choice("Exit", value="exit"),
            ],
            style=STYLE,
        ).ask()

        if mode is None or mode == "exit":
            console.print("\n[dim]Bye.[/]")
            return

        if mode == "theme":
            theme = _pick_theme()
            STYLE = _make_style(theme)
            if theme == "light":
                ACCENT, ACCENT2 = "#5856D6", "#007AFF"
            else:
                ACCENT, ACCENT2 = "#5E5CE6", "#0A84FF"
            continue

        if mode == "dataset":
            selected = _pick_dataset(dataset)
            if selected is not None:
                dataset = selected
                cases_dir_name = _dataset_cases_dir_name(dataset)
                cases = load_cases(cases_dir_name)
                dataset_summary = _dataset_summary(dataset)
                _show_header(models, cases, dataset)
            continue

        if mode == "configure":
            mode_configure()
            models = load_models()
            _show_header(models, cases, dataset)
            continue

        # Every run mode (including Human) needs a live engine. If it
        # wasn't fixable earlier, try one more time now — the user may
        # have started Docker Desktop in another window, or we may be
        # catching a transient failure.
        if mode in ("single", "batch", "human"):
            engine, engine_status, engine_detail = _check_engine()
            if engine_status != "ready":
                if not _fix_engine(engine, engine_status, engine_detail):
                    console.print()
                    console.print(
                        "  [yellow]Container engine is still not "
                        "ready — can't launch this mode.[/]"
                    )
                    continue

        # Human mode is intentionally allowed with zero models — it
        # drives the browser via noVNC without any LLM at all.
        if mode == "human":
            mode_human(cases, cases_dir_name, dataset_summary)
            continue

        # Single / batch both need at least one configured model. Instead
        # of printing an error and looping, offer to configure one now.
        if mode in ("single", "batch") and not models:
            console.print()
            console.print("  [dim]This mode needs at least one configured model.[/]")
            add_now = questionary.confirm(
                "Add a model now?", default=True, style=STYLE
            ).ask()
            if add_now:
                data = load_models_data()
                _add_model(data)
                models = load_models()
            continue

        if mode == "single":
            mode_single(models, cases, cases_dir_name, dataset_summary)
        elif mode == "batch":
            mode_batch(models, cases, cases_dir_name, dataset_summary, dataset)


def _onboard_no_models() -> None:
    """First-run guidance when ``models/models.yaml`` has zero entries.

    Shown after the theme picker but before the main menu. The user has
    three real options: add a model now, skip straight to Human mode
    (which doesn't need any LLM), or quit.
    """
    console.print()
    console.print(
        Panel(
            Text.assemble(
                Text("No models configured yet.\n\n", style="bold"),
                Text(
                    "ClawBench needs at least one model entry in "
                    "models/models.yaml before it can run agent-mode tasks. "
                    "Let's add one now — it takes about 30 seconds and you "
                    "only need your API key.\n\n"
                    "You can also skip this and jump straight to Human mode, "
                    "which drives the browser via noVNC without any LLM.",
                    style="dim",
                ),
            ),
            title="[bold]First-run setup[/]",
        )
    )
    console.print()

    choice = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice("Add a model now  (recommended)", value="add"),
            questionary.Choice("Skip — I'll use Human mode", value="skip"),
            questionary.Choice("Quit", value="quit"),
        ],
        style=STYLE,
    ).ask()

    if choice is None or choice == "quit":
        console.print("\n[dim]Bye.[/]")
        sys.exit(0)

    if choice == "add":
        data = load_models_data()
        _add_model(data)
        # Loop once more in case the user cancelled mid-wizard: we want
        # them to land in a sane state (either configured or explicitly
        # choosing to skip to Human mode).
        if not load_models():
            console.print()
            console.print(
                "  [dim]No model was saved. You can still use Human mode "
                "from the menu, or pick 'Configure models' later.[/]"
            )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[dim]Aborted.[/]")
        sys.exit(0)
