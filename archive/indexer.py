#!/usr/bin/env python3
"""
Knowledge Archive Indexer — scans the archive drive, builds a searchable
index of everything stored, and serves it through the monitor dashboard.

Run after downloads to catalog what's actually on the drive.
"""

import json
import os
import time
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ArchiveEntry:
    name: str
    path: str
    category: str
    size_bytes: int = 0
    file_count: int = 0
    file_types: dict = field(default_factory=dict)
    indexed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "category": self.category,
            "size_bytes": self.size_bytes,
            "size_human": self._human_size(),
            "file_count": self.file_count,
            "file_types": self.file_types,
            "indexed_at": self.indexed_at,
        }

    def _human_size(self) -> str:
        size = self.size_bytes
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


def scan_directory(path: str) -> tuple[int, int, dict]:
    """Scan a directory tree, return (total_size, file_count, extension_counts)."""
    total_size = 0
    file_count = 0
    extensions: dict[str, int] = {}

    try:
        for root, dirs, files in os.walk(path):
            # Skip .git directories
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in files:
                filepath = os.path.join(root, f)
                try:
                    size = os.path.getsize(filepath)
                    total_size += size
                    file_count += 1
                    ext = Path(f).suffix.lower() or "(none)"
                    extensions[ext] = extensions.get(ext, 0) + 1
                except OSError:
                    pass
    except PermissionError:
        pass

    return total_size, file_count, extensions


def build_index(base_dir: str, catalog: dict) -> dict:
    """Scan the archive and build a complete index."""
    index = {
        "base_dir": base_dir,
        "indexed_at": time.time(),
        "categories": {},
        "totals": {
            "size_bytes": 0,
            "file_count": 0,
            "categories": 0,
            "entries": 0,
        },
    }

    for cat_key, cat_data in catalog.get("categories", {}).items():
        cat_dir = os.path.join(base_dir, cat_data["dir"])
        if not os.path.exists(cat_dir):
            continue

        cat_entries = []
        cat_size = 0
        cat_files = 0

        # Scan each subdirectory as a separate entry
        try:
            items = sorted(os.listdir(cat_dir))
        except PermissionError:
            continue

        for item in items:
            item_path = os.path.join(cat_dir, item)
            if os.path.isdir(item_path):
                size, count, types = scan_directory(item_path)
                entry = ArchiveEntry(
                    name=item,
                    path=item_path,
                    category=cat_key,
                    size_bytes=size,
                    file_count=count,
                    file_types=types,
                )
                cat_entries.append(entry.to_dict())
                cat_size += size
                cat_files += count
            elif os.path.isfile(item_path):
                size = os.path.getsize(item_path)
                ext = Path(item).suffix.lower()
                entry = ArchiveEntry(
                    name=item,
                    path=item_path,
                    category=cat_key,
                    size_bytes=size,
                    file_count=1,
                    file_types={ext: 1} if ext else {},
                )
                cat_entries.append(entry.to_dict())
                cat_size += size
                cat_files += 1

        if cat_entries:
            index["categories"][cat_key] = {
                "description": cat_data.get("description", ""),
                "dir": cat_data["dir"],
                "entries": cat_entries,
                "total_size_bytes": cat_size,
                "total_size_human": ArchiveEntry(
                    name="", path="", category="", size_bytes=cat_size
                )._human_size(),
                "total_files": cat_files,
            }
            index["totals"]["size_bytes"] += cat_size
            index["totals"]["file_count"] += cat_files
            index["totals"]["entries"] += len(cat_entries)
            index["totals"]["categories"] += 1

    # Human readable total
    index["totals"]["size_human"] = ArchiveEntry(
        name="", path="", category="", size_bytes=index["totals"]["size_bytes"]
    )._human_size()

    return index


def save_index(index: dict, base_dir: str):
    """Save the index to disk."""
    index_path = os.path.join(base_dir, "archive_index.json")
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2, default=str)
    print(f"Index saved: {index_path}")
    print(f"  Categories: {index['totals']['categories']}")
    print(f"  Entries: {index['totals']['entries']}")
    print(f"  Files: {index['totals']['file_count']}")
    print(f"  Total size: {index['totals']['size_human']}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Knowledge Archive Indexer")
    parser.add_argument("--base-dir", type=str, help="Archive base directory")
    parser.add_argument("--catalog", type=str, help="Catalog JSON path")
    args = parser.parse_args()

    catalog_path = args.catalog or os.path.join(os.path.dirname(__file__), "catalog.json")
    with open(catalog_path) as f:
        catalog = json.load(f)

    base_dir = args.base_dir or catalog["drive"]["base_dir"]
    print(f"Indexing archive at: {base_dir}")

    index = build_index(base_dir, catalog)
    save_index(index, base_dir)


if __name__ == "__main__":
    main()
