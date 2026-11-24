# Usage

## `parse_address`

```python
parse_address(address, *, labels=None, data_dir=None) -> pl.Expr
```

`address` is a string expression or a column name. The result is a struct expression, so `.unnest()` it or pick fields with
`.struct.field()`. It works on `LazyFrame`s and the output schema is known without parsing anything.

## Labels

The struct has one string field per libpostal label, in this order (also available as `polars_libpostal.LABELS`):

| Label                                           | Meaning                                  |
| ----------------------------------------------- | ---------------------------------------- |
| `house`, `category`, `near`                     | Venue or building name, type, "near ..." |
| `house_number`, `road`                          | Number and street                        |
| `unit`, `level`, `staircase`, `entrance`        | Apartment, floor, staircase, entrance    |
| `po_box`                                        | PO box                                   |
| `postcode`                                      | Postal code                              |
| `suburb`, `city_district`, `city`               | Sub-city areas and the city              |
| `island`                                        | Island                                   |
| `state_district`, `state`, `country_region`     | Regions below the country                |
| `country`, `world_region`                       | Country and continent-level region       |

- A label that libpostal returns twice is joined with a space.
- A label that is absent, and null or empty input, give null.
- Output is lowercase, as libpostal produces it.
- libpostal ignores the country when it parses, so there is no country argument.

### Choosing labels

`labels` limits the struct to the labels you name, in the order you give. An unknown or repeated label raises `ValueError`.

```python
parse_address("address", labels=["house_number", "road", "city", "postcode"])
```

To get back a single combined field, build it from the labels you want:

```python
pl.concat_str(
    pl.col("p").struct.field("city", "state"), separator=", ", ignore_nulls=True
)
```

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
