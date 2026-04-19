"""
First-boot setup portal for AI Scientists VM.

Runs on port 5001 before the main web UI. Presents a form for API key
configuration. After submission, writes keys to config/vm.env, creates
the sentinel file ~/.setup-complete, stops itself, and starts the main
services (sandbox-vm + ai-scientists-web).
"""

import os
import re
import subprocess
import sys

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

VM_ENV_PATH = os.path.expanduser("~/controllable-sandbox/config/vm.env")
SETUP_SENTINEL = os.path.expanduser("~/.setup-complete")


def _update_env_key(filepath: str, key: str, value: str) -> None:
    """Update a KEY=value line in the env file."""
    with open(filepath, "r") as f:
        content = f.read()
    pattern = rf"^{re.escape(key)}=.*$"
    replacement = f"{key}={value}"
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    with open(filepath, "w") as f:
        f.write(content)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/setup", methods=["POST"])
def setup():
    data = request.get_json()
    openai_key = (data.get("openai_api_key") or "").strip()
    firecrawl_key = (data.get("firecrawl_api_key") or "").strip()

    if not openai_key:
        return jsonify({"error": "OPENAI_API_KEY is required"}), 400

    # Basic format validation
    if not openai_key.startswith("sk-"):
        return jsonify({"error": "OPENAI_API_KEY should start with 'sk-'"}), 400

    try:
        _update_env_key(VM_ENV_PATH, "OPENAI_API_KEY", openai_key)
        if firecrawl_key:
            _update_env_key(VM_ENV_PATH, "FIRECRAWL_API_KEY", firecrawl_key)

        # Create sentinel to disable this portal on next boot
        open(SETUP_SENTINEL, "w").close()

        # Start the main services in background, then stop ourselves
        subprocess.Popen(
            [
                "bash", "-c",
                "sudo systemctl start sandbox-vm.service && "
                "sudo systemctl start ai-scientists-web.service && "
                "sleep 2 && "
                "sudo systemctl stop ai-scientists-setup.service"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return jsonify({
            "status": "ok",
            "message": "API keys saved. Starting AI Scientists Web UI... "
                       "The page will redirect in ~30 seconds."
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Check if setup already done
    if os.path.exists(SETUP_SENTINEL):
        print("Setup already completed. Exiting.")
        sys.exit(0)

    print("AI Scientists Setup Portal running at http://0.0.0.0:5001")
    print(f"Config file: {VM_ENV_PATH}")
    app.run(host="0.0.0.0", port=5001, debug=False)
