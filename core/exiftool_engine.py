"""
ExifTool Engine: Persistent-process wrapper using ExifTool's -stay_open mode.

Keeps a single ExifTool process alive for the duration of a run, communicating
via stdin/stdout with the {ready} sentinel.  Falls back to one-shot subprocess
mode if the persistent process cannot be started.
"""

import subprocess
import logging
import sys
import os
import re
import time
import queue
import threading
import atexit
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from core.utils import get_app_base_path

class ExifToolEngine:
    """Thread-safe ExifTool wrapper using -stay_open for batch performance.

    A single ExifTool process is launched on the first call to write_metadata().
    All subsequent calls reuse the same process, sending commands via stdin and
    reading responses until the ``{ready}`` sentinel.  A threading.Lock serialises
    access so the engine is safe to use from a ThreadPoolExecutor.
    """

    _SENTINEL = "{ready}"

    def __init__(self, exiftool_path: str):
        # Resolve path relative to app base directory
        app_base = get_app_base_path()
        self.exiftool_path = app_base / exiftool_path

        # Handle Windows executable or Unix extension-less alternatives
        if not self.exiftool_path.exists():
            alt_paths = []
            if os.name == 'nt':
                alt_paths = [
                    app_base / "tools" / "exiftool.exe",
                    Path("tools") / "exiftool.exe",
                    Path(exiftool_path)
                ]
            else:
                clean_path = exiftool_path[:-4] if exiftool_path.endswith('.exe') else exiftool_path
                alt_paths = [
                    app_base / clean_path,
                    Path(clean_path),
                    app_base / "tools" / "exiftool",
                    Path("tools") / "exiftool"
                ]
            for alt_path in alt_paths:
                if alt_path.exists():
                    self.exiftool_path = alt_path
                    break

        logger.info(f"Searching for ExifTool at: {self.exiftool_path}")

        if not self.exiftool_path.exists():
            error_msg = f"ExifTool not found at {self.exiftool_path}. Base path: {app_base}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        logger.info(f"Successfully found ExifTool at: {self.exiftool_path}")

        # Persistent process state
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Persistent process management
    # ------------------------------------------------------------------

    def _ensure_process(self):
        """Start the persistent ExifTool process if it is not already running."""
        if self._process is not None and self._process.poll() is None:
            return  # Already running

        creation_flags = 0
        cmd = []
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NO_WINDOW
            cmd.append(str(self.exiftool_path))
        else:
            # On Mac/Linux, ExifTool is a Perl script, so invoke perl explicitly.
            # perl is available by default on macOS and most Linux distros.
            cmd.extend(["perl", str(self.exiftool_path)])

        cmd.extend([
            "-stay_open", "True",
            "-@", "-",            # Read args from stdin
            "-common_args",       # Subsequent args are shared across commands
        ])

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creation_flags,
        )
        logger.info("ExifTool persistent process started (PID %s)", self._process.pid)

    def _execute(self, args: list[str], timeout: float = 600, cancel_event=None) -> str:
        """Send *args* to the persistent process and return the output.

        Each call writes the arguments (one per line) followed by
        ``-execute\n`` and then reads stdout until the ``{ready}``
        sentinel line appears.
        """
        self._ensure_process()

        # Write args to stdin, one per line, terminated by -execute
        payload = "\n".join(args) + "\n-execute\n"
        try:
            self._process.stdin.write(payload)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            logger.warning("ExifTool stdin write failed (%s); restarting process", exc)
            self._kill_process()
            self._ensure_process()
            self._process.stdin.write(payload)
            self._process.stdin.flush()

        # Read stdout lines until the sentinel.
        # A daemon reader thread performs the blocking readline() so that
        # timeout and cancel checks in the main thread are not blocked.

        line_queue = queue.Queue()
        stdout_ref = self._process.stdout

        def _reader():
            try:
                while True:
                    line = stdout_ref.readline()
                    line_queue.put(line)
                    if not line:
                        break
                    if line.rstrip("\r\n").strip() == self._SENTINEL:
                        break
            except Exception:
                line_queue.put("")

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        output_lines: list[str] = []
        deadline = time.monotonic() + timeout
        while True:
            if cancel_event and cancel_event.is_set():
                self._kill_process()
                raise InterruptedError("Cancelled by user")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._kill_process()
                raise TimeoutError(f"ExifTool did not respond within {timeout}s")
            try:
                line = line_queue.get(timeout=min(1.0, remaining))
            except queue.Empty:
                continue
            if not line:
                # Process died
                raise RuntimeError("ExifTool process terminated unexpectedly")
            line = line.rstrip("\r\n")
            if line.strip() == self._SENTINEL:
                break
            output_lines.append(line)

        return "\n".join(output_lines)

    def _kill_process(self):
        """Terminate the persistent process if it is running."""
        if self._process is not None:
            try:
                if self._process.poll() is None:
                    # Graceful shutdown attempt
                    try:
                        self._process.stdin.write("-stay_open\nFalse\n")
                        self._process.stdin.flush()
                        self._process.wait(timeout=2)
                    except Exception:
                        pass
                    
                    # Force kill if still running
                    if self._process.poll() is None:
                        try:
                            self._process.kill()
                            self._process.wait(timeout=1)
                        except Exception:
                            pass
            except Exception:
                pass
            finally:
                # Force close all pipes to guarantee EOF at the OS level
                for pipe in (self._process.stdin, self._process.stdout, self._process.stderr):
                    try:
                        if pipe is not None:
                            pipe.close()
                    except Exception:
                        pass
                self._process = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_metadata(self, file_path: str, tags: dict, keep_backup: bool = False, cancel_event=None) -> bool:
        """
        Writes a dictionary of tags to a file using the persistent ExifTool process.
        Returns True if successful, False otherwise.

        Thread-safe: concurrent callers are serialised by an internal lock.
        """
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Cancelled by user before ExifTool call")
            
        args: list[str] = []

        # Keep ExifTool's *_original backup files only when explicitly requested.
        if not keep_backup:
            args.append("-overwrite_original")

        # Add tag arguments
        for tag, value in tags.items():
            if value is not None:
                args.append(f"-{tag}={value}")

        # Add file path
        args.append(file_path)

        logger.debug("Writing metadata to: %s", file_path)

        with self._lock:
            try:
                output = self._execute(args, cancel_event=cancel_event)
            except (TimeoutError, RuntimeError, OSError) as exc:
                logger.error("ExifTool persistent-mode failure for %s: %s — falling back to one-shot", file_path, exc)
                self._kill_process()  # Force restart on next execution to prevent corrupted state
                return self._write_metadata_oneshot(file_path, tags, keep_backup)

        return self._parse_output(output, file_path)

    def _write_metadata_oneshot(self, file_path: str, tags: dict, keep_backup: bool) -> bool:
        """Fallback: run a one-shot ExifTool subprocess for a single file."""
        args = []
        if os.name != 'nt':
            args.append("perl")
        args.append(str(self.exiftool_path))
        
        if not keep_backup:
            args.append("-overwrite_original")
        for tag, value in tags.items():
            if value is not None:
                args.append(f"-{tag}={value}")
        args.append(file_path)

        try:
            creation_flags = 0
            if os.name == 'nt':
                creation_flags = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                args, capture_output=True, text=True,
                timeout=600, creationflags=creation_flags,
            )
            output = result.stdout + result.stderr
            return self._parse_output(output, file_path)
        except Exception as e:
            logger.error("ExifTool one-shot fallback failed for %s: %s", file_path, e)
            return False

    @staticmethod
    def _parse_output(output: str, file_path: str) -> bool:
        """Interpret ExifTool's textual output and return success/failure."""
        output_lower = output.lower()

        # Look for "1 image files updated" or similar
        updated_match = re.search(r'(\d+)\s+image files? updated', output_lower)
        if updated_match:
            count = int(updated_match.group(1))
            if count > 0:
                logger.debug("Successfully updated %d file(s) for %s", count, file_path)
                return True

        # "unchanged" is also valid (file already had correct metadata)
        if "unchanged" in output_lower and "error" not in output_lower and "weren't updated" not in output_lower:
            logger.debug("File unchanged (already had correct metadata): %s", file_path)
            return True

        # Check for error patterns
        if "error" in output_lower or "weren't updated" in output_lower or "failed" in output_lower:
            logger.debug("ExifTool write failed for %s: %s", file_path, output)
            return False

        # Unexpected output
        logger.warning("ExifTool unexpected output for %s: %s", file_path, output)
        return False

    def stop(self):
        """Shut down the persistent ExifTool process gracefully."""
        with self._lock:
            self._kill_process()
        logger.info("ExifTool engine stopped")

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class ExifToolPool:
    """Pool of N persistent ExifTool instances for high-performance mode."""

    def __init__(self, exiftool_path: str, pool_size: int):
        self._pool: queue.Queue = queue.Queue()
        self._engines: list = []
        self._pool_size = pool_size
        
        # Register global cleanup to guarantee zombie process termination on crash
        atexit.register(self.stop)
        
        # Pre-extract ExifTool PAR::Packer files synchronously to prevent multi-process
        # extraction collision (which causes missing perl5*.dll errors)
        try:
            # We use a throwaway engine just to resolve the correct absolute path
            temp_engine = ExifToolEngine(exiftool_path)
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.run([str(temp_engine.exiftool_path), "-ver"], 
                           capture_output=True, check=True, timeout=30, creationflags=creation_flags)
        except Exception as exc:
            logger.warning("Failed to perform initial ExifTool extraction check: %s", exc)

        for _ in range(pool_size):
            engine = ExifToolEngine(exiftool_path)
            self._engines.append(engine)
            self._pool.put(engine)
        logger.info("ExifToolPool created with %d engines", pool_size)

        # Pre-warm: start all persistent processes now to avoid cold-start
        # latency when the first batch of files arrives.
        for engine in self._engines:
            try:
                engine._ensure_process()
            except Exception as exc:
                logger.warning("Failed to pre-warm ExifTool engine: %s", exc)

    def write_metadata(self, file_path: str, tags: dict, keep_backup: bool = False, cancel_event=None) -> bool:
        """Acquire an engine from the pool, write metadata, then return it.

        Blocks up to 120 s waiting for an available engine.
        """
        engine: ExifToolEngine = self._pool.get(timeout=120)
        try:
            return engine.write_metadata(file_path, tags, keep_backup=keep_backup, cancel_event=cancel_event)
        finally:
            self._pool.put(engine)

    def stop(self):
        """Shut down all persistent ExifTool processes gracefully."""
        # Unregister from atexit if stopped manually to avoid double-free
        try:
            atexit.unregister(self.stop)
        except Exception:
            pass

        for engine in self._engines:
            try:
                engine.stop()
            except Exception as exc:
                logger.warning("Error stopping ExifTool pool engine: %s", exc)
        logger.info("ExifToolPool stopped")
        
    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
