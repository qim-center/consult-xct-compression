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
COMPRESSION_TESTS_DIR = PROJECT_SCRATCH_DIR / "compression_tests"

NATURARV3D_STUDY_DIR = (
    Path("/").resolve()
    / "dtu"
    / "3d-imaging-center"
    / "projects"
    / "2026_DANFIX_201"
    / "analysis"
    / "naturarv3d_compression_study"
)

# Reconstructions already cast/scaled for the codecs, one subdirectory per
# variant (e.g. u16_1000) holding one slice_z####.tif stack per dataset.
RECONSTRUCTIONS_TRANSFORMED_DIR = NATURARV3D_STUDY_DIR / "reconstructions_transformed"
