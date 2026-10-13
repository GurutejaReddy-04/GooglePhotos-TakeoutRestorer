"""
Deterministic Benchmarking Harness for Takeout Restorer for Google Photos.
"""

import sys
import os
import time
import json
import argparse
import platform
from pathlib import Path
import tempfile
import shutil

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.state_db import StateDatabase, FileStatus
from core.scanner import FileScanner
from core.matcher import MetadataMatcher
from core.processor import FileProcessor
from tests.conftest import SAMPLE_JPEG_BYTES, SAMPLE_MOV_BYTES, SAMPLE_MP4_BYTES, SAMPLE_PNG_BYTES

def generate_synthetic_dataset(target_dir: Path, total_files: int = 1000) -> dict:
    """Generates synthetic media and matching JSON sidecars."""
    target_dir.mkdir(parents=True, exist_ok=True)
    
    jpeg_count = int(total_files * 0.8)
    png_count = int(total_files * 0.1)
    mp4_count = int(total_files * 0.05)
    mov_count = total_files - (jpeg_count + png_count + mp4_count)
    
    print(f"Generating {total_files} synthetic files in {target_dir}...")
    print(f"Distribution: {jpeg_count} JPEGs, {png_count} PNGs, {mp4_count} MP4s, {mov_count} MOVs")
    
    idx = 0
    # JPEGs
    for i in range(jpeg_count):
        fname = f"IMG_{idx:05d}.jpg"
        (target_dir / fname).write_bytes(SAMPLE_JPEG_BYTES)
        sidecar = {
            "title": fname,
            "description": f"Benchmark photo {idx}",
            "photoTakenTime": {"timestamp": str(1600000000 + idx * 60)},
            "geoDataExif": {"latitude": 41.8902, "longitude": 12.4922, "altitude": 20.0}
        }
        (target_dir / f"{fname}.json").write_text(json.dumps(sidecar), encoding="utf-8")
        idx += 1
        
    # PNGs
    for i in range(png_count):
        fname = f"IMG_{idx:05d}.png"
        (target_dir / fname).write_bytes(SAMPLE_PNG_BYTES)
        sidecar = {
            "title": fname,
            "photoTakenTime": {"timestamp": str(1600000000 + idx * 60)},
            "geoDataExif": {"latitude": 37.7749, "longitude": -122.4194, "altitude": 10.0}
        }
        (target_dir / f"{fname}.json").write_text(json.dumps(sidecar), encoding="utf-8")
        idx += 1

    # MP4s
    for i in range(mp4_count):
        fname = f"VID_{idx:05d}.mp4"
        (target_dir / fname).write_bytes(SAMPLE_MP4_BYTES)
        sidecar = {
            "title": fname,
            "photoTakenTime": {"timestamp": str(1600000000 + idx * 60)},
            "geoDataExif": {"latitude": 51.5074, "longitude": -0.1278, "altitude": 5.0}
        }
        (target_dir / f"{fname}.json").write_text(json.dumps(sidecar), encoding="utf-8")
        idx += 1

    # MOVs
    for i in range(mov_count):
        fname = f"LIVE_{idx:05d}.mov"
        (target_dir / fname).write_bytes(SAMPLE_MOV_BYTES)
        sidecar = {
            "title": fname,
            "photoTakenTime": {"timestamp": str(1600000000 + idx * 60)},
            "geoDataExif": {"latitude": 48.8566, "longitude": 2.3522, "altitude": 35.0}
        }
        (target_dir / f"{fname}.json").write_text(json.dumps(sidecar), encoding="utf-8")
        idx += 1

    return {
        "total_files": total_files,
        "jpeg_count": jpeg_count,
        "png_count": png_count,
        "mp4_count": mp4_count,
        "mov_count": mov_count
    }

