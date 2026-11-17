"""Export the clauses and extracted values of the sample folder for the presentation page.

The "From paper to rows" page (reports/presentation/paper-to-rows.html) embeds, for each of
the ten sample contracts, the clauses the pipeline stored (id, type, page, text) and the field
values it extracted (field, value, confidence, source clause, page). This script reads them from
the database after the sample folder has been loaded, and writes them as JSON.

Usage (from the repository root, with the hotel database loaded and the sample folder read):

    DATABASE_URL=postgresql://vmo:vmo@localhost:5432/vmo_hotel \
        python scripts/export_presentation_data.py > reports/presentation/paper-to-rows-data.json

Then paste the JSON into the <script type="application/json" id="docs-data"> block of the page,
replacing "</" with "<\\/" so the browser does not close the script early. The contract ids in the
page (53-62) must match the ids the database gave the sample files; if they differ, update FOLDER
and ROWS at the top of the page's script as well.
"""

from __future__ import annotations

import json
import os
import sys

import psycopg

SAMPLE_PREFIX = "uploads/samples/"


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql://vmo:vmo@localhost:5432/vmo_hotel"
    )
    # SQLAlchemy URLs carry a driver name that psycopg does not accept.
    return url.replace("postgresql+psycopg://", "postgresql://")


def export(conn: psycopg.Connection) -> dict[int, dict]:
    out: dict[int, dict] = {}
    contracts = conn.execute(
        "select id, title from contracts where source_path like %s order by id",
        (SAMPLE_PREFIX + "%",),
    ).fetchall()
    for cid, title in contracts:
        clauses = [
            {"id": i, "t": t, "p": p, "x": " ".join((x or "").split())}
            for i, t, p, x in conn.execute(
                "select id, clause_type, page, text from clauses"
                " where contract_id = %s order by page, id",
                (cid,),
            )
        ]
        fields = [
            {"f": f, "v": v, "c": float(c) if c is not None else None, "cl": s, "p": p}
            for f, v, c, s, p in conn.execute(
                "select field, value, confidence, source_clause_id, source_page"
                " from field_extractions where contract_id = %s"
                " and value is not null and value <> '' order by id",
                (cid,),
            )
        ]
        out[cid] = {"title": title, "clauses": clauses, "fields": fields}
    return out


def main() -> int:
    with psycopg.connect(_dsn()) as conn:
        data = export(conn)
    if not data:
        print(
            "No sample contracts found: read the sample folder on the Admin page first.",
            file=sys.stderr,
        )
        return 1
    json.dump(data, sys.stdout, separators=(",", ":"), ensure_ascii=False)
    sys.stdout.write("\n")
    print(f"Exported {len(data)} contracts.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
