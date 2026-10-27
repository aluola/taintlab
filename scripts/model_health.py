"""Read only loopback model health; optional one true local structured-generation probe."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PORT = 8080


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Local model health requests must not follow redirects")


def request(path, data=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}" + path, data=None if data is None else json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=90) as res:
        return json.load(res)


def main():
    global PORT
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    PORT = args.port
    result = {"health": request("/health"), "models": request("/v1/models"), "backend_type": "local_llama_cpp"}
    if args.smoke:
        schema = {"type":"object","properties":{"type":{"type":"string","enum":["tool_call"]},"tool":{"type":"string","enum":["read_document"]},"arguments":{"type":"object","properties":{"doc_id":{"type":"string"}},"required":["doc_id"],"additionalProperties":False}},"required":["type","tool","arguments"],"additionalProperties":False}
        start = time.perf_counter()
        response = request("/v1/chat/completions", {"model":"qwen3-0.6b", "messages":[{"role":"system","content":"You propose exactly one JSON action. read_document requires doc_id. Do not invent a result."},{"role":"user","content":"Read document meeting."}],"max_tokens":512,"temperature":0.2,"top_p":0.9,"repeat_penalty":1.0,"seed":17,"response_format":{"type":"json_schema","json_schema":{"name":"action","strict":True,"schema":schema}}})
        result.update({"elapsed_seconds":time.perf_counter()-start,"response":response,"parsed_action":json.loads(response["choices"][0]["message"]["content"])})
    evidence = ROOT / "results/environment"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / ("model_smoke.json" if args.smoke else "model_health.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
