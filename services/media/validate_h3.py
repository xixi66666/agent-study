"""Generate a local H3 AV clip and verify its decoded video and audio streams."""

import argparse
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import av
import requests

ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_STATE = ROOT / ".cache/h3-download.json"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def build_prompt(config, prompt, run_id):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": config["diffusion_model"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": config["text_encoder"], "type": "minimax", "device": config["text_encoder_device"]}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": config["video_vae"]}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": config["audio_vae"]}},
        "5": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {"clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0], "prompt": prompt, "width": config["width"], "height": config["height"], "length": config["frames"], "ref_image_size": "match"}},
        "6": {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["5", 0]}},
        "7": {"class_type": "BasicScheduler", "inputs": {"model": ["1", 0], "scheduler": config["scheduler"], "steps": config["steps"], "denoise": 1.0}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": config["sampler"]}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": config["seed"]}},
        "10": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["9", 0], "guider": ["6", 0], "sampler": ["8", 0], "sigmas": ["7", 0], "latent_image": ["5", 1]}},
        "11": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["10", 0], "vae": ["3", 0], "tile_size": 256, "overlap": 64, "temporal_size": 32, "temporal_overlap": 8}},
        "12": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["10", 0], "vae": ["4", 0]}},
        "13": {"class_type": "CreateVideo", "inputs": {"images": ["11", 0], "fps": config["fps"], "audio": ["12", 0]}},
        "14": {"class_type": "SaveVideo", "inputs": {"video": ["13", 0], "filename_prefix": "video/" + run_id + "/h3_check", "format": "mp4", "format.codec": "h264", "format.codec.encoding": "auto"}},
    }


def installed_files():
    if not DOWNLOAD_STATE.exists():
        return False
    state = json.loads(DOWNLOAD_STATE.read_text(encoding="utf-8"))
    if state.get("status") == "failed":
        raise RuntimeError("H3 download failed; see .cache/h3-download.stderr.log")
    if state.get("status") != "complete":
        return False
    for entry in state["files"]:
        path = ROOT / "ComfyUI/models" / entry["file"]
        if entry["status"] != "verified" or not path.exists() or path.stat().st_size != entry["size"]:
            raise RuntimeError("H3 installation is incomplete: " + entry["file"])
    return True


