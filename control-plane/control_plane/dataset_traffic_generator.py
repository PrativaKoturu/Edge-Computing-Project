"""
Dataset-driven traffic generator.

Uses the AI4I 2020 Predictive Maintenance dataset (UCI ML Repository) instead of
random synthetic data. Each row becomes a real EdgeRequest with anomaly flags
derived from the Machine_failure column.

Dataset: https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset
10,000 rows | columns: UDI, Product ID, Type, Air/Process temp, RPM, Torque,
             Tool wear, Machine failure, TWF, HDF, PWF, OSF, RNF

Mapping:
  stream_id  = cnc-{(UDI-1) % 50:02d}/{sensor_type}   → 50 machines × 3 sensors
  sensor_type cycles:  vibration → temperature → pressure (per row index)
  payload_kb = scaled from the sensor reading for that type:
                vibration   → Rotational speed [rpm]   → 500–2000 KB
                temperature → Process temperature [K]  → 200–800  KB
                pressure    → Torque [Nm]              → 300–1500 KB
  anomaly    = Machine failure == 1
"""

from __future__ import annotations

import io
import logging
import os
import ssl
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from .config import load_settings
from .messages import EdgeRequest
from .mqtt_client import MqttBus, MqttConfig
from .topics import request_topic

# ── dataset download ──────────────────────────────────────────────────────────

