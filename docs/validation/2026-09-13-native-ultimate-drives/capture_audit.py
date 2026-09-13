"""Raw chunk and borrower audit, reused from signed input trace 2eba45b3."""
import hashlib
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def captures(folder, report):
    chunks = total = pairs = 0
    failures = []
    for capture in report['captures']:
        payload = bytearray()
        for chunk in capture['chunks']:
            status = (folder/chunk['status_file']).read_bytes()
            data = (folder/chunk['payload_file']).read_bytes()
            assert sha(status) == chunk['status_sha256'] and len(status) == 12
            assert status[0] == chunk['code'] == 1
            assert not status[9] & 0x40 and status[10] & 15 == 4
            assert status[11] == chunk['foreground_mmu'] in (0, 14)
            assert sha(data) == chunk['payload_sha256'] and len(data) == chunk['count']
            payload.extend(data)
            chunks += 1
        assert len(payload) == capture['count']
        assert payload == (folder/(capture['label']+'.bin')).read_bytes()
        total += len(payload)
        changed = []
        for name, row in capture['borrower_checks'].items():
            before = (folder/row['before_file']).read_bytes()
            after = (folder/row['after_file']).read_bytes()
            assert len(before) == len(after) == row['bytes']
            assert sha(before) == row['before_sha256'] and sha(after) == row['after_sha256']
            offsets = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
            assert row['matches'] == (before == after)
            assert offsets == row['different_offsets']
            assert len(offsets) == len(row['changes'])
            for i, change in zip(offsets, row['changes']):
                assert (change['address'], change['before'], change['after']) == (row['address']+i, before[i], after[i])
            if offsets:
                changed.append(name)
            pairs += 1
        assert capture['restored'] == (not changed)
        assert [r['region'] for r in capture['borrower_failures']] == changed
        if changed:
            failures.append(capture['label'])
    for batch in report.get('paused_capture_batches', []):
        assert batch['pause_acknowledged'] and batch['resume_acknowledged']
    return dict(captures=len(report['captures']), chunks=chunks, payload_bytes=total,
                borrower_pairs=pairs, rejected=failures)

