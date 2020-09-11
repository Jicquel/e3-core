import ast
import logging
import os
import sys

import e3.env
import e3.fs
import e3.os.fs
import e3.os.process
import e3.sys
from e3.sys import RewriteImportNodeTransformer, RewriteImportRule, RewriteNodeError

import pytest


def test_filtering_import():
    script = """
import a, b, c
import a1, b, c
import a2, a3
from d import l1, l2, c3
from foo.bar.module import name1, name2, name3
from foo.bar2.module import name1, name2, name3
from foo.bar2.module import name2
from foo.bar2.module3 import name1
"""

    node = ast.parse(script, "<string>")
    node = RewriteImportNodeTransformer(
        [
            RewriteImportRule("b"),
            RewriteImportRule("a"),
            RewriteImportRule(".*3"),
            RewriteImportRule(r".*\.bar\..*", "name2"),
        ]
    ).visit(node)

    expected = "Module(body=["

    expected += "Import(names=[alias(name='c', asname=None)]),"
    # import a, b, c
    # b and a skipped

    expected += (
        " Import(names=[alias(name='a1', asname=None),"
        " alias(name='c', asname=None)]),"
    )
    # import a1, b, c => a1, c  -- b is skipped

    expected += " Import(names=[alias(name='a2', asname=None)]),"
    # import a2, a3 => a2 -- a3 is skipped (.*3)

    expected += (
        " ImportFrom(module='d',"
        " names=[alias(name='l1', asname=None),"
        " alias(name='l2', asname=None),"
        " alias(name='c3', asname=None)], level=0),"
    )
    # from d import l1, l2, c3 - not modified

    expected += (
        " ImportFrom(module='foo.bar.module',"
        " names=[alias(name='name1', asname=None),"
        " alias(name='name3', asname=None)], level=0),"
    )
    # from foo.bar.module import name1, name2, name3
    # .*\.bar\..* name2 -> name2 is skipped

    expected += (
        " ImportFrom(module='foo.bar2.module',"
        " names=[alias(name='name1', asname=None), "
        "alias(name='name2', asname=None), "
        "alias(name='name3', asname=None)], level=0),"
    )
    # from foo.bar2.module import name1, name2, name3 - not modifed

    expected += (
        " ImportFrom(module='foo.bar2.module',"
        " names=[alias(name='name2', asname=None)], level=0),"
    )
    # from foo.bar2.module import name2 - not modified

    expected += " ImportFrom(module='foo.bar2.module3'," " names=[], level=0)])"
    # from foo.bar2.module3 import name1 -- module matching .*3

    ast_dump = ast.dump(node)
    # Make the test compatible with Python 3.8
    ast_dump = ast_dump.replace(", type_ignores=[]", "")
    assert ast_dump == expected

    node2 = ast.parse(script, "<string>")
    with pytest.raises(RewriteNodeError) as err:
        RewriteImportNodeTransformer(
            [
                RewriteImportRule("a", action=RewriteImportRule.RuleAction.reject),
                RewriteImportRule("b"),
                RewriteImportRule(".*3"),
                RewriteImportRule(r".*\.bar\..*", "name2"),
            ]
        ).visit(node2)

    # verify that import a is rejected
    assert (
        "Import(names=[alias(name='a', asname=None),"
        " alias(name='b', asname=None),"
        " alias(name='c', asname=None)])" in str(err.value)
    )

    node3 = ast.parse(script, "<string>")
    with pytest.raises(RewriteNodeError) as err3:
        RewriteImportNodeTransformer(
            [
                RewriteImportRule("a"),
                RewriteImportRule("b"),
                RewriteImportRule(".*3"),
                RewriteImportRule(
                    r".*\.bar\..*", "name2", action=RewriteImportRule.RuleAction.reject
                ),
            ]
        ).visit(node3)
    # verify that from foo.bar.module import name2 is rejected
    assert "module='foo.bar." in str(err3.value)