_UCI_URL = (
    "https://archive.ics.uci.edu/static/public/601/"
    "ai4i+2020+predictive+maintenance+dataset.zip"
)
_CSV_FILENAME = "ai4i2020.csv"
_DEFAULT_DATA_DIR = Path("/app/data")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _setup_logger(level: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("traffic")


def _resolve_csv(log: logging.Logger) -> Path:
    """
    Return path to the AI4I CSV.
    Priority:
      1. DATA_FILE env var
      2. <DATA_DIR>/ai4i2020.csv  (DATA_DIR env var, default /app/data)
      3. Download from UCI into DATA_DIR
    """
    explicit = os.getenv("DATA_FILE")
    if explicit and Path(explicit).exists():
        log.info("Using dataset from DATA_FILE=%s", explicit)
        return Path(explicit)

    data_dir = Path(os.getenv("DATA_DIR", str(_DEFAULT_DATA_DIR)))
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / _CSV_FILENAME

    if csv_path.exists():
        log.info("Found cached dataset at %s", csv_path)
        return csv_path

    log.info("Dataset not found locally. Downloading from UCI ML Repository...")
    log.info("URL: %s", _UCI_URL)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(_UCI_URL, timeout=60, context=ctx) as resp:
            raw = resp.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            candidates = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not candidates:
                raise RuntimeError(f"No CSV found in zip. Contents: {zf.namelist()}")
            # Prefer the main dataset file; fall back to first CSV found
            target = next(
                (n for n in candidates if "ai4i" in n.lower()), candidates[0]
            )
            log.info("Extracting %s → %s", target, csv_path)
            csv_path.write_bytes(zf.read(target))
        log.info("Download complete. %d bytes saved.", csv_path.stat().st_size)
        return csv_path
    except Exception as exc:
        log.error("Dataset download failed: %s", exc)
        raise RuntimeError(
            "Could not obtain the AI4I 2020 dataset. "
            "Download it manually from https://archive.ics.uci.edu/dataset/601 "
            f"and place ai4i2020.csv in {data_dir}"
        ) from exc


# ── row → EdgeRequest mapping ─────────────────────────────────────────────────

_SENSOR_TYPES = ["vibration", "temperature", "pressure"]


def _payload_vibration(rpm: float) -> int:
    """Rotational speed 1168–2886 rpm → 500–2000 KB"""
    rpm_min, rpm_max = 1168.0, 2886.0
    frac = max(0.0, min((rpm - rpm_min) / (rpm_max - rpm_min), 1.0))
    return int(500 + frac * 1500)


def _payload_temperature(temp_k: float) -> int:
    """Process temperature 305–314 K → 200–800 KB"""
    t_min, t_max = 305.0, 314.0
    frac = max(0.0, min((temp_k - t_min) / (t_max - t_min), 1.0))
    return int(200 + frac * 600)


def _payload_pressure(torque_nm: float) -> int:
    """Torque 3.8–76.6 Nm → 300–1500 KB"""
    t_min, t_max = 3.8, 76.6
    frac = max(0.0, min((torque_nm - t_min) / (t_max - t_min), 1.0))
    return int(300 + frac * 1200)


def _row_to_request(row: pd.Series, row_idx: int, node_id: str) -> EdgeRequest:
    """
    Map one AI4I row to a single EdgeRequest.

    stream_id   = cnc-{machine_num:02d}/{sensor_type}
    sensor_type = cycles vibration → temperature → pressure (by row_idx % 3)
    payload_kb  = scaled from the sensor reading matching sensor_type
    anomaly     = Machine failure == 1  (also triggered by any failure sub-type)
    """
    udi = int(row["UDI"])
    machine_num = (udi - 1) % 50          # maps 10,000 rows → 50 distinct machines
    sensor_type = _SENSOR_TYPES[row_idx % 3]
    stream_id = f"cnc-{machine_num:02d}/{sensor_type}"

    rpm = float(row.get("Rotational speed [rpm]", 1500))
    temp_k = float(row.get("Process temperature [K]", 308.0))
    torque = float(row.get("Torque [Nm]", 40.0))

    if sensor_type == "vibration":
        payload_kb = _payload_vibration(rpm)
    elif sensor_type == "temperature":
        payload_kb = _payload_temperature(temp_k)
    else:
        payload_kb = _payload_pressure(torque)

    # anomaly = any failure in this row (Machine failure OR individual failure bits)
    failure_cols = ["Machine failure", "TWF", "HDF", "PWF", "OSF", "RNF"]
    anomaly = any(int(row.get(c, 0)) == 1 for c in failure_cols if c in row.index)

    return EdgeRequest(
        node_id=node_id,
        ts_ms=_now_ms(),
        stream_id=stream_id,
        payload_kb=payload_kb,
        anomaly=anomaly,
    )


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    settings = load_settings()
    log = _setup_logger(settings.log_level)

    period_s = float(os.getenv("BURST_PERIOD_S", "30"))
    burst_size = int(os.getenv("BURST_SIZE", "20"))

    csv_path = _resolve_csv(log)
    df = pd.read_csv(csv_path)
    log.info(
        "Loaded dataset: %d rows, %d columns — %s",
        len(df),
        len(df.columns),
        list(df.columns),
    )

    # Count anomalies so we can log the anomaly rate
    failure_col = "Machine failure"
    if failure_col in df.columns:
        anomaly_rate = df[failure_col].mean() * 100
        log.info("Anomaly rate in dataset: %.2f%%", anomaly_rate)

    bus = MqttBus(
        MqttConfig(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            client_id=f"traffic-dataset-{os.getpid()}",
        ),
        logger=log,
    )
    bus.connect()

    node_id = settings.edge_node_ids[0]
    total_rows = len(df)
    row_cursor = 0
    burst_num = 0

    log.info(
        "Dataset traffic started. node=%s period=%.1fs burst_size=%d rows=%d",
        node_id,
        period_s,
        burst_size,
        total_rows,
    )

    while True:
        burst_ts = _now_ms()
        burst_anomalies = 0
        rows_sent = 0

        for _ in range(burst_size):
            row = df.iloc[row_cursor]
            req = _row_to_request(row, row_cursor, node_id)

            bus.publish(request_topic(node_id), req.to_json(), qos=0)

            if req.anomaly:
                burst_anomalies += 1
            rows_sent += 1

            row_cursor = (row_cursor + 1) % total_rows   # loop dataset

        burst_num += 1
        progress_pct = (row_cursor / total_rows) * 100
        log.info(
            "Burst #%d sent %d requests (anomalies=%d) | dataset %.1f%% complete",
            burst_num,
            rows_sent,
            burst_anomalies,
            progress_pct,
        )

        time.sleep(period_s)


if __name__ == "__main__":
    main()
