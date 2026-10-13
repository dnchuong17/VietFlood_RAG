"""Build source_registry.jsonl deterministically from Markdown front matter."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from kb_common import read_jsonl, read_markdown, sha256_text, write_jsonl
from pipeline_config import (
    ELIGIBLE_REPRESENTATIONS,
    EMBEDDING_MODEL,
    MARKDOWN_DIR,
    PROJECT_ROOT,
    SOURCE_REGISTRY_PATH,
    TOPICS_BY_PREFIX,
)


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def infer_publisher(title: str) -> str:
    for separator in (" — ", " - ", ":"):
        if separator in title:
            return title.split(separator, 1)[0].strip()
    return title.strip()


def infer_country(metadata: dict[str, Any]) -> str:
    title = str(metadata.get("title", "")).lower()
    url = str(metadata.get("source_url", "")).lower()
    vietnam_markers = (
        "việt nam",
        "vietnam/vi/",
        ".gov.vn",
        "baochinhphu.vn",
    )
    return "VN" if any(marker in title or marker in url for marker in vietnam_markers) else "GLOBAL"


def infer_topics(source_ids: list[str]) -> list[str]:
    topics: set[str] = set()
    for source_id in source_ids:
        topics.update(TOPICS_BY_PREFIX.get(source_id[:1], ["FLOOD_KNOWLEDGE"]))
    if any(source_id in {"H04"} for source_id in source_ids):
        topics.add("FOOD_SAFETY")
    if any(source_id in {"H01", "H02", "H03", "H05", "H06"} for source_id in source_ids):
        topics.add("WATER_SAFETY")
    if any(source_id in {"M01", "M02", "F04"} for source_id in source_ids):
        topics.add("DROWNING")
    return sorted(topics)


def exclusion_reason(representation: str, status: str) -> str | None:
    if representation == "dynamic_source_record":
        return "dynamic_source_requires_live_adapter"
    if representation == "access_record":
        return "broken_or_redirected_source"
    if representation == "source_index_description":
        return "index_page_without_primary_content"
    if status.startswith("BROKEN"):
        return "broken_or_redirected_source"
    return None


def build_registry(markdown_dir: Path) -> list[dict[str, Any]]:
    previous = {r["document_id"]: r for r in read_jsonl(SOURCE_REGISTRY_PATH)} if SOURCE_REGISTRY_PATH.exists() else {}
    records: list[dict[str, Any]] = []
    for path in sorted(markdown_dir.glob("*.md"), key=lambda item: item.name.lower()):
        metadata, body = read_markdown(path)
        source_ids = as_list(metadata.get("source_ids"))
        if not source_ids:
            raise ValueError(f"Missing source_ids: {path}")
        representation = str(metadata.get("representation", ""))
        verification_status = str(metadata.get("verification_status", ""))
        eligible = representation in ELIGIBLE_REPRESENTATIONS
        reason = None if eligible else exclusion_reason(representation, verification_status)
        if not eligible and reason is None:
            reason = "representation_not_eligible"

        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        title = str(metadata.get("title", path.stem))
        record = {
            "document_id": source_ids[0],
            "source_ids": source_ids,
            "file_name": path.name,
            "file_path": relative_path,
            "title": title,
            "publisher": infer_publisher(title),
            "source_url": str(metadata.get("source_url", "")),
            "language": str(metadata.get("language", "vi")),
            "country_code": infer_country(metadata),
            "hazard_types": ["FLOOD"],
            "topics": infer_topics(source_ids),
            "representation": representation,
            "verification_status": verification_status,
            "medical_review_required": bool(metadata.get("medical_review_required", False)),
            "chemical_dosing_review_required": bool(
                metadata.get("chemical_dosing_review_required", False)
            ),
            "ingest_eligible": eligible,
            "exclusion_reason": reason,
            "review_status": "APPROVED" if eligible else "EXCLUDED",
            "license_status": "APPROVED_FOR_RAG" if eligible else "REVIEW_REQUIRED",
            "public_retrieval": eligible,
            "document_version": int(previous.get(source_ids[0], {}).get("document_version", 0)) + (0 if previous.get(source_ids[0], {}).get("content_hash") == sha256_text(body) and previous.get(source_ids[0], {}).get("title") == title and previous.get(source_ids[0], {}).get("source_url") == str(metadata.get("source_url", "")) else 1),
            "embedding_model": EMBEDDING_MODEL,
            "accessed_at": metadata.get("accessed_at"),
            "rechecked_at": metadata.get("rechecked_at"),
            "content_hash": sha256_text(body),
        }
        records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown-dir", type=Path, default=MARKDOWN_DIR)
    parser.add_argument("--output", type=Path, default=SOURCE_REGISTRY_PATH)
    args = parser.parse_args()

    records = build_registry(args.markdown_dir)
    eligible = sum(bool(record["ingest_eligible"]) for record in records)
    write_jsonl(args.output, records)
    print(f"Wrote {len(records)} sources to {args.output}")
    print(f"Eligible for staging: {eligible}; excluded: {len(records) - eligible}")


if __name__ == "__main__":
    main()

