import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """
    Dataclass for storing the result of a process.

    Features timing information as well.
    """

    wall_time: float
    user_time: float
    system_time: float

    memory_max_rss: int  # Maximum resident set size used (in bytes), "max memory used"

    returncode: int

    stdout: str
    stderr: str


def _max_rss_bytes(rusage: resource.struct_rusage) -> int:
    # Linux reports ru_maxrss in KiB; macOS reports bytes.
    if sys.platform.startswith("linux"):
        return rusage.ru_maxrss * 1024
    return rusage.ru_maxrss


def run_process(
    command: str,
    args: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> ProcessResult:
    """
    Run a process and collect its timing and memory usage.

    Standard output and error are discarded by default. When ``capture_output``
    is true, they are captured in temporary files and returned in the result.
    Temporary files avoid pipe-buffer deadlocks while waiting with ``wait4``.
    """
    args = args or []
    assert isinstance(args, list)

    fq_exe = shutil.which(command)
    argv = [fq_exe, *args]

    with ExitStack() as stack:
        if capture_output:
            stdout_file = stack.enter_context(tempfile.TemporaryFile())
            stderr_file = stack.enter_context(tempfile.TemporaryFile())
            stdout_target = stdout_file
            stderr_target = stderr_file
        else:
            stdout_file = None
            stderr_file = None
            stdout_target = subprocess.DEVNULL
            stderr_target = subprocess.DEVNULL

        wall_time_start = time.perf_counter()
        proc = subprocess.Popen(
            argv,
            env=env,
            stdout=stdout_target,
            stderr=stderr_target,
        )

        # Do not call proc.wait(): wait4 both waits and returns this child's
        # individual resource usage.
        _, wait_status, rusage = os.wait4(proc.pid, 0)
        proc.returncode = os.waitstatus_to_exitcode(wait_status)

        if capture_output:
            assert stdout_file is not None
            assert stderr_file is not None
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read().decode(errors="replace")
            stderr = stderr_file.read().decode(errors="replace")
        else:
            stdout = ""
            stderr = ""

    return ProcessResult(
        wall_time=time.perf_counter() - wall_time_start,
        user_time=rusage.ru_utime,
        system_time=rusage.ru_stime,
        memory_max_rss=_max_rss_bytes(rusage),
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )
