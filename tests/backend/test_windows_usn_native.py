import os
from contextlib import closing

import pytest

from collectors.windows.inventory import Scope
from collectors.windows.native import NativeInventory
from collectors.windows.usn_native import NativeJournal
from packages.contracts.inventory import FileObjectRecord

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native Windows NTFS required")


def test_existing_journal_readonly_crud_and_inventory_identity(tmp_path):
    root = tmp_path / "synthetic-usn"
    root.mkdir()
    scope = Scope((str(root),))
    journal = NativeJournal(scope)
    assert len(journal.volumes) == 1
    volume = journal.volumes[0]
    with closing(journal.open(volume)) as stream:
        before = stream.query()
        target = root / "Синтетический.txt"
        target.write_text("one", encoding="utf-8")
        target.write_text("two", encoding="utf-8")
        metadata = [o.record for o in NativeInventory().scan(scope)
                    if isinstance(o.record, FileObjectRecord) and o.record.name == target.name]
        assert len(metadata) == 1
        file_id = metadata[0].file_id
        target = target.rename(root / "После.txt")
        target.unlink()
        cursor = before.next_usn
        found = []
        for _ in range(50):
            next_cursor, records = stream.read(before.journal_id, cursor)
            found.extend(r for r in records if r.file_id == file_id)
            if next_cursor == cursor:
                break
            cursor = next_cursor
        assert len(found) > 0, "SYNTHETIC_RECORDS_NOT_FOUND"
        assert any(r.reason & 0x100 for r in found), "CREATE_MISSING"
        assert any(r.reason & 7 for r in found), "WRITE_MISSING"
        assert any(r.reason & 0x1000 for r in found), "RENAME_OLD_MISSING"
        assert any(r.reason & 0x2000 for r in found), "RENAME_NEW_MISSING"
        assert any(r.reason & 0x200 for r in found), "DELETE_MISSING"
        assert {r.name for r in found} <= {"Синтетический.txt", "После.txt"}
        after = stream.query()
        assert after.journal_id == before.journal_id
        assert after.maximum_size == before.maximum_size
        assert after.allocation_delta == before.allocation_delta
