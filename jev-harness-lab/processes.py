"""Bounded subprocesses on macOS/Linux, including spawned child processes."""
import os
import signal
import subprocess


def run_process(argv, *, timeout, input=None, **kwargs):
    if os.name != "posix":
        raise OSError("This lab's process-group limits require macOS or Linux")
    process = subprocess.Popen(argv, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=True, **kwargs)
    def kill_group():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill adapter/check and descendants in its session, not only the direct child.
        kill_group()
        process.communicate(timeout=2)
        raise
    finally:
        # A successful adapter can still leave a child with redirected stdio alive.
        # Such a child must not mutate the project after evidence has been collected.
        kill_group()
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
