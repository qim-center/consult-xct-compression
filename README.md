# NaturArv3D Compression Study

This repository contains the code, documentation, and results that forms the compression study
undertaken by Jeppe Klitgaard as part of QIM's contribution to the NaturArv3D Data Pipeline.

## Navigating the Repository

Older tests and documentation was moved to `archive/`, which notably features
an early report-like document that was never finished.

In `docs/` you will find most of the results alongside their documentation,
mostly in the form of slides for the Data Pipeline meetings with the NaturArv3D Steering Group (NA3D-SA):

- `docs/meetings/**/slides.pdf`: slides that were produced prior to meetings in the NA3D-SA
- `docs/poster_abstract_D3A_4_0`: poster abstract submitted to and accepted by the D3A 4.0 Conference
- `docs/poster_D3A_4_0`: poster presented at the D3A 4.0 Conference
    - Note: A full rerun of the experiments were performed for the poster results, which are the most up-to-date experimental results.
    - These were run using the pipeline given in `data_gathering/`
    - The raw data results are stored in `docs/poster_D3A_4_0/assets/summary.csv`

### Handover

Lastly, the results and documents stored in `docs/handover/` are a copy/summary of everything else in
the repository and should be sufficient to summarise and understand all the key points and results of the study.

## Reproducibility

A reproducible environment is defined using the `pixi` tool which leverages `pixi.lock` and `pyproject.toml`.

The tests were run on the DTU HPC Cluster using the job submission files strewn about the repository.
As seen in those files, specific host groups were selected to ensure equivalent hardware was used within each substudy.

## LLM Disclosure

Much of the initial study and structure was hand-coded.
This was then used as context for an LLM (Claude Opus 5.5) to produce the
scaffolding in `data_gathering/*.{py,sh}` which instruments the HPC using the
human-made library in `src/comptest` to produce various experimental results.

Similarly, the documents in `docs/**/*.typ` are human-made,
but some of the code that has generated the plots was made with LLM assistance,
particularly to iterate on different plot layouts and colors for the poster.

The author happily takes responsibility for all the code, that made exclusively by myself
as well as that made with LLM assistance.

## Contact

If you have questions or concerns around the study, please do not hesitate to contact the author
Jeppe Klitgaard:

- E-Mail (DTU): `s250250@dtu.dk`
- E-Mail (Personal): `qim+naturarv3d@jeppe.science`

Alternatively, you can reach out to the QIM Center directly.