def test_python_func():
    e3.sys.set_python_env("/foo")
    if sys.platform == "win32":
        assert "/foo" in os.environ["PATH"].split(os.pathsep)
        assert [e3.os.fs.unixpath(p) for p in e3.sys.python_script("run", "/foo")] == [
            "/foo/python.exe",
            "/foo/Scripts/run",
        ]
        assert [e3.os.fs.unixpath(p) for p in e3.sys.python_script("run")][
            0
        ] == e3.os.fs.unixpath(sys.executable)

        e3.fs.mkdir("Scripts")
        e3.os.fs.touch("Scripts/run.exe")
        assert e3.os.fs.unixpath(
            e3.sys.python_script("run.exe", os.getcwd())[0]
        ) == e3.os.fs.unixpath(os.path.join(os.getcwd(), "Scripts", "run.exe"))
        assert e3.os.fs.unixpath(
            e3.sys.python_script("run", os.getcwd())[0]
        ) == e3.os.fs.unixpath(os.path.join(os.getcwd(), "Scripts", "run.exe"))
    else:
        assert "/foo/bin" in os.environ["PATH"].split(os.pathsep)
        assert e3.sys.python_script("run", "/foo") == [
            "/foo/bin/python",
            "/foo/bin/run",
        ]

    assert e3.os.fs.unixpath(
        os.path.dirname(e3.sys.python_script("run")[0])
    ) == e3.os.fs.unixpath(os.path.dirname(sys.executable))
    assert e3.os.fs.unixpath(e3.sys.interpreter()) == e3.os.fs.unixpath(sys.executable)

    # Check support for python3
    if sys.platform == "win32":
        e3.os.fs.touch("python3.exe")
        assert e3.sys.interpreter(os.getcwd()) == os.path.join(
            os.getcwd(), "python3.exe"
        )
    else:
        e3.fs.mkdir("bin")
        e3.os.fs.touch(os.path.join("bin", "python3"))
        assert e3.sys.interpreter(os.getcwd()) == os.path.join(
            os.getcwd(), "bin", "python3"
        )


@pytest.mark.xfail(
    os.environ.get("TRAVIS", "") == "true", reason="Test not working on travis"
)
def test_relocate_python_distrib():
    env = e3.env.Env()

    # Create a venv and add pip manually to ensure no upgrade is done.
    p = e3.os.process.Run(
        [sys.executable, "-m", "venv", "--without-pip", "--copies", "my_env"]
    )
    assert p.status == 0, f"output was:\n{p.out}"

    p = e3.os.process.Run([e3.sys.interpreter("./my_env"), "-m", "ensurepip"])
    assert p.status == 0, f"output was:\n{p.out}"

    # Move the venv and check that calling a script inside it will
    # result in a failure as absolute location to Python interpreter will
    # be wrong
    e3.fs.mv("my_env", "moved_env")
    logging.info(e3.fs.ls("./moved_env/*/*"))

    if sys.platform == "win32":
        script = "./Scripts/pip3.exe"
    else:
        script = "./bin/pip3"

    try:
        p = e3.os.process.Run([os.path.join("./moved_env", script), "--help"])
        # On Windows we will get a status != 0 in case of error
        assert p.status != 0
    except FileNotFoundError:
        # On Unixes we get an exception (interpreter not found)
        pass

    # Apply relocation on the venv and freeze the interpreter
    e3.sys.relocate_python_distrib(
        python_distrib_dir=os.path.abspath("./moved_env"), freeze=True
    )
    p = e3.os.process.Run([os.path.join("./moved_env", script), "--help"])
    assert p.status == 0

    # Move the environment, relocate it but make it relocatable this time.
    e3.fs.mv("moved_env", "moved_env2")
    logging.info("Make venv non location specific")
    e3.sys.relocate_python_distrib(python_distrib_dir=os.path.abspath("./moved_env2"))

    # Moving the venv should result in a working environment providing PATH is
    # set correctly
    e3.fs.mv("moved_env2", "moved_env3")
    env.add_path(os.path.abspath(os.path.join("moved_env3", "bin")))
    env.add_path(os.path.abspath(os.path.join("moved_env3", "Scripts")))
    env.add_path(os.path.abspath("moved_env3"))

    p = e3.os.process.Run([os.path.join("moved_env3", script), "--help"])
    assert p.status == 0, f"output was:\n{p.out}"
