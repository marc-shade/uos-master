"""Collect a finite idle/pause/IRQ-capture input trace, retaining rejections."""
import time
from native_capture import wait
from native_input_trace import InputTrace


def run_input_workflow(mon,capture,work,disk,report,save,*,idle_seconds=30,pause_batches=12,captures=6):
    def read(address,count=1):
        data=bytes(mon.read_mem(address,address+count-1));mon.resume();return data
    wait(lambda:read(0x1c13,6)==b'UOS128' and read(0x3d11,2)==b'\0\1' and read(0xd0,2)==b'\0\0',
         'native desktop idle before input trace',180)
    trace=InputTrace(mon,work,capture.batch,report,save)
    report['input_diagnostic']=diagnostic=dict(completed=False,app_qualification=False,
        idle_seconds=idle_seconds,pause_batches=pause_batches,capture_limit=captures,
        phases=[],initial_selection=read(0x3d2f)[0],initial_keys=int.from_bytes(read(0x3d13,2),'little'))
    try:
        trace.install()
        capture.batch=trace.timed_batch
        trace.phase(1)
        start=time.monotonic()
        print('Input trace: idle CPU interval, no host requests for',idle_seconds,'seconds',flush=True)
        while True:
            remaining=idle_seconds-(time.monotonic()-start)
            if remaining<=0:break
            time.sleep(min(10,remaining))
        first=trace.snapshot('input-idle')
        diagnostic['phases'].append(dict(phase=1,start=start,finish=time.monotonic(),
            scans=first['scans'],consumed=first['consumed']));save()
        trace.phase(2)
        print('Input trace: bounded host pause/read/resume batches',flush=True)
        for index in range(pause_batches):
            with trace.timed_batch(f'input-pause-{index}'):
                row=dict(phase=2,index=index,time=time.monotonic(),
                    keyboard_state=read(0xcc,10).hex(),buffer=read(0x34a,10).hex(),header=read(0x5200,15).hex())
                diagnostic['phases'].append(row);save()
        trace.snapshot('input-pauses')
        trace.phase(3)
        print('Input trace: bounded IRQ captures with unchanged borrower checks',flush=True)
        for index in range(captures):
            try:
                capture.capture(f'input-observer-{index}',address=0x2500,count=2000)
            except BaseException as error:
                diagnostic['capture_rejected']=dict(index=index,type=type(error).__name__,message=str(error))
                save();raise
            trace.snapshot(f'input-observer-state-{index}')
        diagnostic['completed']=True;save()
    finally:
        trace.restore()
        diagnostic['final_selection']=read(0x3d2f)[0]
        diagnostic['final_keys']=int.from_bytes(read(0x3d13,2),'little')
        if trace.row['snapshots']:
            last=trace.row['snapshots'][-1]
            diagnostic['observed_scans']=last.get('scans')
            diagnostic['observed_consumed']=last.get('consumed')
        save()