def run_benchmark(input_dir: Path, output_dir: Path, high_performance: bool) -> dict:
    """Runs a full pipeline benchmark pass and measures performance."""
    mode_name = "High-Performance" if high_performance else "Normal"
    print(f"\n--- Starting Benchmark: {mode_name} Mode ---")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    db_file = output_dir / "bench_state.db"
    db = StateDatabase(db_file)
    
    config = {
        "app_name": "Takeout Restorer for Google Photos",
        "supported_image_extensions": [".jpg", ".jpeg", ".png"],
        "supported_video_extensions": [".mp4", ".mov"],
        "processing": {"max_workers": 4, "chunk_size": 100},
        "matching": {"levenshtein_threshold": 3, "min_truncation_length": 8},
        "settings": {"gps_enabled": True, "timezone_enabled": True}
    }
    
    # 1. Scanning
    t0 = time.perf_counter()
    scanner = FileScanner(config, db, output_dir / "scanner_tmp")
    media_count, json_count = scanner.scan_inputs([input_dir])
    scan_time = time.perf_counter() - t0
    print(f"Scanned {media_count} media files and {json_count} sidecars in {scan_time:.3f}s")
    
    # 2. Matching
    t0 = time.perf_counter()
    matcher = MetadataMatcher(db, config)
    matcher.run_matching()
    match_time = time.perf_counter() - t0
    print(f"Matched metadata in {match_time:.3f}s")
    
    # 3. Processing
    all_files = db.get_files_by_status(FileStatus.MATCHED)
    file_ids = [f.id for f in all_files]
    
    processor = FileProcessor(
        db=db,
        config=config,
        log_dir=output_dir / "logs",
        run_id="bench_run",
        high_performance=high_performance
    )
    
    t0 = time.perf_counter()
    processor.process_files(
        file_ids=file_ids,
        output_dir=output_dir / "dest",
        output_mode="copy"
    )
    proc_time = time.perf_counter() - t0
    
    completed_files = len(db.get_files_by_status(FileStatus.COMPLETED))
    throughput = completed_files / proc_time if proc_time > 0 else 0.0
    
    print(f"Processed {completed_files} files in {proc_time:.3f}s ({throughput:.2f} files/sec)")
    print(f"Configured workers: {processor.max_workers}")
    
    db.close()
    
    return {
        "mode": mode_name,
        "workers": processor.max_workers,
        "total_files": completed_files,
        "scan_time_sec": round(scan_time, 3),
        "match_time_sec": round(match_time, 3),
        "process_time_sec": round(proc_time, 3),
        "throughput_files_per_sec": round(throughput, 2)
    }

def main():
    parser = argparse.ArgumentParser(description="Takeout Restorer for Google Photos Benchmark")
    parser.add_argument("--count", type=int, default=1000, help="Total synthetic media files to benchmark (default: 1000)")
    parser.add_argument("--quick", action="store_true", help="Quick smoke benchmark (100 files)")
    parser.add_argument("--out", type=str, default="benchmark_results.json", help="Output path for JSON report")
    args = parser.parse_args()
    
    total_files = 100 if args.quick else args.count
    bench_dir = Path(tempfile.mkdtemp(prefix="takeout_bench_"))
    
    try:
        input_dir = bench_dir / "input"
        output_dir_normal = bench_dir / "out_normal"
        output_dir_high = bench_dir / "out_high"
        
        dataset_meta = generate_synthetic_dataset(input_dir, total_files)
        
        system_info = {
            "platform": platform.platform(),
            "cpu": platform.processor(),
            "cpu_count": os.cpu_count(),
            "python_version": sys.version.split()[0]
        }
        
        normal_results = run_benchmark(input_dir, output_dir_normal, high_performance=False)
        high_results = run_benchmark(input_dir, output_dir_high, high_performance=True)
        
        report = {
            "system_info": system_info,
            "dataset": dataset_meta,
            "results": {
                "normal_mode": normal_results,
                "high_performance_mode": high_results
            }
        }
        
        out_path = Path(args.out)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nBenchmark report successfully written to {out_path.resolve()}")
        
    finally:
        shutil.rmtree(bench_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
