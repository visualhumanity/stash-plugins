import json
import os
import shutil
import subprocess

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "vhPlayerAspectRatioFix")
PLUGIN_JS = os.path.abspath(os.path.join(PLUGIN_DIR, "vhPlayerAspectRatioFix.js"))


def run_plugin(expression, payload=None):
    """Load the plugin script in Node as `plugin` and return the JSON value of `expression`.

    `input` inside the expression is `payload`, passed through JSON.
    """
    node = shutil.which("node")
    if node is None:
        raise AssertionError("node is required to run the vhPlayerAspectRatioFix tests")
    script = (
        "const plugin = require(process.argv[1]);"
        "const input = JSON.parse(process.argv[2]);"
        f"process.stdout.write(JSON.stringify({expression}));"
    )
    out = subprocess.run(
        [node, "-e", script, PLUGIN_JS, json.dumps(payload)], check=True, capture_output=True, text=True
    )
    return json.loads(out.stdout)
