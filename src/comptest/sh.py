import os
import resource
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessTiming:
    """
    Dataclass for storing timing information of a process.
    """

    wall: float
    user: float
    system: float


@dataclass(frozen=True, slots=True)
class ProcessMemoryUsage:
    """
    Dataclass for storing memory usage information of a process.
    """

    max_rss: int  # Maximum resident set size used (in bytes), "max memory used"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """
    Dataclass for storing the result of a process.

    Features timing information as well.
    """

    time: ProcessTiming
    memory: ProcessMemoryUsage
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
) -> ProcessResult:
    args = args or []
    assert isinstance(args, list)

    fq_exe = shutil.which(command)
    kwargs = {
        "env": env,
    }

    argv = [fq_exe, *args]

    wall_time_start = time.perf_counter()
    proc = subprocess.Popen(argv, **kwargs)

    # Do not call proc.wait(): wait4 both waits and returns this child's
    # individual resource usage.
    _, wait_status, rusage = os.wait4(proc.pid, 0)
    proc.returncode = os.waitstatus_to_exitcode(wait_status)

    stdout_b, stderr_b = proc.communicate()
    stdout = stdout_b.decode() if stdout_b is not None else ""
    stderr = stderr_b.decode() if stderr_b is not None else ""

    return ProcessResult(
        time=ProcessTiming(
            wall=time.perf_counter() - wall_time_start,
            user=rusage.ru_utime,
            system=rusage.ru_stime,
        ),
        memory=ProcessMemoryUsage(
            max_rss=_max_rss_bytes(rusage),
        ),
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )
