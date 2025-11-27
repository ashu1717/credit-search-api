import sys
import os
import datetime

try:
    import pyarrow.parquet as pq
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyarrow'])
    import pyarrow.parquet as pq


def generate_markdown(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    pf = pq.ParquetFile(file_path)
    arrow_schema = pq.read_schema(file_path)

    num_rows = pf.metadata.num_rows
    num_row_groups = pf.metadata.num_row_groups

    lines = []
    lines.append('# Processed Dataset Schema')
    lines.append('')
    lines.append(f'- Source file: `{file_path}`')
    lines.append(f'- Rows: `{num_rows}`')
    lines.append(f'- Row groups: `{num_row_groups}`')
    # Use UTC-aware timestamp
    lines.append(f'- Generated: `{datetime.datetime.now(datetime.timezone.utc).isoformat()}`')
    lines.append('')
    lines.append('## Columns')
    lines.append('')
    lines.append('| Column | Type | Nullable |')
    lines.append('|--------|------|----------|')

    for field in arrow_schema:
        name = field.name
        type_str = str(field.type)
        nullable = 'true' if field.nullable else 'false'
        lines.append(f"| `{name}` | `{type_str}` | `{nullable}` |")

    return "\n".join(lines)


def main():
    file_path = 'data/processed/ingested.parquet'
    try:
        md = generate_markdown(file_path)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(md)


if __name__ == '__main__':
    main()