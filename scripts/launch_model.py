"""Spawn the Windows local model server without inheriting console/pipe handles."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def model_command(root, port=None, gpu_layers=None):
    """One source of the already-validated server arguments, including legacy calls."""
    from urllib.parse import urlparse
    root = Path(root).resolve()
    lock = json.loads((root / "configs/model.lock.json").read_text(encoding="utf-8-sig"))
    config = json.loads((root / "configs/model.json").read_text(encoding="utf-8-sig"))
    selected_port = port if port is not None else urlparse(config["endpoint"]).port
    selected_gpu = gpu_layers if gpu_layers is not None else lock["gpu_layers"]
    return [str(root / lock["server_file"]), "-m", str(root / lock["model_file"]),
            "--host", "127.0.0.1", "--port", str(selected_port),
            "-c", str(lock["server_context_size"]), "-np", str(lock["parallel_slots"]),
            "-ngl", str(selected_gpu), "--jinja", "--reasoning", "off",
            "--no-context-shift", "--temp", str(config["temperature"]),
            "--top-p", str(config["top_p"]), "--repeat-penalty", str(config["repeat_penalty"]),
            "--alias", config["model"], "--no-webui"]


def spawn_model(root, log_dir, port=None, gpu_layers=None, log_prefix="llama"):
    root, log_dir = Path(root).resolve(), Path(log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    command = model_command(root, port, gpu_layers)
    env = os.environ.copy()
    env["LLAMA_ARG_CHAT_TEMPLATE_KWARGS"] = '{"enable_thinking":false}'
    with (log_dir / f"{log_prefix}.stdout.log").open("wb") as stdout, (log_dir / f"{log_prefix}.stderr.log").open("wb") as stderr:
        return subprocess.Popen(command, cwd=Path(command[0]).parent, env=env,
                                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                close_fds=True,
                                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--gpu-layers", type=int, default=99)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("This launcher has been validated on Windows only.")
    log_dir = ROOT / "results/environment"
    log_dir.mkdir(parents=True, exist_ok=True)
    process = spawn_model(ROOT, log_dir, args.port, args.gpu_layers)
    (log_dir / "model.pid").write_text(str(process.pid), encoding="ascii")
    print(process.pid)


if __name__ == "__main__":
    main()
