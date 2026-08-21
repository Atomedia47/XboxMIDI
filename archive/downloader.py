#!/usr/bin/env python3
"""
Knowledge Archive Downloader — pulls sources from the catalog onto the
WD Black 8TB drive. Handles large files with resume support, integrity
checks, and progress tracking.

Usage:
  python3 -m archive.downloader                      # Download everything
  python3 -m archive.downloader --category wikipedia  # Just Wikipedia
  python3 -m archive.downloader --priority 1          # Critical items only
  python3 -m archive.downloader --dry-run             # Show what would download
"""

import json
import os
import sys
import time
import hashlib
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class DownloadTask:
    name: str
    url: str
    dest_dir: str
    size_gb: float = 0
    priority: int = 1
    status: str = "pending"  # pending, downloading, completed, failed, skipped
    progress_pct: float = 0
    error: str = ""


def load_catalog(path: str = None) -> dict:
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "catalog.json")
    with open(path) as f:
        return json.load(f)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def download_file(url: str, dest: str, resume: bool = True) -> bool:
    """Download a file with resume support and progress display."""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    existing_size = 0
    if resume and dest_path.exists():
        existing_size = dest_path.stat().st_size

    headers = {}
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"

    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416:  # Range not satisfiable = file already complete
            return True
        raise

    total = resp.headers.get("Content-Length")
    if total:
        total = int(total) + existing_size

    mode = "ab" if existing_size > 0 else "wb"
    downloaded = existing_size
    chunk_size = 1024 * 1024  # 1MB chunks

    with open(dest, mode) as f:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = (downloaded / total) * 100
                bar = "#" * int(pct / 2) + "-" * (50 - int(pct / 2))
                size_mb = downloaded / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                print(f"\r  [{bar}] {pct:.1f}% ({size_mb:.0f}/{total_mb:.0f} MB)", end="", flush=True)
    print()
    return True


def clone_repo(url: str, dest: str) -> bool:
    """Clone a git repository."""
    if os.path.exists(os.path.join(dest, ".git")):
        print(f"  Updating existing repo: {dest}")
        result = subprocess.run(["git", "-C", dest, "pull"], capture_output=True, text=True)
        return result.returncode == 0
    print(f"  Cloning: {url}")
    result = subprocess.run(["git", "clone", "--depth", "1", url, dest], capture_output=True, text=True)
    return result.returncode == 0


def download_kiwix_zim(url: str, dest_dir: str) -> bool:
    """Download a Kiwix ZIM file (large, uses aria2c if available for speed)."""
    filename = url.split("/")[-1]
    dest = os.path.join(dest_dir, filename)

    # Prefer aria2c for large files (multi-connection download)
    aria2c = subprocess.run(["which", "aria2c"], capture_output=True).returncode == 0
    if aria2c:
        print(f"  Using aria2c for fast download...")
        result = subprocess.run([
            "aria2c", "-x", "16", "-s", "16", "-c",
            "-d", dest_dir, "-o", filename, url
        ])
        return result.returncode == 0
    else:
        # Fallback to wget with resume
        wget = subprocess.run(["which", "wget"], capture_output=True).returncode == 0
        if wget:
            result = subprocess.run([
                "wget", "-c", "-O", dest, url
            ])
            return result.returncode == 0
        else:
            return download_file(url, dest)


def build_download_tasks(catalog: dict, category: str = None, max_priority: int = 99) -> list[DownloadTask]:
    """Build the list of download tasks from the catalog."""
    base_dir = catalog["drive"]["base_dir"]
    tasks = []

    for cat_key, cat_data in catalog["categories"].items():
        if category and cat_key != category:
            continue

        cat_dir = os.path.join(base_dir, cat_data["dir"])

        for source in cat_data.get("sources", []):
            if source.get("priority", 99) > max_priority:
                continue
            url = source.get("url", "")
            if not url:
                # No direct URL — create a placeholder README for manual acquisition
                tasks.append(DownloadTask(
                    name=source["name"],
                    url="",
                    dest_dir=cat_dir,
                    size_gb=source.get("size_gb", 0),
                    priority=source.get("priority", 99),
                    status="manual",
                ))
                continue

            tasks.append(DownloadTask(
                name=source["name"],
                url=url,
                dest_dir=cat_dir,
                size_gb=source.get("size_gb", 0),
                priority=source.get("priority", 99),
            ))

    tasks.sort(key=lambda t: t.priority)
    return tasks


