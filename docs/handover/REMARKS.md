# Remarks

Much of the later discussion focused around _container formats_ as opposed to
the specific compression codecs.

As such, I believe that when the results of this study are to be implemented,
the choice of the exact compression codec should be revisited, perhaps using
the `summary.csv` data or by running new experiments.

In particular, if (OME-)Zarr is chosen as the preferred container format,
I expect that more codecs will have reached standardisation
(see: [`zarr-developers/zarr-extensions`](https://github.com/zarr-developers/zarr-extensions)).

If a suitable lossy codec has reached standardisation, this should be preferred over codecs
that reach maximal performance. As such, the JPEG-XL codec that was demonstrated for plots
in the meetings and on the poster should be considered an _example_ rather than an
endorsement of a particular codec.

When such a time arrives, I am happy to join a meeting to advise on the exact choice of
codec.

The full code for the study, the experiments, and the results can be found at
https://github.com/qim-center/consult-xct-compression.

Very best,
_Jeppe_

## Contact

If you have questions or concerns around the study, please do not hesitate to contact the author
Jeppe Klitgaard:

- E-Mail (DTU): `s250250@dtu.dk`
- E-Mail (Personal): `qim+naturarv3d@jeppe.science`

Alternatively, you can reach out to the QIM Center directly.
