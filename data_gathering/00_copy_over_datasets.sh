#!/bin/bash
set -euo pipefail

VERBOSE=true

# Recursively copy the contents of SRC into DST, skipping files already up to date.
# Usage: copy_dir SRC DST
copy_dir() {
    local src="$1"
    local dst="$2"

    if [ ! -d "$src" ]; then
        echo "Error: '$src' is not a directory" >&2
        return 1
    fi

    local rsync_flags=(-a --info=progress2)
    if [ "$VERBOSE" = true ]; then
        rsync_flags+=(-v)
    fi

    echo "Copying $src -> $dst"
    mkdir -p "$dst"
    rsync "${rsync_flags[@]}" "$src/" "$dst/"
}

copy_dir \
    "/dtu/3d-imaging-center/projects/2022_DANFIX_70_WOLF-MORPH/raw_data_3DIM/Alaska_UAM_2023/Box2/Canislupus_UAM_18197 [2023-04-05 12.39.02]"\
    "/dtu/3d-imaging-center/projects/2026_DANFIX_201/analysis/naturarv3d_compression_study/reconstruction_inputs/Canislupus_UAM_18197"

copy_dir \
    "/dtu/3d-imaging-center/projects/2022_DANFIX_70_WOLF-MORPH/raw_data_3DIM/Bergen_BM_2023/Canislupus_BM_2600 [2023-04-06 17.41.56]"\
    "/dtu/3d-imaging-center/projects/2026_DANFIX_201/analysis/naturarv3d_compression_study/reconstruction_inputs/Canislupus_BM_2600"

copy_dir \
    "/dtu/3d-imaging-center/projects/2022_DANFIX_70_WOLF-MORPH/raw_data_3DIM/Copenhagen_CZM_2023/Canislupus_CZM_712 [2023-04-07 11.57.59]"\
    "/dtu/3d-imaging-center/projects/2026_DANFIX_201/analysis/naturarv3d_compression_study/reconstruction_inputs/Canislupus_CZM_712"
