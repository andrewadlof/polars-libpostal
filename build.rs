// Links the libpostal shared library.
//
// LIBPOSTAL_PREFIX must point at an install of the *patched* libpostal (the
// one `scripts/build_libpostal.sh` produces): stock libpostal shares one parse
// context between all callers and corrupts memory when parsed from several
// threads, which this plugin does on Polars' thread pool.
fn main() {
    let prefix = std::env::var("LIBPOSTAL_PREFIX").unwrap_or_else(|_| "/usr/local".into());
    println!("cargo:rerun-if-env-changed=LIBPOSTAL_PREFIX");
    println!("cargo:rustc-link-search=native={prefix}/lib");
    println!("cargo:rustc-link-lib=dylib=postal");
    // Lets a plain `maturin develop` build find the library without
    // LD_LIBRARY_PATH. Wheels are repaired by auditwheel, which bundles
    // libpostal.so and rewrites this rpath.
    println!("cargo:rustc-link-arg=-Wl,-rpath,{prefix}/lib");
}
