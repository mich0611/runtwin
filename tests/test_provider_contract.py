from pathlib import Path

from runtwin.providers.snapshot import SnapshotProvider


def test_snapshot_exposes_activity_details_and_capabilities():
    path = Path(__file__).parent.parent / "fixtures" / "anonymous_mcp_snapshot.json"
    provider = SnapshotProvider(path)
    capability = provider.capabilities()
    assert capability.activity_list
    assert capability.activity_details
    assert capability.scheduler_safe
    assert provider.get_activity_details("fx-easy-1")["name"] == "Easy Run"
