"""Dependency-free interactive evaluator for the SDK with local Ollama."""
from __future__ import annotations
import argparse, json, os, queue, sys, urllib.request, uuid
from typing import Any
from .runtime import Runtime

def _ollama(base: str, model: str, request: dict[str, Any]) -> dict[str, Any]:
    messages=request.get("payload",{}).get("messages",[])
    body=json.dumps({"model":model,"messages":messages,"stream":False}).encode()
    req=urllib.request.Request(base.rstrip("/")+"/api/chat",data=body,headers={"content-type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=300) as response: data=json.load(response)
    except Exception: return {"ok":False,"error":{"code":"model_unavailable","message":"model unavailable"}}
    content=str(data.get("message",{}).get("content", ""))
    return {"ok":True,"result":{"chunks":[{"type":"content_delta","delta":content}],"completion":{"content":content,"tool_calls":[],"finish_reason":"stop","usage":{"input_tokens":int(data.get("prompt_eval_count",0) or 0),"output_tokens":int(data.get("eval_count",0) or 0)}}}}

def main(argv: list[str]|None=None)->int:
    p=argparse.ArgumentParser(description="Evaluate NoteMeld Agent SDK with local Ollama")
    p.add_argument("--model",default=os.environ.get("NOTEMELD_OLLAMA_MODEL","qwen3:4b")); p.add_argument("--ollama-url",default=os.environ.get("OLLAMA_URL","http://127.0.0.1:11434")); p.add_argument("--library",default=os.environ.get("NOTEMELD_AGENT_SDK_LIBRARY")); args=p.parse_args(argv)
    history=[]; model=args.model
    def driver(req): return _ollama(args.ollama_url,model,req)
    try:
        with Runtime(args.library,driver=driver) as runtime:
            print(f"agent sdk / ollama ({model}) — /model NAME, /new, /exit",file=sys.stderr)
            while True:
                try: line=input("agent> ").strip()
                except EOFError: break
                if not line: continue
                if line=="/exit": break
                if line=="/new": history=[]; print("new session",file=sys.stderr); continue
                if line.startswith("/model "): model=line.split(None,1)[1]; print(f"model: {model}",file=sys.stderr); continue
                request={"schema_version":"1","request_id":str(uuid.uuid4()),"session_id":"ollama-cli","input":{"text":line,"attachments":[],"context_refs":[]},"model_override":None,"approval_mode":"interactive","history":history}
                token=runtime.submit_turn(request); runtime.wait(token,300_000)
                while True:
                    try: event=runtime.events.get_nowait()
                    except queue.Empty: break
                    print(json.dumps(event,ensure_ascii=False),file=sys.stderr)
                    if event.get("type")=="message.delta": print(event.get("payload",{}).get("delta",""),end="",flush=True)
                    if event.get("type")=="turn.succeeded": print()
                history.extend([{"role":"user","content":line}])
        return 0
    except Exception as exc: print(f"agent sdk error: {exc}",file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())
