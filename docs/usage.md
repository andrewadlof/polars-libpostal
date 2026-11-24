# Usage

## `parse_address`

```python
parse_address(address, *, data_dir=None) -> pl.Expr
```

`address` is a string expression or a column name. The result is a struct expression, so `.unnest()` it or pick fields with
`.struct.field()`. It works on `LazyFrame`s and the output schema is known without parsing anything.

| Field          | Content                                                          |
| -------------- | ---------------------------------------------------------------- |
| `house`        | Building or venue name                                           |
| `house_number` | Number on the street                                             |
| `road`         | Street name                                                      |
| `unit`         | Apartment or suite                                               |
| `level`        | Floor                                                            |
| `po_box`       | PO box                                                           |
| `other`        | Every other libpostal label (suburb, city, state, postcode, ...) |

The names are available as `polars_libpostal.COMPONENTS`.

- A label that appears twice is joined with a space.
- Null or empty input gives nulls in every field.
- Output is lowercase, as libpostal produces it.
- libpostal ignores the country when it parses, so there is no country argument.

## Data helpers

```python
from polars_libpostal import data_dir, download_data

data_dir()          # directory that will be used
download_data()     # fetch the models there, returns the path
```

`download_data(dest=None, *, force=False)` skips the download when the directory already holds data.

## Repeated addresses

The plugin parses every row, repeated ones included. If your data has many repeats, parse the distinct values and join the
result back:

```python
uniq = df.select("address").unique().with_columns(parse_address("address").alias("p"))
df.join(uniq, on="address")
```