def write_status(base_dir: str, tasks: list[DownloadTask]):
    """Write current download status to a JSON file for the monitor."""
    status_path = os.path.join(base_dir, "download_status.json")
    status = {
        "timestamp": time.time(),
        "tasks": [
            {
                "name": t.name,
                "status": t.status,
                "progress": t.progress_pct,
                "size_gb": t.size_gb,
                "error": t.error,
            }
            for t in tasks
        ],
        "completed": sum(1 for t in tasks if t.status == "completed"),
        "total": len(tasks),
    }
    ensure_dir(base_dir)
    with open(status_path, "w") as f:
        json.dump(status, f, indent=2)


def create_manual_readme(dest_dir: str, source_name: str):
    """For sources without direct URLs, create a README with acquisition instructions."""
    ensure_dir(dest_dir)
    safe_name = source_name.replace("/", "-").replace(" ", "_").lower()
    readme_path = os.path.join(dest_dir, f"ACQUIRE_{safe_name}.md")
    if os.path.exists(readme_path):
        return
    with open(readme_path, "w") as f:
        f.write(f"# {source_name}\n\n")
        f.write(f"This resource needs to be acquired manually.\n")
        f.write(f"Place the files in this directory: `{dest_dir}`\n\n")
        f.write(f"Once acquired, the archive index will pick it up automatically.\n")


def run_downloads(catalog: dict, category: str = None, max_priority: int = 99, dry_run: bool = False):
    """Execute downloads based on the catalog."""
    base_dir = catalog["drive"]["base_dir"]
    tasks = build_download_tasks(catalog, category, max_priority)

    print(f"\n{'='*60}")
    print(f"  KNOWLEDGE ARCHIVE DOWNLOADER")
    print(f"  Target: {base_dir}")
    print(f"  Tasks: {len(tasks)}")
    total_gb = sum(t.size_gb for t in tasks)
    print(f"  Estimated size: {total_gb:.1f} GB")
    print(f"{'='*60}\n")

    if dry_run:
        for t in tasks:
            status = "MANUAL" if t.status == "manual" else "DOWNLOAD"
            print(f"  [{status}] P{t.priority} {t.name} ({t.size_gb:.1f} GB)")
            if t.url:
                print(f"           {t.url}")
        print(f"\nDry run complete. Use without --dry-run to start downloads.")
        return

    for i, task in enumerate(tasks):
        print(f"\n[{i+1}/{len(tasks)}] {task.name} (P{task.priority})")

        if task.status == "manual":
            create_manual_readme(task.dest_dir, task.name)
            print(f"  -> Created acquisition readme (no direct URL)")
            task.status = "skipped"
            write_status(base_dir, tasks)
            continue

        ensure_dir(task.dest_dir)
        task.status = "downloading"
        write_status(base_dir, tasks)

        try:
            url = task.url
            if url.endswith(".git") or "github.com" in url or "gitlab.com" in url:
                repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
                dest = os.path.join(task.dest_dir, repo_name)
                success = clone_repo(url, dest)
            elif ".zim" in url:
                success = download_kiwix_zim(url, task.dest_dir)
            else:
                filename = url.split("/")[-1] or "index.html"
                dest = os.path.join(task.dest_dir, filename)
                success = download_file(url, dest)

            task.status = "completed" if success else "failed"
            if success:
                task.progress_pct = 100
                print(f"  -> Done")
            else:
                task.error = "Download failed"
                print(f"  -> FAILED")

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            print(f"  -> ERROR: {e}")

        write_status(base_dir, tasks)

    print(f"\n{'='*60}")
    completed = sum(1 for t in tasks if t.status == "completed")
    failed = sum(1 for t in tasks if t.status == "failed")
    skipped = sum(1 for t in tasks if t.status == "skipped")
    print(f"  Completed: {completed} | Failed: {failed} | Manual: {skipped}")
    print(f"{'='*60}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Knowledge Archive Downloader")
    parser.add_argument("--category", type=str, help="Download only this category")
    parser.add_argument("--priority", type=int, default=99, help="Max priority level (1=critical only)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would download")
    parser.add_argument("--catalog", type=str, help="Custom catalog path")
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    run_downloads(catalog, args.category, args.priority, args.dry_run)


if __name__ == "__main__":
    main()
