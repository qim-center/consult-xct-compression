set minimum-version := '1.55.0'
set default-list := true

# Installs the project dependencies
[group: 'dev']
install:
    pixi install

[group: 'dev']
shell:
    pixi shell

# Run with `$(just cd-201)` to change to the project directory
[group: 'shortcut']
cd-201:
    echo "cd /dtu/3d-imaging-center/projects/2026_DANFIX_201/analysis/compression"

# Formats the code using ruff
[group: 'format']
format:
    uv run ruff check . --fix
    uv run ruff format .

# Checks the code for linting errors
[group: 'format']
lint:
    uv run ruff check .

# Runs the test suite
[group: 'test']
test:
    uv run pytest
