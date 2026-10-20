import pytest
from moatleak.readers.hermes import HermesLogReader
from moatleak.registry import Registry
from moatleak.resolve import resolve

pytestmark = pytest.mark.acceptance


def test_every_served_by_name_resolves(snapshot):
    _, gt = snapshot
    reg = Registry.load()
    missing = [n for n in gt["served_by"] if reg.provider_for_name(n) is None]
    assert not missing, f"{len(missing)} unresolved provider names"


def test_g1_parent_coverage(snapshot):
    _, gt = snapshot
    reg = Registry.load()
    names = list(gt["served_by"])
    known = 0
    for n in names:
        pid = reg.provider_for_name(n)
        if pid and reg.providers[pid].get("parent_id", "unknown") != "unknown":
            known += 1
    assert known / len(names) >= 0.8


def test_resolver_end_to_end_no_unknown(snapshot):
    home, _ = snapshot
    reg = Registry.load()
    unknown = 0
    for row in HermesLogReader().iter_rows(home):
        if row.served_by_raw and resolve(row, reg).provider_id is None:
            unknown += 1
    assert unknown == 0, f"{unknown} rows with served_by_raw unresolved"
