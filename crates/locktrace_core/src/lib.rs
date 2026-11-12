pub mod compact;
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
fn batch_verify_signatures(py: Python<'_>, items: Vec<(String, String, String)>) -> PyResult<Vec<bool>> {
    let res = py.detach(|| {
        crypto::batch_verify_signatures(&items)
    });
    Ok(res)
}

#[pyfunction]
fn compute_merkle_root(py: Python<'_>, tx_hashes: Vec<String>) -> PyResult<String> {
    let res = py.detach(|| {
        merkle::compute_merkle_root(&tx_hashes)
    });
    res.map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
}

#[pyfunction]
fn verify_spv_proof(
    target_hash: &str,
    merkle_root: &str,
    proof_steps: Vec<(String, String)>,
) -> PyResult<bool> {
    Ok(merkle::verify_spv_proof(target_hash, merkle_root, &proof_steps))
}

#[pyfunction]
#[pyo3(signature = (prefix, suffix, target_difficulty, max_nonces, start_nonce=0))]
fn solve_pow(
    py: Python<'_>,
    prefix: &str,
    suffix: &str,
    target_difficulty: u32,
    max_nonces: u64,
    start_nonce: u64,
) -> PyResult<(bool, u64, String, f64)> {
    let res = py.detach(|| {
        pow::solve_pow(prefix, suffix, target_difficulty, max_nonces, start_nonce)
    });
    Ok(res)
}

#[pyfunction]
fn validate_compact_block_json(json_str: &str) -> PyResult<bool> {
    compact::deserialize_compact_block(json_str.as_bytes())
        .map(|_| true)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
}

#[pyfunction]
fn serialize_compact_block_json(json_str: &str) -> PyResult<String> {
    let block = compact::deserialize_compact_block(json_str.as_bytes())
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
    let bytes = compact::serialize_compact_block(&block)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
    String::from_utf8(bytes).map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

#[pyfunction]
fn is_native_rust_active() -> PyResult<bool> {
    Ok(true)
}

#[pymodule]
fn locktrace_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(public_key_to_address, m)?)?;
    m.add_function(wrap_pyfunction!(verify_signature, m)?)?;
    m.add_function(wrap_pyfunction!(batch_verify_signatures, m)?)?;
    m.add_function(wrap_pyfunction!(compute_merkle_root, m)?)?;
    m.add_function(wrap_pyfunction!(verify_spv_proof, m)?)?;
    m.add_function(wrap_pyfunction!(solve_pow, m)?)?;
    m.add_function(wrap_pyfunction!(validate_compact_block_json, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_compact_block_json, m)?)?;
    m.add_function(wrap_pyfunction!(is_native_rust_active, m)?)?;
    m.add("__version__", "2.9.2")?;
    Ok(())
}
