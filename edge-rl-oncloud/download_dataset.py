"""
Download the AI4I 2020 Predictive Maintenance dataset from UCI.
Run once before starting Docker: python3 download_dataset.py
"""
import io
import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = (
    "https://archive.ics.uci.edu/static/public/601/"
    "ai4i+2020+predictive+maintenance+dataset.zip"
)
OUT = Path("data/ai4i2020.csv")

def main():
    if OUT.exists():
        print(f"Already exists: {OUT}  ({OUT.stat().st_size:,} bytes)")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading AI4I 2020 dataset from UCI ML Repository...")
    print(f"  {URL}")

    # macOS ships without root CA bundle for Python — skip SSL verification
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(URL, timeout=60, context=ctx) as resp:
            total = resp.headers.get("Content-Length")
            total = f"{int(total):,} bytes" if total else "unknown size"
            print(f"  File size: {total}")
            raw = resp.read()
    except Exception as e:
        print(f"ERROR: Download failed — {e}")
        sys.exit(1)

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        print(f"  Zip contents: {zf.namelist()}")
        candidates = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not candidates:
            print("ERROR: No CSV found in zip")
            sys.exit(1)
        target = next((n for n in candidates if "ai4i" in n.lower()), candidates[0])
        print(f"  Extracting: {target}")
        OUT.write_bytes(zf.read(target))

    print(f"\nSaved to: {OUT}  ({OUT.stat().st_size:,} bytes)")

    # Quick preview
    try:
        import pandas as pd
        df = pd.read_csv(OUT)
        print(f"\nDataset preview:")
        print(f"  Rows:     {len(df):,}")
        print(f"  Columns:  {list(df.columns)}")
        if "Machine failure" in df.columns:
            failures = df["Machine failure"].sum()
            print(f"  Failures: {failures} ({failures/len(df)*100:.2f}%)")
        print(f"\n{df.head(3).to_string()}")
    except ImportError:
        pass

if __name__ == "__main__":
    main()
