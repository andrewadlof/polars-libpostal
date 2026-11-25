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

## `parse_address_list`

```python
parse_address_list(address, *, data_dir=None) -> pl.Expr
```

Returns libpostal's response as it is: a `List(Struct({"label": String, "value": String}))` with one element per component,
in the order the components appear in the address text. Labels are the ones in the table above.

- A label that libpostal returns more than once stays as separate elements, in place.
- Null or empty input gives null.
- It works on `LazyFrame`s and the output schema is known without parsing anything.

Joining each label's values with a space gives the matching `parse_address` field, so use `parse_address` when you want
columns and `parse_address_list` when the order of the parts matters.

```python
df.with_columns(parts=parse_address_list("address"))
```

```
address                                     parts
Apt 4B, 456 Elm Ave, Springfield, IL 62704  [{"unit","apt 4b"}, {"house_number","456"}, {"road","elm ave"},
                                             {"city","springfield"}, {"state","il"}, {"postcode","62704"}]
```

Work on the parts inside each list with `list.eval`. For example, fold every label except the street-level ones into one
column, in address order:

```python
kept = ["house", "house_number", "road", "unit", "level", "po_box"]
label = pl.element().struct.field("label")
value = pl.element().struct.field("value")
parse_address_list("address").list.eval(value.filter(~label.is_in(kept))).list.join(" ")
```

Or get one row per component, to group or join on:

```python
df.with_columns(parts=parse_address_list("address")).explode("parts").unnest("parts")
```

To look labels up by name, convert the list to Polars' `Map` type. `list.to_map()` needs the fields named `key` and `value`:

```python
pl.col("parts").list.eval(
    pl.element().struct.rename_fields(["key", "value"])
).list.to_map()
```

!!! warning

    A `Map` keeps one value per key: the last one. If libpostal splits a label, as in `city: "new"`, `state: "ny"`,
    `city: "york"`, the map holds `{"city": "york", "state": "ny"}` and "new" is lost. Keep the list when the order or the
    repeats matter, or use `parse_address`, which joins repeated labels with a space.

## `expand_address`

```python
expand_address(address, *, languages=None, data_dir=None) -> pl.Expr
```

Returns libpostal's normalized forms of each address as a `List(String)`, in libpostal's order and without repeats. These
are the spellings libpostal considers equivalent: abbreviations spelled out (`St` gives both `street` and `saint`),
numbers written as digits, accents, hyphens and punctuation normalized, all lowercase.

```python
df.with_columns(expanded=expand_address("address"))
```

```
address                                      expanded
30 W 26th St                                 ["30 w 26th saint", "30 w 26th street", "30 west 26th saint",
                                              "30 west 26th street", "30 w 26 saint", "30 w 26 street", ...]
Quatre-vingt-douze Ave des Champs-Élysées    ["92 avenue des champs-elysees", "92 avenue des champs elysees",
                                              "92 avenue des champselysees"]
```

- Null or empty input gives null.
- It works on `LazyFrame`s and the output schema is known without loading anything.
- It does not load the parser model, so an expansion-only process uses far less memory than one that parses.

### Languages

By default libpostal's language classifier guesses the languages of each address, which is how the second row above is
read as French. Pass `languages` when you know them:

```python
expand_address("address", languages=["en"])
expand_address("address", languages=["fr", "de"])
```

Naming the languages is faster and avoids wrong guesses on short inputs, but it is taken literally: read as English,
`rue de rivoli` also expands to `rue delaware rivoli`. Codes are libpostal's 2 or 3 letter lowercase codes (`en`, `fr`,
`fil`, ...). An empty list, a repeat or a code of the wrong shape raises `ValueError`. With `languages` set, the language
classifier is not loaded, so its data is not needed.

### Matching on expansions

Two addresses that share an expansion are likely the same place. Explode the lists and join on them:

```python
def keyed(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(key=expand_address("address")).explode("key")


matches = keyed(left).join(keyed(right), on="key").unique(["left_id", "right_id"])
```

## Data helpers

```python
from polars_libpostal import data_dir, download_data

data_dir()  # directory that will be used
download_data()  # fetch the models there, returns the path
```

`download_data(dest=None, *, force=False)` skips the download when the directory already holds data.

## Repeated addresses

The plugin parses every row, repeated ones included. If your data has many repeats, parse the distinct values and join the
result back:

```python
uniq = df.select("address").unique().with_columns(parse_address("address").alias("p"))
df.join(uniq, on="address", how="left")
```
