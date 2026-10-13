"""Parse approved Markdown sources into structured document JSONL."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from kb_common import normalize_text, read_jsonl, read_markdown, write_jsonl
from pipeline_config import PARSED_DOCUMENTS_PATH, PROJECT_ROOT, SOURCE_REGISTRY_PATH


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def split_sections(body: str) -> list[dict[str, Any]]:
    """Split Markdown by headings while retaining a hierarchical section path."""
    sections: list[dict[str, Any]] = []
    heading_stack: list[str] = []
    content_lines: list[str] = []

    def flush() -> None:
        content = normalize_text("\n".join(content_lines))
        if content:
            sections.append(
                {
                    "section_index": len(sections),
                    "section_path": heading_stack.copy(),
                    "text": content,
                }
            )
        content_lines.clear()

    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack[:] = heading_stack[: level - 1]
            while len(heading_stack) < level - 1:
                heading_stack.append("")
            heading_stack.append(title)
        else:
            content_lines.append(line)
    flush()
    return sections


def parse_registry_record(record: dict[str, Any]) -> dict[str, Any]:
    path = PROJECT_ROOT / record["file_path"]
    metadata, body = read_markdown(path)
    actual_ids = [str(item) for item in metadata.get("source_ids", [])]
    if actual_ids != record["source_ids"]:
        raise ValueError(f"source_ids mismatch for {path}")
    if not body:
        raise ValueError(f"Empty Markdown body: {path}")
    sections = split_sections(body)
    if not sections:
        raise ValueError(f"No content sections found: {path}")
    return {
        "document_id": record["document_id"],
        "document_version": record["document_version"],
        "file_name": record["file_name"],
        "file_path": record["file_path"],
        "title": record["title"],
        "body": body,
        "sections": sections,
        "metadata": record,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=SOURCE_REGISTRY_PATH)
    parser.add_argument("--output", type=Path, default=PARSED_DOCUMENTS_PATH)
    parser.add_argument(
        "--include-excluded",
        action="store_true",
        help="Parse excluded registry records as well; disabled for normal ingestion.",
    )
    args = parser.parse_args()

    registry = read_jsonl(args.registry)
    selected = [
        record
        for record in registry
        if args.include_excluded or bool(record.get("ingest_eligible"))
    ]
    documents = [parse_registry_record(record) for record in selected]
    write_jsonl(args.output, documents)
    print(f"Parsed {len(documents)} documents into {args.output}")


if __name__ == "__main__":
    main()

