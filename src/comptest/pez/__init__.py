import datetime
import pickle
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from shlex import quote
from typing import Any, Self

import cloudpickle
from pydantic import (
    BaseModel,
    ConfigDict,
    PositiveInt,
    constr,
    model_validator,
)
from scientific_pydantic import SliceAdapter

import comptest.pez.payload as payload_module
from comptest.pez.common import get_node_path_from_payload_path
from comptest.pez.constants import LSB_JOBINDEX as LSB_JOBINDEX


class Resource(BaseModel):
    """
    Represents a resource requirement for an LSF job.

    See: https://www.ibm.com/docs/en/spectrum-lsf/10.1.0?topic=bsub-options
    """

    def to_resource_str(self) -> str:
        raise NotImplementedError("Subclasses must implement this method.")


class ResourceCustom(Resource):
    value: str

    model_config = ConfigDict(extra="allow")

    def __init__(self, value: str):
        super().__init__(value=value)

    def to_resource_str(self) -> str:
        return self.value


class ResourceSelect(Resource):
    _SECTION = "select"
    value: str

    def __init__(self, value: str):
        super().__init__(value=value)

    def to_resource_str(self) -> str:
        return f"{self._SECTION}[{self.value}]"


class ResourceSpan(Resource):
    _SECTION = "span"
    value: str

    def __init__(self, value: str):
        super().__init__(value=value)

    def to_resource_str(self) -> str:
        return f"{self._SECTION}[{self.value}]"


class ResourceRUsage(Resource):
    _SECTION = "rusage"
    value: str

    def __init__(self, value: str):
        super().__init__(value=value)

    def to_resource_str(self) -> str:
        return f"{self._SECTION}[{self.value}]"


# We hack this a bit by using Slice, see https://github.com/psalvaggio/scientific_pydantic/issues/34
_JobArrayRangeAdapter = SliceAdapter(
    start_type=PositiveInt,
    stop_type=PositiveInt,
    step_type=PositiveInt | None,
)
_JobArrayIndicesT = _JobArrayRangeAdapter | PositiveInt
_JobArrayIndicesInputT = _JobArrayIndicesT | str


_LSF_ARRAY_RANGE = re.compile(
    r"^(?P<start>[1-9]\d*)-(?P<stop>[1-9]\d*)(?::(?P<step>[1-9]\d*))?$"
)


