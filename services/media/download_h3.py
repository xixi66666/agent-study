"""Download the H3 INT8 profile from ModelScope, with resume and SHA256 checks."""

import hashlib
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
REPO = "Comfy-Org/MiniMax-H3"
FILES = [
    "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
    "vae/minimax_h3_video_vae_fp16.safetensors",
    "vae/minimax_h3_audio_vae_fp32.safetensors",
]
STATE = ROOT / ".cache/h3-download.json"
STATE_LOCK = threading.Lock()


def save_state(progress):
    with STATE_LOCK:
        temporary = STATE.with_suffix(".tmp")
        temporary.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(STATE)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    STATE.parent.mkdir(exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    response = session.get("https://modelscope.cn/api/v1/models/" + REPO + "/repo/files",
                           params={"Recursive": "true", "Revision": "master"}, timeout=45)
    response.raise_for_status()
    metadata = {item["Path"]: item for item in response.json()["Data"]["Files"]}
    progress = {"repository": REPO, "revision": "master", "status": "downloading", "files": []}
    for source in FILES:
        expected = metadata[source]
        if not expected.get("Sha256") or expected["Size"] <= 0:
            raise RuntimeError("ModelScope checksum or size missing: " + source)
        progress["files"].append({"file": source, "size": expected["Size"],
                                  "sha256": expected["Sha256"], "downloaded": 0, "status": "pending"})
    save_state(progress)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(download_file, entry, progress) for entry in progress["files"]]
        for future in futures:
            future.result()
    progress["status"] = "complete"
    save_state(progress)
    print("H3 INT8 model files ready", flush=True)


def download_file(entry, progress):
    session = requests.Session()
    session.trust_env = False
    source = entry["file"]
    target = ROOT / "ComfyUI/models" / source
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    if target.exists():
        if target.stat().st_size != entry["size"] or sha256(target) != entry["sha256"]:
            raise RuntimeError("Existing model checksum mismatch: " + source)
        entry.update(status="verified", downloaded=entry["size"])
        save_state(progress)
        return
    entry["status"] = "downloading"
    for attempt in range(8):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == entry["size"]:
            break
        if offset > entry["size"]:
            raise RuntimeError("Partial file larger than expected: " + source)
        try:
            url = "https://modelscope.cn/models/" + REPO + "/resolve/master/" + source + "?download=true"
            with session.get(url, headers={"Range": f"bytes={offset}-"} if offset else {},
                             stream=True, timeout=(45, 90)) as response:
                response.raise_for_status()
                if offset and response.status_code == 206:
                    if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise RuntimeError("Unexpected resume range: " + source)
                elif offset:
                    offset = 0
                last_report = 0
                with partial.open("ab" if offset else "wb") as output:
                    for chunk in response.iter_content(4 * 1024 * 1024):
                        output.write(chunk)
                        offset += len(chunk)
                        if time.monotonic() - last_report >= 10:
                            entry["downloaded"] = offset
                            save_state(progress)
                            print(f"{source}: {offset / 1024**3:.2f}/{entry['size'] / 1024**3:.2f} GiB", flush=True)
                            last_report = time.monotonic()
            if partial.stat().st_size != entry["size"]:
                raise RuntimeError("Incomplete download: " + source)
            break
        except (requests.RequestException, RuntimeError):
            if attempt == 7:
                raise
            time.sleep(min(2 ** attempt, 30))
    entry["status"] = "verifying"
    entry["downloaded"] = partial.stat().st_size
    save_state(progress)
    if sha256(partial) != entry["sha256"]:
        raise RuntimeError("Downloaded model checksum mismatch: " + source)
    partial.replace(target)
    entry.update(status="verified", downloaded=entry["size"])
    save_state(progress)
    print("Verified: " + source, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        current = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
        current.update(status="failed", error=type(error).__name__)
        save_state(current)
        raise
