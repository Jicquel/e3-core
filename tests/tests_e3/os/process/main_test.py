import e3.fs
import e3.os.fs
import e3.os.process
import os
import pytest
import tempfile
import sys


def test_run_shebang():
    """Verify that the parse shebang option works."""
    tempd = tempfile.mkdtemp(prefix='test_e3_os_process')
    try:
        prog_filename = os.path.join(tempd, 'prog')
        with open(prog_filename, 'wb') as f:
            f.write(b'#!/usr/bin/env python\n')
            f.write(b'print("running python prog")\n')
        e3.os.fs.chmod('a+x', prog_filename)
        p = e3.os.process.Run([prog_filename], parse_shebang=True)
        assert p.out == 'running python prog\n'
    finally:
        e3.fs.rm(tempd, True)


def test_rlimit():
    """rlimit kill the child process after a timeout."""
    p = e3.os.process.Run(
        [sys.executable, '-c',
         "print('hello'); import sys; sys.stdout.flush(); "
         "import time; time.sleep(10); print('world')"],
        timeout=1)
    assert 'hello' in p.out
    assert 'world' not in p.out


def test_not_found():
    with pytest.raises(OSError) as err:
        e3.os.process.Run(['e3-bin-not-found'])
        assert 'e3-bin-not-found not found' in err

    with pytest.raises(OSError) as err:
        e3.os.process.Run([[sys.executable, '-c', 'pass'],
                           ['e3-bin-not-found2']])
        assert 'e3-bin-not-found2 not found' in err


@pytest.mark.skipif(sys.platform != 'win32', reason="windows specific test")
def test_invalid_executable():
    p = os.path.join(os.path.dirname(__file__), 'invalid.exe')
    with pytest.raises(WindowsError):
        e3.os.process.Run([p])


def test_enable_commands_handler():
    tempd = tempfile.mkdtemp()
    try:
        log_file = os.path.join(tempd, 'cmds.log')
        h = e3.os.process.enable_commands_handler(log_file)
        try:
            e3.os.process.Run([sys.executable, '-c', 'print "dummy"'])
            e3.os.process.Run([sys.executable, '-c', 'print "dummy2"'])
        finally:
            e3.os.process.disable_commands_handler(h)

        with open(log_file, 'rb') as fd:
            lines = fd.read().splitlines()
        assert len(lines) == 2

    finally:
        e3.fs.rm(tempd, True)


def test_wait_for_processes():
    p1 = e3.os.process.Run([sys.executable, '-c',
                            'import time; time.sleep(3); print "process1"'],
                           bg=True)
    p2 = e3.os.process.Run([sys.executable, '-c',
                            'import time; time.sleep(4); print "process2"'],
                           bg=True)

    process_list = [p1, p2]
    result = e3.os.process.wait_for_processes(process_list, 0)
    del process_list[result]
    e3.os.process.wait_for_processes(process_list, 0)

    assert p1.status == 0
    assert p1.out.strip() == 'process1'
    assert p2.status == 0
    assert p2.out.strip() == 'process2'


def test_run_pipe():
    p = e3.os.process.Run(
        [[sys.executable, '-c', 'print "dummy"'],
         [sys.executable, '-c',
          'import sys; print sys.stdin.read().replace("y", "ies")']])
    assert p.status == 0
    assert p.out.strip() == 'dummies'


def test_command_line_image():
    result = e3.os.process.command_line_image(["echo", ""])
    assert result == "echo ''"
    result = e3.os.process.command_line_image([["echo", "dummy"],
                                               ["grep", "m"]])
    assert result == "echo dummy | grep m"


def test_poll():
    import time
    result = e3.os.process.Run(
        [sys.executable, '-c',
         'import time; time.sleep(1); print "process"'], bg=True)

    assert result.poll() is None
    time.sleep(2)
    assert result.poll() == 0
    assert result.out.strip() == 'process'

    # check that subsequent calls to poll or wait do not crash or alter the
    # result
    assert result.poll() == 0
    assert result.wait() == 0
    assert result.out.strip() == 'process'


def test_file_redirection():
    tempd = tempfile.mkdtemp()
    try:
        p_out = os.path.join(tempd, 'p.out')
        result = e3.os.process.Run(
            [sys.executable, '-c', 'print "dummy"'],
            input=None,
            output=p_out,
            error=e3.os.process.STDOUT)
        with open(p_out, 'rb') as fd:
            content = fd.read().strip()
        assert result.status == 0
        assert content == 'dummy'
    finally:
        e3.fs.rm(tempd, True)


def test_output_append():
    tempd = tempfile.mkdtemp()
    try:
        p_out = os.path.join(tempd, 'p.out')
        e3.os.process.Run([sys.executable, '-c', 'print "line1"'],
                          output=p_out)
        e3.os.process.Run([sys.executable, '-c', 'print "line2"'],
                          output="+" + p_out)
        with open(p_out, 'r') as fd:
            content = fd.read().strip()
        assert content == "line1\nline2"
    finally:
        e3.fs.rm(tempd, True)


def test_pipe_input():
    p = e3.os.process.Run([sys.executable,
                           '-c',
                           'import sys; print sys.stdin.read()'],
                          input='|dummy')
    assert p.out.strip() == 'dummy'
