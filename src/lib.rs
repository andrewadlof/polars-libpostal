//! Polars expression plugin that parses and expands addresses with libpostal.
//!
//! Rows are processed in parallel on Polars' own Rayon pool. For parsing that
//! is only safe with the patched libpostal in `patches/`: stock libpostal keeps
//! one shared parse context, CRF context and Viterbi buffer, so concurrent
//! callers corrupt each other's state. Expansion and language classification
//! only read their models and allocate per call, so they need no patch; the
//! ThreadSanitizer stress test (`scripts/tsan.sh ... expand`) checks that.

use std::ffi::{c_char, CStr, CString};
use std::path::Path;
use std::sync::{Mutex, OnceLock};

use polars::chunked_array::builder::get_list_builder;
use polars::prelude::*;
use pyo3::types::PyModule;
use pyo3::{pymodule, Bound, PyResult, Python};
use pyo3_polars::derive::polars_expr;
use pyo3_polars::export::polars_core::runtime::RAYON;
use rayon::prelude::*;
use serde::Deserialize;

#[repr(C)]
#[derive(Clone, Copy)]
struct ParserOptions {
    language: *mut c_char,
    country: *mut c_char,
}

#[repr(C)]
struct ParserResponse {
    num_components: usize,
    components: *mut *mut c_char,
    labels: *mut *mut c_char,
}

/// `libpostal_normalize_options_t`. Every field is declared so the layout
/// matches the C struct; only the language fields are set from Rust.
#[repr(C)]
#[derive(Clone, Copy)]
struct NormalizeOptions {
    languages: *mut *mut c_char,
    num_languages: usize,
    address_components: u16,
    latin_ascii: bool,
    transliterate: bool,
    strip_accents: bool,
    decompose: bool,
    lowercase: bool,
    trim_string: bool,
    drop_parentheticals: bool,
    replace_numeric_hyphens: bool,
    delete_numeric_hyphens: bool,
    split_alpha_from_numeric: bool,
    replace_word_hyphens: bool,
    delete_word_hyphens: bool,
    delete_final_periods: bool,
    delete_acronym_periods: bool,
    drop_english_possessives: bool,
    delete_apostrophes: bool,
    expand_numex: bool,
    roman_numerals: bool,
}

type Loader = unsafe extern "C" fn(datadir: *mut c_char) -> bool;

extern "C" {
    fn libpostal_setup_datadir(datadir: *mut c_char) -> bool;
    fn libpostal_setup_parser_datadir(datadir: *mut c_char) -> bool;
    fn libpostal_setup_language_classifier_datadir(datadir: *mut c_char) -> bool;
    fn libpostal_get_address_parser_default_options() -> ParserOptions;
    fn libpostal_parse_address(address: *mut c_char, options: ParserOptions)
        -> *mut ParserResponse;
    fn libpostal_address_parser_response_destroy(response: *mut ParserResponse);
    fn libpostal_get_default_options() -> NormalizeOptions;
    fn libpostal_expand_address(
        input: *mut c_char,
        options: NormalizeOptions,
        n: *mut usize,
    ) -> *mut *mut c_char;
    fn libpostal_expansion_array_destroy(expansions: *mut *mut c_char, n: usize);
}

#[derive(Deserialize)]
struct ParseKwargs {
    /// Directory holding `address_parser/`, `numex/`, `transliteration/` and
    /// `address_expansions/`.
    data_dir: String,
    /// Labels to return, in output order. The Python side validates them
    /// against libpostal's label set.
    labels: Vec<String>,
}

#[derive(Deserialize)]
struct ListKwargs {
    /// Same as `ParseKwargs::data_dir`.
    data_dir: String,
}

#[derive(Deserialize)]
struct ExpandKwargs {
    /// Same as `ParseKwargs::data_dir`.
    data_dir: String,
    /// Language codes to expand for. Empty means libpostal's language
    /// classifier picks them per address.
    languages: Vec<String>,
}

/// Each part of libpostal's data loads once per process, on first use. The
/// first call's directory wins.
static BASE: OnceLock<Result<(), String>> = OnceLock::new();
static PARSER: OnceLock<Result<(), String>> = OnceLock::new();
static CLASSIFIER: OnceLock<Result<(), String>> = OnceLock::new();
/// libpostal's setup functions are not documented as safe to run at the same
/// time, and a query can reach two of them at once from different threads.
static LOADING: Mutex<()> = Mutex::new(());

