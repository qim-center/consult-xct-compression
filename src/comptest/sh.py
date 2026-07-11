import resource
import shutil
import subprocess
import time
from dataclasses import dataclass
from multiprocessing import Manager, Process
from multiprocessing.managers import ValueProxy
from typing import Any


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


def _run_process(
    command: str,
    args: list[str],
    kwargs: dict[str, Any],
    result: ValueProxy[ProcessResult],
) -> None:

    wall_time_start = time.perf_counter()
    # Need to use lower-level `Popen` instead of `run` to get PID
    proc = subprocess.Popen([command, *args], **kwargs)
    proc.wait()
    wall_time = time.perf_counter() - wall_time_start

    rusage = resource.getrusage(resource.RUSAGE_CHILDREN)

    result.value = ProcessResult(
        time=ProcessTiming(
            wall=wall_time, user=rusage.ru_utime, system=rusage.ru_stime
        ),
        memory=ProcessMemoryUsage(max_rss=rusage.ru_maxrss),
        returncode=proc.returncode,
    )


# See: https://valarmorghulis.io/tech/202505-measuring-cpu-memory-python-subprocess/
def run_process(
    command: str,
    args: list[str] | None = None,
    *,
    shell: bool = False,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    args = args or []
    assert isinstance(args, list)

    fq_exe = shutil.which(command)
    kwargs = {
        "env": env,
        "shell": shell,
    }

    with Manager() as manager:
        result = manager.Value(ProcessResult, None)
        proc = Process(target=_run_process, args=(fq_exe, args, kwargs, result))
        proc.start()
        proc.join()

        assert result.value is not None, (
            "ProcessResult should not be None after process completion"
        )
        return result.value
