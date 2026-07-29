import os
import sys
from pathlib import Path
from pprint import pprint

import cloudpickle

from comptest.pez.common import get_node_path_from_payload_path
from comptest.pez.constants import LSB_JOBINDEX

if __name__ == "__main__":
    lsb_jobindex = int(os.environ["LSB_JOBINDEX"])

    payload_path = Path(sys.argv[1])

    # We need to get the node payload path
    node_payload_path = get_node_path_from_payload_path(
        payload_path, lsb_jobindex
    )

    # Fetch and unpack the payload from the file
    try:
        with node_payload_path.open("rb") as payload_file:
            function, args, kwargs = cloudpickle.load(payload_file)
    finally:
        node_payload_path.unlink(missing_ok=True)

    # Patch up args/kwargs
    args = tuple(lsb_jobindex if x is LSB_JOBINDEX else x for x in args)
    kwargs = {
        key: lsb_jobindex if value is LSB_JOBINDEX else value
        for key, value in kwargs.items()
    }

    # Run function
    result = function(*args, **kwargs)

    # Print output
    pprint(result)