fn load(
    cell: &OnceLock<Result<(), String>>,
    data_dir: &str,
    folder: &str,
    loader: Loader,
) -> PolarsResult<()> {
    let result = cell.get_or_init(|| {
        if !Path::new(data_dir).join(folder).is_dir() {
            return Err(format!(
                "libpostal data not found in {data_dir:?} (no {folder}/); run `python -m polars_libpostal download-data`"
            ));
        }
        let dir = CString::new(data_dir).map_err(|e| e.to_string())?;
        let _guard = LOADING.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        // Safety: libpostal copies the path while loading; `dir` outlives the call.
        if unsafe { loader(dir.as_ptr() as *mut c_char) } {
            Ok(())
        } else {
            Err(format!("libpostal could not load {folder}/ from {data_dir:?}"))
        }
    });
    result.clone().map_err(|msg| PolarsError::ComputeError(msg.into()))
}

/// Load the shared dictionaries and the parser model (about 3 GB).
fn setup(data_dir: &str) -> PolarsResult<()> {
    load(&BASE, data_dir, "address_expansions", libpostal_setup_datadir)?;
    load(&PARSER, data_dir, "address_parser", libpostal_setup_parser_datadir)
}

/// Load the shared dictionaries, plus the language classifier when libpostal
/// has to guess the language. Expansion does not need the parser model.
fn setup_expansion(data_dir: &str, classify: bool) -> PolarsResult<()> {
    load(&BASE, data_dir, "address_expansions", libpostal_setup_datadir)?;
    if classify {
        load(
            &CLASSIFIER,
            data_dir,
            "language_classifier",
            libpostal_setup_language_classifier_datadir,
        )?;
    }
    Ok(())
}

/// Parse one address into its `(label, value)` components, in libpostal's
/// response order, which is the order of the address text. Repeated labels
/// are kept as separate components. `None` when libpostal cannot take the
/// input (an interior NUL) or returns no response.
fn parse_components(address: &str) -> Option<Vec<(String, String)>> {
    let c_address = CString::new(address).ok()?;
    // Safety: as in `parse_one`.
    unsafe {
        let response = libpostal_parse_address(
            c_address.as_ptr() as *mut c_char,
            libpostal_get_address_parser_default_options(),
        );
        if response.is_null() {
            return None;
        }
        let n = (*response).num_components;
        let mut out = Vec::with_capacity(n);
        for i in 0..n {
            let label = CStr::from_ptr(*(*response).labels.add(i)).to_string_lossy();
            let value = CStr::from_ptr(*(*response).components.add(i)).to_string_lossy();
            out.push((label.into_owned(), value.into_owned()));
        }
        libpostal_address_parser_response_destroy(response);
        Some(out)
    }
}

/// Parse one address into one value per requested label. Labels libpostal
/// returns that were not requested are dropped; a label that appears more than
/// once is joined with a space.
fn parse_one(address: &str, labels: &[String]) -> Vec<Option<String>> {
    let mut out: Vec<Option<String>> = vec![None; labels.len()];
    let Ok(c_address) = CString::new(address) else {
        return out;
    };
    // Safety: `c_address` is a valid NUL-terminated string for the whole call,
    // the response is only read before it is destroyed, and parsing is
    // thread-safe with the patched libpostal.
    unsafe {
        let response = libpostal_parse_address(
            c_address.as_ptr() as *mut c_char,
            libpostal_get_address_parser_default_options(),
        );
        if response.is_null() {
            return out;
        }
        for i in 0..(*response).num_components {
            let label = CStr::from_ptr(*(*response).labels.add(i)).to_string_lossy();
            let Some(slot) = labels.iter().position(|l| *l == label) else {
                continue;
            };
            let value = CStr::from_ptr(*(*response).components.add(i)).to_string_lossy();
            match &mut out[slot] {
                Some(existing) => {
                    existing.push(' ');
                    existing.push_str(&value);
                },
                empty => *empty = Some(value.into_owned()),
            }
        }
        libpostal_address_parser_response_destroy(response);
    }
    out
}

fn parsed_output(_input_fields: &[Field], kwargs: ParseKwargs) -> PolarsResult<Field> {
    let fields = kwargs
        .labels
        .iter()
        .map(|name| Field::new(name.as_str().into(), DataType::String))
        .collect();
    Ok(Field::new("parsed".into(), DataType::Struct(fields)))
}

#[polars_expr(output_type_func_with_kwargs=parsed_output)]
fn parse_address(inputs: &[Series], kwargs: ParseKwargs) -> PolarsResult<Series> {
    let addresses = inputs[0].str()?;
    setup(&kwargs.data_dir)?;

    // Collect first so the parallel section works on plain slices
    let rows: Vec<Option<&str>> = addresses.iter().map(|a| a.filter(|s| !s.is_empty())).collect();
    let labels = &kwargs.labels;
    let parsed: Vec<Vec<Option<String>>> = RAYON.install(|| {
        rows.par_iter()
            .map(|row| match row {
                Some(address) => parse_one(address, labels),
                None => vec![None; labels.len()],
            })
            .collect()
    });

    let columns: Vec<Series> = labels
        .iter()
        .enumerate()
        .map(|(k, name)| {
            let values: StringChunked = parsed.iter().map(|row| row[k].as_deref()).collect();
            values.with_name(name.as_str().into()).into_series()
        })
        .collect();
    StructChunked::from_series("parsed".into(), parsed.len(), columns.iter())
        .map(|s| s.into_series())
}

