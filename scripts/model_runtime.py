"""Capture the running local server version, template, and effective properties."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

import model_health

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    model_health.PORT = args.port
    lock = json.loads((ROOT / "configs/model.lock.json").read_text(encoding="utf-8"))
    props = model_health.request("/props")
    version = subprocess.run([str(ROOT / lock["server_file"]), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    template = props.get("chat_template", "")
    result = {"captured_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "backend_type":"local_llama_cpp", "version_stdout":version.stdout, "version_stderr":version.stderr, "version_exit_code":version.returncode, "template_sha256":hashlib.sha256(template.encode()).hexdigest(), "properties":props}
    evidence = ROOT / "results/environment"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "model_runtime.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (evidence / "chat_template.jinja").write_text(template,encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "properties"},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
