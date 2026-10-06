"""Start the local studio and GPU engine, then open the editing console."""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE="http://127.0.0.1:8190"
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))


def status():
    try:
        with opener.open(BASE+"/api/status",timeout=4) as response:
            return json.load(response)
    except (urllib.error.URLError,TimeoutError,ValueError):
        return None


def main():
    cache=ROOT/".cache"
    cache.mkdir(exist_ok=True)
    current=status()
    if current and current.get("app")!="AIMedia Studio":
        raise RuntimeError("Port 8190 is already used by another application")
    if not current:
        with (cache/"studio.stdout.log").open("ab") as out,(cache/"studio.stderr.log").open("ab") as err:
            process=subprocess.Popen([sys.executable,"-u",str(Path(__file__).with_name("server.py")),"--port","8190"],cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        (cache/"studio.pid").write_text(str(process.pid),encoding="utf-8")
        for _ in range(30):
            if status():
                break
            if process.poll() is not None:
                raise RuntimeError("Studio failed to start; check .cache/studio.stderr.log")
            time.sleep(.5)
        else:
            raise RuntimeError("Studio did not become ready; check .cache/studio.stderr.log")
    request=urllib.request.Request(BASE+"/api/engine/start",data=b"{}",headers={"Content-Type":"application/json","X-AIMedia-Client":"studio"})
    with opener.open(request,timeout=10) as response:
        json.load(response)
    webbrowser.open(BASE)
    print("AIMedia Studio: "+BASE)


if __name__=="__main__":
    try:
        main()
    except (RuntimeError,urllib.error.URLError) as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