fn component_dtype() -> DataType {
    DataType::Struct(vec![
        Field::new("label".into(), DataType::String),
        Field::new("value".into(), DataType::String),
    ])
}

fn list_output(_input_fields: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new("parts".into(), DataType::List(Box::new(component_dtype()))))
}

#[polars_expr(output_type_func=list_output)]
fn parse_address_list(inputs: &[Series], kwargs: ListKwargs) -> PolarsResult<Series> {
    let addresses = inputs[0].str()?;
    setup(&kwargs.data_dir)?;

    let rows: Vec<Option<&str>> = addresses.iter().map(|a| a.filter(|s| !s.is_empty())).collect();
    let parsed: Vec<Option<Vec<(String, String)>>> =
        RAYON.install(|| rows.par_iter().map(|row| row.and_then(parse_components)).collect());

    // One flat struct column of every component, then each row is a slice of it.
    let labels: StringChunked =
        parsed.iter().flatten().flatten().map(|(label, _)| Some(label.as_str())).collect();
    let values: StringChunked =
        parsed.iter().flatten().flatten().map(|(_, value)| Some(value.as_str())).collect();
    let flat = StructChunked::from_series(
        "parts".into(),
        labels.len(),
        [
            labels.with_name("label".into()).into_series(),
            values.with_name("value".into()).into_series(),
        ]
        .iter(),
    )?
    .into_series();

    let mut builder =
        get_list_builder(&component_dtype(), flat.len(), parsed.len(), "parts".into());
    let mut offset = 0i64;
    for row in &parsed {
        match row {
            Some(parts) => {
                builder.append_series(&flat.slice(offset, parts.len()))?;
                offset += parts.len() as i64;
            },
            None => builder.append_null(),
        }
    }
    Ok(builder.finish().into_series())
}

/// Expand one address into its normalized forms, in libpostal's order.
/// `languages` empty lets libpostal's classifier pick the languages. `None`
/// when libpostal cannot take the input (an interior NUL) or returns nothing.
fn expand_one(address: &str, languages: &[CString]) -> Option<Vec<String>> {
    let c_address = CString::new(address).ok()?;
    let mut language_ptrs: Vec<*mut c_char> =
        languages.iter().map(|l| l.as_ptr() as *mut c_char).collect();
    // Safety: `c_address` and the language strings outlive the call, libpostal
    // only reads them, and the result is read before it is destroyed.
    // Expansion keeps no shared mutable state (see the module docs).
    unsafe {
        let mut options = libpostal_get_default_options();
        if !language_ptrs.is_empty() {
            options.languages = language_ptrs.as_mut_ptr();
            options.num_languages = language_ptrs.len();
        }
        let mut n = 0usize;
        let expansions =
            libpostal_expand_address(c_address.as_ptr() as *mut c_char, options, &mut n);
        if expansions.is_null() {
            return None;
        }
        let out = (0..n)
            .map(|i| CStr::from_ptr(*expansions.add(i)).to_string_lossy().into_owned())
            .collect();
        libpostal_expansion_array_destroy(expansions, n);
        Some(out)
    }
}

fn expanded_output(_input_fields: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new("expansions".into(), DataType::List(Box::new(DataType::String))))
}

#[polars_expr(output_type_func=expanded_output)]
fn expand_address(inputs: &[Series], kwargs: ExpandKwargs) -> PolarsResult<Series> {
    let addresses = inputs[0].str()?;
    setup_expansion(&kwargs.data_dir, kwargs.languages.is_empty())?;
    let languages: Vec<CString> = kwargs
        .languages
        .iter()
        .map(|l| CString::new(l.as_str()))
        .collect::<Result<_, _>>()
        .map_err(|e| PolarsError::ComputeError(e.to_string().into()))?;

    let rows: Vec<Option<&str>> = addresses.iter().map(|a| a.filter(|s| !s.is_empty())).collect();
    let expanded: Vec<Option<Vec<String>>> = RAYON.install(|| {
        rows.par_iter().map(|row| row.and_then(|a| expand_one(a, &languages))).collect()
    });

    let values = expanded.iter().flatten().map(Vec::len).sum();
    let mut builder = ListStringChunkedBuilder::new("expansions".into(), expanded.len(), values);
    for row in &expanded {
        match row {
            Some(forms) => builder.append_values_iter(forms.iter().map(String::as_str)),
            None => builder.append_null(),
        }
    }
    Ok(builder.finish().into_series())
}

#[pymodule]
fn _internal(_py: Python, _m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