def inspect_video(path, config):
    with av.open(str(path)) as container:
        video = container.streams.video[0]
        audio = container.streams.audio[0]
        specs = {"width": video.width, "height": video.height, "fps": float(video.average_rate),
                 "frames": video.frames, "audio_sample_rate": audio.rate,
                 "audio_channels": audio.channels, "duration_seconds": container.duration / av.time_base}
        decoded_video = sum(1 for _ in container.decode(video=0))
    with av.open(str(path)) as container:
        decoded_audio = sum(frame.samples for frame in container.decode(audio=0))
    if (specs["width"], specs["height"], specs["fps"], decoded_video) != (config["width"], config["height"], config["fps"], config["frames"]):
        raise RuntimeError("Unexpected H3 video dimensions, frame rate or frame count")
    if specs["audio_channels"] != 2 or decoded_audio <= 0:
        raise RuntimeError("H3 stereo audio is missing or cannot be decoded")
    specs.update(decoded_video_frames=decoded_video, decoded_audio_samples=decoded_audio)
    return specs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/h3_video.json")
    parser.add_argument("--prompt", type=Path, default=ROOT / "prompts/h3_install_check.txt")
    parser.add_argument("--wait-for-download", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    base = config["comfyui_url"].rstrip("/")
    if urlsplit(base).hostname not in ("localhost", "127.0.0.1", "::1"):
        parser.error("Only local ComfyUI is supported")
    prompt = args.prompt.read_text(encoding="utf-8").strip()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_h3_install_check")
    graph = build_prompt(config, prompt, run_id)
    if args.prepare_only:
        write_json(ROOT / "workflows/h3_int8_validation_api.json", graph)
        print("Prepared workflows/h3_int8_validation_api.json", flush=True)
        return
    deadline = time.monotonic() + config["timeout_seconds"]
    while not installed_files():
        if not args.wait_for_download:
            raise RuntimeError("Download H3 first with services/media/download_h3.py")
        if time.monotonic() > deadline:
            raise TimeoutError("Timed out waiting for H3 download")
        time.sleep(10)
    session = requests.Session()
    session.trust_env = False
    while True:
        response = session.get(base + "/queue", timeout=30)
        response.raise_for_status()
        queue = response.json()
        if not queue["queue_running"] and not queue["queue_pending"]:
            break
        if time.monotonic() > deadline:
            raise TimeoutError("ComfyUI queue remained busy")
        time.sleep(10)
    run = ROOT / "runs" / run_id
    for folder in ("prompts", "logs", "final"):
        (run / folder).mkdir(parents=True, exist_ok=True)
    manifest = {"run_id": run_id, "model": "MiniMax H3 Ref2VA INT8 ConvRot", "status": "submitting"}
    write_json(run / "config.json", config)
    write_json(run / "prompts/prompt_api.json", graph)
    (run / "prompts/prompt.txt").write_text(prompt, encoding="utf-8")
    write_json(run / "manifest.json", manifest)
    write_json(ROOT / ".cache/h3-validation.json", manifest)
    response = session.post(base + "/free", json={"unload_models": True, "free_memory": True}, timeout=30)
    response.raise_for_status()
    response = session.post(base + "/prompt", json={"prompt": graph}, timeout=90)
    if response.status_code != 200:
        write_json(run / "logs/rejected.json", response.json())
        raise RuntimeError("H3 workflow rejected; see run logs")
    prompt_id = response.json()["prompt_id"]
    started = time.monotonic()
    manifest.update(status="running", prompt_id=prompt_id)
    write_json(run / "manifest.json", manifest)
    write_json(ROOT / ".cache/h3-validation.json", manifest)
    print("H3 validation submitted: " + prompt_id, flush=True)
    while True:
        response = session.get(base + "/history/" + prompt_id, timeout=30)
        response.raise_for_status()
        history = response.json().get(prompt_id)
        if history is not None:
            break
        if time.monotonic() - started > config["timeout_seconds"]:
            raise TimeoutError("H3 generation did not finish within timeout")
        time.sleep(5)
    write_json(run / "logs/history.json", history)
    if history["status"]["status_str"] != "success":
        manifest.update(status="failed", elapsed_seconds=round(time.monotonic() - started, 2))
        write_json(run / "manifest.json", manifest)
        write_json(ROOT / ".cache/h3-validation.json", manifest)
        raise RuntimeError("H3 generation failed; see " + str(run / "logs/history.json"))
    outputs = history["outputs"]["14"]
    video = next(item for item in outputs.get("images", outputs.get("videos", [])) if item["filename"].endswith(".mp4"))
    output_root = (ROOT / "ComfyUI/output").resolve()
    source = (output_root / video.get("subfolder", "") / video["filename"]).resolve()
    if not source.is_relative_to(output_root):
        raise RuntimeError("Unexpected ComfyUI output path")
    destination = run / "final/h3_check.mp4"
    shutil.copyfile(source, destination)
    specs = inspect_video(destination, config)
    manifest.update(status="success", elapsed_seconds=round(time.monotonic() - started, 2),
                    output=str(destination.relative_to(ROOT)), specs=specs)
    write_json(run / "manifest.json", manifest)
    write_json(ROOT / ".cache/h3-validation.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        state_path = ROOT / ".cache/h3-validation.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        state.update(status="failed", error=type(error).__name__)
        write_json(state_path, state)
        if state.get("run_id"):
            manifest = ROOT / "runs" / state["run_id"] / "manifest.json"
            if manifest.exists():
                write_json(manifest, state)
        raise
