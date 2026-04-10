"""Optional HuggingFace dataset upload for ClawBench runs."""

import json
from datetime import datetime, timezone
from pathlib import Path


def hf_upload_enabled(env: dict[str, str]) -> bool:
    """Check if HF_TOKEN and HF_REPO_ID are configured."""
    return bool(env.get("HF_TOKEN")) and bool(env.get("HF_REPO_ID"))


def upload_run(output_dir: Path, repo_path_prefix: str, env: dict[str, str]) -> None:
    """Upload a run's output directory to HuggingFace, then replace local data/ with a marker.

    Args:
        output_dir: Local output path (contains run-meta.json, eval-schema.json, data/).
        repo_path_prefix: Path inside the HF repo, e.g. "model/case-model-ts".
        env: Dict with HF_TOKEN and HF_REPO_ID.
    """
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("  WARNING: huggingface_hub not installed, skipping upload")
        return

    token = env["HF_TOKEN"]
    repo_id = env["HF_REPO_ID"]
    api = HfApi(token=token)

    try:
        commit_info = api.upload_folder(
            folder_path=str(output_dir),
            repo_id=repo_id,
            repo_type="dataset",
            path_in_repo=repo_path_prefix,
            ignore_patterns=[".my-info-tmp/**"],
            commit_message=f"Add run: {repo_path_prefix}",
        )
        commit_url = getattr(commit_info, "commit_url", None) or ""
        print(f"  Uploaded to HF: {repo_id}/{repo_path_prefix}")

        # Replace local data/ with a lightweight marker
        marker = {
            "repo_id": repo_id,
            "path_in_repo": repo_path_prefix,
            "commit_url": commit_url,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        (output_dir / "uploaded.json").write_text(json.dumps(marker, indent=2))

    except Exception as e:
        print(f"  WARNING: HuggingFace upload failed: {e}")


def upload_file(local_path: Path, path_in_repo: str, env: dict[str, str]) -> None:
    """Upload a single file to HuggingFace (e.g. batch-summary.json)."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("  WARNING: huggingface_hub not installed, skipping upload")
        return

    token = env["HF_TOKEN"]
    repo_id = env["HF_REPO_ID"]
    api = HfApi(token=token)

    try:
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=path_in_repo,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Add {path_in_repo}",
        )
        print(f"  Uploaded to HF: {repo_id}/{path_in_repo}")
    except Exception as e:
        print(f"  WARNING: HuggingFace upload failed: {e}")