class JobArrayIndices(BaseModel):
    indices: list[_JobArrayIndicesT]
    inclusive: bool = False

    def __init__(
        self,
        indices: _JobArrayIndicesT | str | Sequence[_JobArrayIndicesT | str],
        inclusive: bool | None = None,
    ) -> None:
        values: dict[str, Any] = {"indices": indices}
        if inclusive is not None:
            values["inclusive"] = inclusive
        super().__init__(**values)

    def __iter__(self):
        for indices in self.indices:
            if isinstance(indices, slice):
                stop = indices.stop + 1 if self.inclusive else indices.stop
                yield from range(indices.start, stop, indices.step or 1)
            elif isinstance(indices, int):
                yield indices
            else:
                raise ValueError(
                    f"Invalid type for indices: {type(indices)}. Must be int or slice."
                )

    @model_validator(mode="before")
    @classmethod
    def parse_shorthand(cls, value: object) -> object:
        if isinstance(value, cls):
            return value

        if isinstance(value, dict):
            values = value.copy()
            if "indices" not in values:
                return values
            indices = values["indices"]
        else:
            values = {}
            indices = value

        if not isinstance(indices, (tuple, list)):
            indices = [indices]

        parsed_indices = []
        has_lsf_range = False

        for index in indices:
            if isinstance(index, str):
                match = _LSF_ARRAY_RANGE.fullmatch(index)
                if match is not None:
                    start = int(match["start"])
                    stop = int(match["stop"])
                    step = int(match["step"]) if match["step"] else None
                    parsed_indices.append(slice(start, stop, step))
                    has_lsf_range = True
                    continue

            parsed_indices.append(index)

        values["indices"] = parsed_indices
        if has_lsf_range and "inclusive" not in values:
            values["inclusive"] = True

        return values

    @model_validator(mode="after")
    def validate_indices(self) -> Self:
        elements = list(self)

        if len(elements) != len(set(elements)):
            duplicates = [
                element for element in set(elements) if elements.count(element) > 1
            ]
            raise ValueError(
                f"Duplicate indices found in JobArrayIndices: {duplicates}"
            )

        return self

    def to_str(self) -> str:
        """
        Convert the JobArrayIndices instance to a string representation suitable for LSF.

        Returns:
            str: The string representation of the job array indices.
        """
        parts = []
        for element in self.indices:
            if isinstance(element, slice):
                start = element.start
                stop = element.stop
                step = element.step or 1

                if not self.inclusive:
                    stop = start + ((stop - start - 1) // step) * step

                parts.append(
                    f"{start}-{stop}:{step}" if step != 1 else f"{start}-{stop}"
                )

            elif isinstance(element, int):
                parts.append(str(element))
            else:
                raise ValueError(
                    f"Invalid type for indices: {type(element)}. Must be int or slice."
                )
        return ",".join(parts)


# https://www.ibm.com/docs/hu/spectrum-lsf/10.1.0?topic=administration-job-arrays#v3628022__title__2
_JobName = constr(pattern=r"^[A-Za-z0-9._-]+$", min_length=1, max_length=255)
_NonEmptyStr = constr(min_length=1)

with open(payload_module.__file__, "r") as f:
    _RUN_PICKLED_CALL_FROM_FILE = f.read()

# TODO Better validate different command arguments to the presumably stricter LSF requirements
class LSFJob(BaseModel):
    """
    Represents a job submission to an LSF cluster.

    See: https://www.ibm.com/docs/en/spectrum-lsf/10.1.0?topic=bsub-options
    """

    queue: _NonEmptyStr | None = None  # -q
    jobname: _JobName | None = None  # -J
    description: _NonEmptyStr | None = None  # -Jd
    array_indices: JobArrayIndices | None = None  # -J NAME[INDICES]

    tasks: int | None = None  # -n
    runtime_limit: datetime.timedelta | None = None  # -W

    resources: list[Resource]  # -R

    stderr_file: Path | None = None  # -e / -eo
    stderr_overwrite: bool = False  # -eo
    stdout_file: Path | None = None  # -o / -oo
    stdout_overwrite: bool = False  # -oo
    outdir: Path | None = None  # -outdir

    def _runtime_limit_str(self) -> str:
        assert self.runtime_limit is not None, "runtime_limit is None"
        hours = self.runtime_limit.total_seconds() // 3600
        minutes = (self.runtime_limit.total_seconds() % 3600) // 60

        return f"{int(hours):02d}:{int(minutes):02d}"

    def _get_command_parts(self) -> list[str]:
        cmd_parts = []

        if self.queue:
            cmd_parts.append(f"-q {quote(self.queue)}")
        if self.jobname:
            cmd_parts.append(f"-J {quote(self.get_full_jobname())}")
        if self.description:
            cmd_parts.append(f"-Jd {quote(self.description)}")
        if self.tasks:
            cmd_parts.append(f"-n {self.tasks}")
        if self.runtime_limit:
            # timedelta.__str__ gives HH:MM:SS
            cmd_parts.append(f"-W {quote(self._runtime_limit_str())}")

        for resource in self.resources:
            cmd_parts.append(f"-R {quote(resource.to_resource_str())}")

        if self.stderr_file:
            flag = "-e" if not self.stderr_overwrite else "-eo"
            cmd_parts.append(f"{flag} {quote(str(self.stderr_file))}")
        if self.stdout_file:
            flag = "-o" if not self.stdout_overwrite else "-oo"
            cmd_parts.append(f"{flag} {quote(str(self.stdout_file))}")
        if self.outdir:
            cmd_parts.append(f"-outdir {quote(str(self.outdir))}")

        return cmd_parts

    def to_bsub(self) -> str:
        """
        Convert the LSFJob instance to a bsub command string.

        Returns:
            str: The bsub command string.
        """
        return " ".join(["bsub"] + self._get_command_parts())

    def to_shell_script(
        self,
        command: str | list[str] | None = None,
        add_shebang: bool = True,
        shell: str = "/bin/bash",
    ) -> str:
        """
        Convert the LSF job to a shell script string.
        """
        script_lines = []

        if add_shebang:
            script_lines.append(f"#!{shell}")

        command_parts_lines = ["#BSUB " + part for part in self._get_command_parts()]
        script_lines += command_parts_lines

        if command is not None:
            command = shlex.join(command) if isinstance(command, list) else command
            script_lines.append("")  # Add a blank line before the command
            script_lines.append(command)

        return "\n".join(script_lines)

    def get_full_jobname(self) -> str:
        """
        Returns the jobname with array indices
        """
        assert self.jobname is not None, "jobname is None"
        if self.array_indices is not None:
            return f"{self.jobname}[{self.array_indices.to_str()}]"
        return self.jobname

    @model_validator(mode="after")
    def name_given_if_array(self) -> Self:
        if self.array_indices is not None and self.jobname is None:
            raise ValueError("jobname must be provided if array_indices is provided")
        return self

    @model_validator(mode="after")
    def validate_full_jobname(self) -> Self:
        full_jobname = self.get_full_jobname()
        if len(full_jobname) > 255:
            raise ValueError(
                f"Full jobname '{full_jobname}' exceeds maximum length of 255 characters"
            )
        return self

    def submit(self, command: str | list[str] | None, add_shebang: bool = True) -> None:
        """
        Submit the job to the LSF cluster using the bsub command.

        Args:
            command (str): The command to be executed in the job.
        """

        script = self.to_shell_script(command=command, add_shebang=add_shebang)
        # Do not capture bsub's output: it remains attached to the caller's
        # stdout and stderr and is emitted as the scheduler produces it.
        subprocess.run(
            ["bsub"],
            input=script,
            text=True,
            check=True,
            stdout=None,
            stderr=None,
        )

    def submit_python(
        self,
        function: Callable[..., Any],
        args: Sequence[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        add_shebang: bool = True,
    ) -> None:
        python_executable = sys.executable

        args = tuple(args) if args is not None else ()
        kwargs = dict(kwargs) if kwargs is not None else {}

        call = (
            function,
            args,
            kwargs,
        )
        payload_path: Path | None = None
        node_payload_paths: list[Path] = []
        # Because we can launch jobarrays and we are concerned with cleaning up
        # after ourselves, we want to store the payload in a single place, but with
        # a number of hardlinks to it, effectively using reference counting on the filesystem

        # Wrap in try-clause so we can also clean up if submission fails
        try:
            # Can't use /tmp since that is node-local.
            payload_dir = Path.home() / ".cache" / "pez"
            payload_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=payload_dir,
                prefix="python-call-",
                suffix=".pickle",
                delete=False,
            ) as payload_file:
                cloudpickle.dump(
                    call,
                    payload_file,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
                payload_path = Path(payload_file.name)

                # For each index create a hardlink to the payload file
                # such that each job in the job array gets its own deduplicated file
                for idx in self.array_indices or [0]:
                    node_path = get_node_path_from_payload_path(payload_path, idx)
                    node_path.hardlink_to(payload_path)
                    node_payload_paths.append(node_path)

                # Now remove original file, leaving only the hardlinks. The file will be deleted when all hardlinks are removed.
                payload_path.unlink(missing_ok=True)

            argv = [
                python_executable,
                "-c",
                _RUN_PICKLED_CALL_FROM_FILE,
                str(payload_path),
            ]
            self.submit(command=argv, add_shebang=add_shebang)

        # Something went wrong during submission, clean up!
        except:
            if payload_path is not None:
                payload_path.unlink(missing_ok=True)
            for node_path in node_payload_paths:
                node_path.unlink(missing_ok=True)
            raise
