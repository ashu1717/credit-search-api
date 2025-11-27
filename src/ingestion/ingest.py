from pathlib import Path
import re
from typing import List

import pandas as pd
import numpy as np


def normalize_column(name: str) -> str:
    """Normalize a single column name to snake_case, lowercased, trimmed.

    - Strips leading/trailing whitespace
    - Replaces non-alphanumeric characters with underscores
    - Collapses multiple underscores
    - Lowercases and trims underscores from ends
    """
    if name is None:
        return ""
    s = str(name).strip()
    s = re.sub(r"[^\w]+", "_", s)
    s = re.sub(r"_{2,}", "_", s)
    s = s.strip("_").lower()
    return s


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Apply normalization to all column names and ensure uniqueness."""
    new_cols: List[str] = []
    seen: dict[str, int] = {}
    for col in df.columns:
        base = normalize_column(col) or "unnamed"
        if base in seen:
            seen[base] += 1
            new_cols.append(f"{base}_{seen[base]}")
        else:
            seen[base] = 0
            new_cols.append(base)
    df.columns = new_cols
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Perform generic cleaning suitable for analytics pipelines.

    - Trim whitespace on string/object columns
    - Convert empty strings and string 'nan' to actual NaN
    - Drop rows that are entirely NaN
    - Drop exact duplicate rows
    """
    obj_cols = df.select_dtypes(include=["object"]).columns
    for col in obj_cols:
        # Ensure string type, trim, and normalize empties to NaN
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"": np.nan, "nan": np.nan})

    df = df.dropna(how="all")
    df = df.drop_duplicates()
    return df


def read_tsv_files(input_dir: Path) -> List[pd.DataFrame]:
    """Read all .tsv files in the given directory as string-typed DataFrames."""
    dfs: List[pd.DataFrame] = []
    for f in sorted(input_dir.glob("*.tsv")):
        try:
            df = pd.read_csv(f, sep="\t", dtype=str, keep_default_na=False)
            df = normalize_columns(df)
            df = clean_dataframe(df)
            dfs.append(df)
        except Exception as e:
            print(f"Warning: failed to read {f}: {e}")
    return dfs


def combine_dataframes(dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """Combine multiple DataFrames into one, preserving all columns."""
    if not dfs:
        return pd.DataFrame()
    combined = pd.concat(dfs, ignore_index=True, sort=False)
    combined = clean_dataframe(combined)
    return combined


def save_parquet(df: pd.DataFrame, output_path: Path) -> None:
    """Save a DataFrame to Parquet, trying pyarrow then fastparquet."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(output_path, engine="pyarrow", index=False)
    except Exception as e:
        try:
            df.to_parquet(output_path, engine="fastparquet", index=False)
        except Exception as e2:
            raise RuntimeError(
                f"Failed to save parquet. pyarrow error: {e}; fastparquet error: {e2}"
            )


def main() -> None:
    """CLI entry point: reads TSVs, normalizes, cleans, combines, and saves Parquet."""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Ingestion: read all .tsv in data/raw, normalize columns, clean data, "
            "combine into a unified DataFrame, and save as Parquet."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default=str(Path("data/raw")),
        help="Directory containing .tsv files",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(Path("data/processed/ingested.parquet")),
        help="Output Parquet file path",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    dfs = read_tsv_files(input_dir)
    if not dfs:
        print(f"No .tsv files found in {input_dir}. Saving empty Parquet.")
        save_parquet(pd.DataFrame(), Path(args.output))
        print(f"Saved empty parquet to {args.output}.")
        return

    combined = combine_dataframes(dfs)
    save_parquet(combined, Path(args.output))
    print(
        f"Saved {len(combined)} rows to {args.output} with {len(combined.columns)} columns."
    )


if __name__ == "__main__":
    main()