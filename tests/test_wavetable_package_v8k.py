from __future__ import annotations

from v8k_helpers import pending_v8k

from w_mwxt_wavetable_tool import DumpFile, WctdMode


def test_dense_package_is_n_wavd_plus_one_wctd_in_strict_order() -> None:
    result = pending_v8k()
    package = result.dense_package
    assert package is not None
    n = len(package.waves)
    assert package.manifest.message_count == n + 1
    assert [item.kind for item in package.manifest.messages] == ["WAVD"] * n + ["WCTD"]
    assert package.manifest.mode is WctdMode.DENSE
    assert len(package.manifest.messages[-1].destination) > 0
    assert package.manifest.messages[-1].byte_length == 265


def test_package_is_self_contained_and_roundtrips() -> None:
    package = pending_v8k().dense_package
    assert package is not None
    reparsed = DumpFile.from_bytes(package.package_bytes)
    assert reparsed.to_bytes() == package.package_bytes
    assert package.manifest.to_dict()["boundaries"]["self_contained"] is True
    assert package.manifest.to_dict()["boundaries"]["contains_sound"] is False


def test_dense_and_sparse_packages_share_waves_but_have_distinct_wctd_bytes() -> None:
    result = pending_v8k()
    dense = result.dense_package
    sparse = result.sparse_package_candidate
    assert dense is not None and sparse is not None
    assert tuple(wave.stored_samples for wave in dense.waves) == tuple(wave.stored_samples for wave in sparse.waves)
    assert dense.wavetable.references != sparse.wavetable.references
    assert dense.sha256 != sparse.sha256


def test_complete_package_is_contract_only_for_v9() -> None:
    contract = pending_v8k().complete_package_contract
    assert contract is not None
    payload = contract.to_dict()
    assert payload["contract"] == "N WAVD + 1 WCTD + 1 SNDD"
    assert payload["implemented"] is False
    assert payload["implemented_in_stage"] == "V9"


def test_package_write_is_deterministic(tmp_path) -> None:
    package = pending_v8k().dense_package
    assert package is not None
    syx, manifest = package.write(tmp_path)
    assert syx.read_bytes() == package.package_bytes
    assert manifest.read_text(encoding="utf-8") == package.manifest.to_json()
