"""Write the candidate-record JSON schema: the engine's contract for 004/006.

Run from backend/:  uv run python scripts/export_record_schema.py
A test fails if the committed schema is out of date.
"""

import json
from pathlib import Path

from sazon_screening.engine.record import CandidateRecord

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "specs"
    / "002-screening-engine"
    / "candidate-record.schema.json"
)


def main() -> None:
    schema = CandidateRecord.model_json_schema()
    SCHEMA_FILE.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {SCHEMA_FILE}")


if __name__ == "__main__":
    main()
