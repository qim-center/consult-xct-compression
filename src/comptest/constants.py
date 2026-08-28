from pathlib import Path

PROJECT_SCRATCH_DIR = (
    Path("/").resolve()
    / "dtu"
    / "3d-imaging-center"
    / "projects"
    / "2026_DANFIX_201"
    / "analysis"
    / "compression"
)

DATASETS_PROJECTIONS_DIR = PROJECT_SCRATCH_DIR / "datasets_projections"
DATASETS_RECONSTRUCTIONS_DIR = PROJECT_SCRATCH_DIR / "datasets_reconstructions"
