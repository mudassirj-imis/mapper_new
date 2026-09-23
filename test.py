#!/usr/bin/env python3
"""
migrate_api_endpoints.py

One-time data migration: copies all rows from api_endpoints in the Imis DB
(MySQL) into api_endpoints in Supabase (Postgres).

Column handling:
  - id              : NOT copied. Supabase's gen_random_uuid() default
                       generates a fresh UUID for every inserted row.
  - is_active        : Imis DB ENUM('Y','N')  ->  Supabase BOOLEAN
                       'Y' -> True, 'N' -> False, NULL/anything else -> NULL
  - created_on (src) : mapped to Supabase's created_at
  - updated_at       : not present in source, left NULL (column default / trigger, if any, applies)
  - Supabase-only extra columns (tenant_id, created_by, updated_by,
    is_hidden, mock_enabled, mock_response, description, protocol,
    rate_limit_rpm, request_content_type, require_authentication,
    require_correlation_id, api_auth_url, dynamic_filename_pattern,
    sftp_*  ) : not present in source, left at their column defaults / NULL.

Requires:
    pip install sqlalchemy psycopg2-binary pymysql --break-system-packages
"""

import sys
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Hardcoded config — edit before running
# ---------------------------------------------------------------------------
SRC_URL = "mysql+pymysql://imisuser:uatDevDbimis@103.213.111.121:8556/imis"          # Imis DB (source)
DST_URL = "postgresql+psycopg2://postgres.tismsqqmppktxnfurhfz:iNTeGrATiO123!@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"  # Supabase (destination)

TABLE_SRC = "api_endpoint"
TABLE_DST = "api_endpoints"

# Batch size for inserts (keeps memory bounded on large tables)
BATCH_SIZE = 500
# ---------------------------------------------------------------------------

# Columns that exist in BOTH source and destination, and should be copied
# as-is (no type/value transformation needed beyond driver-level casting).
DIRECT_COLUMNS = [
    "api_id",
    "api_password",
    "endpoint_code",
    "method",
    "source_api_url",
    "target_api_url",
]

# Columns that need a value transform. Each entry: dest_column -> function(src_row) -> value
def is_active_transform(row):
    val = row.get("is_active")
    if val is None:
        return None
    val = str(val).strip().upper()
    if val == "Y":
        return True
    if val == "N":
        return False
    return None

TRANSFORMED_COLUMNS = {
    "is_active": is_active_transform,
    "created_at": lambda row: row.get("created_on"),
}

ALL_DEST_COLUMNS = DIRECT_COLUMNS + list(TRANSFORMED_COLUMNS.keys())


def fetch_source_rows(src_engine):
    src_select_cols = DIRECT_COLUMNS + ["is_active", "created_on"]
    query = text(f"SELECT {', '.join(src_select_cols)} FROM {TABLE_SRC}")
    with src_engine.connect() as conn:
        result = conn.execute(query)
        rows = [dict(row._mapping) for row in result]
    return rows


def build_insert_rows(src_rows):
    dest_rows = []
    for row in src_rows:
        dest_row = {col: row.get(col) for col in DIRECT_COLUMNS}
        for dest_col, fn in TRANSFORMED_COLUMNS.items():
            dest_row[dest_col] = fn(row)
        dest_rows.append(dest_row)
    return dest_rows


def insert_rows(dst_engine, dest_rows):
    if not dest_rows:
        print("No rows to insert.")
        return 0

    col_list = ", ".join(ALL_DEST_COLUMNS)
    placeholders = ", ".join(f":{c}" for c in ALL_DEST_COLUMNS)
    insert_stmt = text(f"INSERT INTO {TABLE_DST} ({col_list}) VALUES ({placeholders})")

    inserted = 0
    with dst_engine.begin() as conn:
        for i in range(0, len(dest_rows), BATCH_SIZE):
            batch = dest_rows[i : i + BATCH_SIZE]
            conn.execute(insert_stmt, batch)
            inserted += len(batch)
            print(f"  Inserted {inserted}/{len(dest_rows)} rows...")

    return inserted


def main():
    try:
        src_engine = create_engine(SRC_URL)
        dst_engine = create_engine(DST_URL)
    except Exception as e:
        print(f"ERROR creating engines: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading rows from {TABLE_SRC} (Imis DB)...")
    try:
        src_rows = fetch_source_rows(src_engine)
    except Exception as e:
        print(f"ERROR reading source table: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetched {len(src_rows)} rows from source.")

    dest_rows = build_insert_rows(src_rows)

    print(f"Inserting into {TABLE_DST} (Supabase)...")
    try:
        inserted = insert_rows(dst_engine, dest_rows)
    except Exception as e:
        print(f"ERROR inserting into destination: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\nDone. Inserted {inserted} rows into {TABLE_DST} on Supabase.")


if __name__ == "__main__":
    main()