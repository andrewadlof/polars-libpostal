# polars-libpostal

Parse street addresses with [libpostal](https://github.com/openvenues/libpostal) as a Polars expression that runs on every
core.

```bash
uv add polars-libpostal
uv run python -m polars_libpostal download-data    # about 3 GB, once
```

```python
import polars as pl
from polars_libpostal import parse_address

df = pl.DataFrame({"address": ["Apt 4B, 456 Elm Ave, Springfield, IL 62704", None]})
df.with_columns(
    parse_address("address", labels=["house_number", "road", "unit", "city", "state", "postcode"])
    .alias("p")
).unnest("p")
```

```
address                                       house_number  road     unit    city         state  postcode
Apt 4B, 456 Elm Ave, Springfield, IL 62704    456           elm ave  apt 4b  springfield  il     62704
null                                          null          null     null    null         null   null
```

## Why this exists

libpostal is a C library, but stock libpostal cannot be called from several threads: its address parser shares scratch
space between calls. From Python the usual workaround is one process per core, each loading its own 3 GB model.

This package ships a patched libpostal that gives each thread its own scratch space, and a Rust plugin that parses rows on
Polars' own Rayon pool. One process, one copy of the model, all cores.

## Speed

Measured on 14 cores (WSL2) with 193,500 distinct addresses:

| Parser                                      | Throughput                 |
| ------------------------------------------- | -------------------------- |
| libpostal through its Python binding        | about 10,000 addresses/s   |
| `polars-libpostal` on 14 threads            | about 54,000 addresses/s   |

The patched parser scales to about 4x at 4 threads and 6x at 8 threads in the C stress test, then flattens.

## Next

- [Install](install.md) the wheel and download the model data.
- [Usage](usage.md) covers the output struct and the API.
- [How it works](architecture.md) explains the patch and how it is tested.
