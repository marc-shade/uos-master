#!/usr/bin/env python3
"""Check host stream backpressure and explicit native session shutdown."""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/claude/host'))
import bridge
import protocol


def run():
    proc = bridge.PtyProcess.__new__(bridge.PtyProcess)
    proc.fd = 42; proc.pending = bytearray(); received = bytearray()
    limits = iter((2, None, 1, 3))
    def writer(fd, data):
        assert fd == 42
        limit = next(limits)
        if limit is None: raise BlockingIOError
        received.extend(data[:limit]); return min(limit,len(data))
    with patch.object(bridge.os,'write',writer):
        proc.write(b'abc'); assert received==b'ab' and proc.pending==b'c'
        proc.write(b'def'); assert proc.pending==b'cdef'
        proc.flush(); proc.flush()
    assert received==b'abcdef' and not proc.pending
    proc.reaped=True;proc.pid=123
    with patch.object(bridge.os,'killpg') as signal, patch.object(bridge.os,'close') as close:
        proc.close();signal.assert_not_called();close.assert_called_once_with(42)
    b=bridge.Bridge.__new__(bridge.Bridge);b.pending_escape=False
    try:
        assert b._take_control(b'p\0')==b'p'
        b._take_control(bytes([protocol.CLIENT_BYE]))
    except bridge.ClientClosed: pass
    else: raise AssertionError('split native BYE was not recognized')
    class Link:
        credits=17
    class Differ:
        def reset(self): self.reset_called=True
    b.link=Link();b.differ=Differ();b.client_ready=True;b.verbose=False
    b._control(protocol.CLIENT_RESYNC)
    assert b.link.credits==17 and b.differ.reset_called and b.dirty
    return ['partial and blocked PTY writes preserve all input in order',
            'reaped child is never signaled', 'split native BYE is a normal close',
            'RESYNC leaves receive credits unchanged']


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    result=dict(passed=False,physical_hardware_io=False)
    try:
        result['cases']=run();result['passed']=True;print('PASS:',len(result['cases']),'host bridge controls')
    except BaseException as exc: result['error']=repr(exc);raise
    finally:a.report.write_text(json.dumps(result,indent=2)+'\n')
