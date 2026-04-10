"""Minimal interactive TUI for ClawBench — select mode, models, and cases."""

import multiprocessing
import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_YAML = PROJECT_ROOT / "models" / "models.yaml"
CASES_DIR = PROJECT_ROOT / "test-cases"

API_TYPES = ["openai-completions", "openai-responses", "anthropic-messages", "google-generative-ai"]
THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "adaptive"]


def load_models_data() -> dict:
    if not MODELS_YAML.exists():
        return {}
    return yaml.safe_load(MODELS_YAML.read_text()) or {}


def save_models(data: dict) -> None:
    MODELS_YAML.parent.mkdir(parents=True, exist_ok=True)
    MODELS_YAML.write_text(yaml.safe_dump(data, sort_keys=False))


def load_models() -> list[str]:
    return sorted(load_models_data().keys())


def load_cases() -> list[str]:
    cases = sorted(p.parent.name for p in CASES_DIR.glob("*/task.json"))
    if not cases:
        print("ERROR: no test cases found in test-cases/")
        sys.exit(1)
    return cases


def _recommend_concurrent() -> int:
    """Recommend max concurrent jobs based on CPU cores and RAM.
    Each container uses ~2 CPU cores and ~2 GB RAM."""
    cpus = multiprocessing.cpu_count()
    try:
        mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        mem_gb = mem_bytes / (1024 ** 3)
    except (ValueError, OSError):
        mem_gb = 8  # fallback
    by_cpu = cpus // 2
    by_ram = int(mem_gb // 2)
    recommended = max(1, min(by_cpu, by_ram))
    print(f"  System: {cpus} CPUs, {mem_gb:.0f} GB RAM — recommended max: {recommended}")
    return recommended


def _has_id_prefix(items: list[str]) -> bool:
    """Check if items have numeric ID prefixes (e.g. '001-foo', '999-bar')."""
    return all(it.split("-", 1)[0].isdigit() for it in items) if items else False


def _id_map(items: list[str]) -> dict[str, str]:
    """Build ID prefix → full name lookup. Maps both '001' and '1' to the item."""
    mapping: dict[str, str] = {}
    for it in items:
        prefix = it.split("-", 1)[0]
        mapping[prefix] = it
        # Also map without leading zeros (e.g. "1" → "001-...")
        stripped = prefix.lstrip("0") or "0"
        mapping[stripped] = it
    return mapping


def pick_one(items: list[str], prompt: str) -> str:
    use_ids = _has_id_prefix(items)
    if use_ids:
        for item in items:
            prefix = item.split("-", 1)[0]
            print(f"  {prefix}  {item}")
    else:
        for i, item in enumerate(items, 1):
            print(f"  {i:>3}. {item}")
    while True:
        choice = input(f"\n{prompt}: ").strip()
        if not choice:
            print("  Invalid choice, try again.")
            continue
        if use_ids:
            mapping = _id_map(items)
            if choice in mapping:
                return mapping[choice]
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(items):
                    return items[idx]
            except ValueError:
                pass
        print("  Invalid choice, try again.")


def pick_many(items: list[str], prompt: str) -> list[str]:
    use_ids = _has_id_prefix(items)
    if use_ids:
        for item in items:
            prefix = item.split("-", 1)[0]
            print(f"  {prefix}  {item}")
    else:
        for i, item in enumerate(items, 1):
            print(f"  {i:>3}. {item}")
    print(f"\nEnter IDs, a range (e.g. 1-50), comma-separated, or * for all.")
    while True:
        choice = input(f"{prompt}: ").strip()
        if not choice:
            print("  Invalid input, try again.")
            continue
        if choice == "*":
            return list(items)
        if use_ids:
            mapping = _id_map(items)
        selected = []
        try:
            for part in choice.split(","):
                part = part.strip()
                if "-" in part:
                    lo, hi = part.split("-", 1)
                    for i in range(int(lo), int(hi) + 1):
                        key = str(i)
                        if use_ids:
                            if key in mapping:
                                selected.append(mapping[key])
                        elif 1 <= i <= len(items):
                            selected.append(items[i - 1])
                else:
                    if use_ids:
                        if part in mapping:
                            selected.append(mapping[part])
                    else:
                        idx = int(part) - 1
                        if 0 <= idx < len(items):
                            selected.append(items[idx])
        except ValueError:
            pass
        if selected:
            return list(dict.fromkeys(selected))  # dedupe, preserve order
        print("  Invalid input, try again.")


def run_cmd(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}\n")
    os.execvp(cmd[0], cmd)


def mode_single(models: list[str], cases: list[str]) -> None:
    print("\n--- Select model ---\n")
    model = pick_one(models, "Model")

    print("\n--- Select test case ---\n")
    case = pick_one(cases, "Case")

    run_cmd([
        "uv", "run", "--project", "test-driver",
        "test-driver/run.py", f"test-cases/{case}", model,
    ])


def mode_batch(models: list[str], cases: list[str]) -> None:
    print("\n--- Select models ---\n")
    selected_models = pick_many(models, "Models")

    print("\n--- Case selection ---")
    print("  1. All cases")
    print("  2. Case range (e.g. 1-50)")
    print("  3. Pick specific cases")
    while True:
        case_mode = input("\nCase selection [1-3]: ").strip()
        if case_mode in ("1", "2", "3"):
            break
        print("  Invalid choice, try again.")

    case_args: list[str] = []
    if case_mode == "1":
        case_args = ["--all-cases"]
    elif case_mode == "2":
        r = input("Range (e.g. 1-50): ").strip()
        case_args = ["--case-range", r]
    else:
        print()
        selected_cases = pick_many(cases, "Cases")
        case_args = ["--cases"] + [f"test-cases/{c}" for c in selected_cases]

    recommended = _recommend_concurrent()
    while True:
        concurrent = input(f"\nMax concurrent jobs [{recommended}]: ").strip() or str(recommended)
        try:
            int(concurrent)
            break
        except ValueError:
            print("  Must be a number.")

    dry = input("Dry run first? [y/N]: ").strip().lower()

    cmd = [
        "uv", "run", "--project", "test-driver",
        "test-driver/batch.py",
        "--models", *selected_models,
        *case_args,
        "--max-concurrent", concurrent,
    ]
    if dry == "y":
        cmd.append("--dry-run")

    run_cmd(cmd)


def mode_human(cases: list[str]) -> None:
    print("\n--- Select test case ---\n")
    case = pick_one(cases, "Case")

    run_cmd([
        "uv", "run", "--project", "test-driver",
        "test-driver/run.py", f"test-cases/{case}", "--human",
    ])


def mode_configure() -> None:
    while True:
        data = load_models_data()
        if data:
            print(f"\n  Current models: {', '.join(sorted(data))}\n")
        else:
            print("\n  No models configured yet.\n")

        print("--- Add a model ---\n")

        # Model name
        while True:
            name = input("Model name: ").strip()
            if not name:
                print("  Name cannot be empty.")
                continue
            if any(c in name for c in "/ \\:*?\"<>|"):
                print("  Name contains illegal characters.")
                continue
            if name in data:
                print(f"  '{name}' already exists.")
                continue
            break

        # Base URL
        base_url = ""
        while not base_url:
            base_url = input("Base URL: ").strip()

        # API type
        print("API type [openai-completions]:")
        for i, t in enumerate(API_TYPES, 1):
            print(f"  {i}. {t}")
        while True:
            api_choice = input(f"Select [1-{len(API_TYPES)}] or Enter for default: ").strip()
            if not api_choice:
                api_type = API_TYPES[0]
                break
            try:
                idx = int(api_choice) - 1
                if 0 <= idx < len(API_TYPES):
                    api_type = API_TYPES[idx]
                    break
            except ValueError:
                pass
            print("  Invalid choice, try again.")

        # API key
        api_key = ""
        while not api_key:
            api_key = input("API key: ").strip()

        # Thinking level
        print("Thinking level [medium]:")
        for i, t in enumerate(THINKING_LEVELS, 1):
            print(f"  {i}. {t}")
        while True:
            tl_choice = input(f"Select [1-{len(THINKING_LEVELS)}] or Enter for default: ").strip()
            if not tl_choice:
                thinking_level = "medium"
                break
            try:
                idx = int(tl_choice) - 1
                if 0 <= idx < len(THINKING_LEVELS):
                    thinking_level = THINKING_LEVELS[idx]
                    break
            except ValueError:
                pass
            print("  Invalid choice, try again.")

        # Save
        data[name] = {
            "api_key": api_key,
            "base_url": base_url,
            "api_type": api_type,
            "thinking_level": thinking_level,
        }
        save_models(data)
        print(f"\n  Saved {name} to {MODELS_YAML}")

        again = input("\nAdd another model? [y/N]: ").strip().lower()
        if again != "y":
            break


def main() -> None:
    os.chdir(PROJECT_ROOT)

    models = load_models()
    cases = load_cases()

    print("\n=== ClawBench ===\n")
    print(f"  Models: {len(models)}   Cases: {len(cases)}\n")
    print("  1. Single run (one model × one case)")
    print("  2. Batch run (models × cases)")
    print("  3. Human mode (no agent, noVNC)")
    print("  4. Configure models")

    while True:
        mode = input("\nSelect mode [1-4]: ").strip()
        if mode in ("1", "2", "3", "4"):
            break
        print("  Invalid choice, try again.")

    if mode == "4":
        mode_configure()
        return

    if not models:
        print("ERROR: no models configured. Run option 4 first, or copy models.example.yaml to models.yaml")
        sys.exit(1)

    if mode == "1":
        mode_single(models, cases)
    elif mode == "2":
        mode_batch(models, cases)
    else:
        mode_human(cases)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(0)
