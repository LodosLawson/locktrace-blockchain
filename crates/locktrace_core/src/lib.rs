pub mod crypto;
pub mod merkle;
pub mod pow;

use pyo3::prelude::*;

#[pyfunction]
fn public_key_to_address(pub_hex: &str) -> PyResult<Option<String>> {
    Ok(crypto::public_key_to_address(pub_hex))
}

#[pyfunction]
fn verify_signature(pub_hex: &str, data: &str, sig_hex: &str) -> PyResult<bool> {
    Ok(crypto::verify_signature(pub_hex, data, sig_hex))
}

#[pyfunction]
fn compute_merkle_root(tx_hashes: Vec<String>) -> PyResult<String> {
    Ok(merkle::compute_merkle_root(&tx_hashes))
}

#[pyfunction]
fn solve_pow(
    prefix: &str,
    suffix: &str,
    target_difficulty: u32,
    max_nonces: u64,
) -> PyResult<(bool, u64, String, f64)> {
    Ok(pow::solve_pow(prefix, suffix, target_difficulty, max_nonces))
}

#[pyfunction]
fn is_native_rust_active() -> PyResult<bool> {
    Ok(true)
}

#[pymodule]
fn locktrace_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(public_key_to_address, m)?)?;
    m.add_function(wrap_pyfunction!(verify_signature, m)?)?;
    m.add_function(wrap_pyfunction!(compute_merkle_root, m)?)?;
    m.add_function(wrap_pyfunction!(solve_pow, m)?)?;
    m.add_function(wrap_pyfunction!(is_native_rust_active, m)?)?;
    m.add("__version__", "2.8.0")?;
    Ok(())
}

