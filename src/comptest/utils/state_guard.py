from collections.abc import Hashable

import sentinel  # TODO: Built-in in 3.15

__SENTINEL = sentinel.create("state_guard.run_once_guard")

_RUN_ONCE_GUARDS = set()


def run_once_guard(id: Hashable = __SENTINEL) -> bool:
    """
    A guard that ensures that a block of code may only be executed once.

    Very useful in Jupyter notebooks where cells may be re-executed multiple times,
    but you want to ensure that a block of code is only executed once.

    Example:
    ```
    if run_once_guard("my_block"):
        # This code will only be executed once, even if the cell is re-executed.
        print("This will only be printed once.")
    ```

    Arguments:
        - id: an identifier for the block. If not provided, uses a global sentinel id.
    """
    if id in _RUN_ONCE_GUARDS:
        return False

    _RUN_ONCE_GUARDS.add(id)
    return True


def clear_run_once_guard(id: Hashable = __SENTINEL) -> None:
    """
    Clears the run once guard for a given id.

    Arguments:
        - id: an identifier for the block. If not provided, uses the global sentinel id.
    """
    if id in _RUN_ONCE_GUARDS:
        _RUN_ONCE_GUARDS.remove(id)
