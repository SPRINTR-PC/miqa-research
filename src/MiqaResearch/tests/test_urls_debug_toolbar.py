import os
import subprocess
import sys


def test_manage_py_check_succeeds_with_debug_false():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {
        **os.environ,
        "MIRES_DEBUG": "False",
        "MIRES_ALLOWED_HOSTS": "testserver",
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=base_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
