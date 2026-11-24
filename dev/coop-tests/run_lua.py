"""Runs a Lua test file under LuaJIT (the Lua the map server uses) without a luajit program: pip install lupa.

    python run_lua.py <test.lua> [arguments for the test...]

The test runs in a new empty scratch folder (the co-op tests write a few small files there) and its exit code is passed on.
"""
import os
import sys
import tempfile

from lupa import luajit21


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    script = os.path.abspath(argv[1])
    args = [os.path.abspath(a) if os.path.exists(a) else a for a in argv[2:]]
    lua = luajit21.LuaRuntime(unpack_returned_tuples=True)
    lua.execute("arg = {}")
    table = lua.globals().arg
    table[0] = script
    for number, value in enumerate(args, 1):
        table[number] = value
    with tempfile.TemporaryDirectory() as scratch:
        os.chdir(scratch)
        try:
            lua.execute("local f = assert(loadfile(arg[0])) f()")
        finally:
            os.chdir(os.path.dirname(script))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
