"""Leave stderr unread until producers finish: a blocked terminal must not stall enqueue."""
import pathlib
import queue
import subprocess
import sys
import tempfile
import threading

with tempfile.TemporaryDirectory(prefix='amw log pressure ') as temp:
    p = subprocess.Popen([sys.argv[1], '--backpressure', str(pathlib.Path(temp) / 'log.xml')],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    messages = queue.Queue()
    reader = threading.Thread(target=lambda: messages.put(p.stdout.readline()), daemon=True)
    reader.start()
    try:
        ready = messages.get(timeout=15)
        assert ready.startswith('READY '), ready
        dropped = int(ready.split()[1])
        assert dropped > 0, 'expected bounded queue overflow with stderr blocked'
        reader.join()
        _, stderr = p.communicate(timeout=15)
        assert p.returncode == 0, (p.returncode, stderr[-1000:])
        assert '[INFO] [pressure]' in stderr
        print('BACKPRESSURE_PASS dropped=' + str(dropped))
    finally:
        if p.poll() is None:
            p.kill()
            p.communicate()

# Close the read end immediately; the logger must count failures and preserve App liveness.
with tempfile.TemporaryDirectory(prefix='amw log broken ') as temp:
    p = subprocess.Popen([sys.argv[1], '--broken-pipe', str(pathlib.Path(temp) / 'log.xml')],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    p.stderr.close()
    try:
        p.wait(timeout=15)
        output = p.stdout.read()
        assert p.returncode == 0 and 'BROKEN_PIPE_PASS' in output, (p.returncode, output)
        print(output.strip())
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
