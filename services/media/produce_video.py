"""Generate local Wan clips and assemble a video, retaining each run's inputs and outputs."""

import argparse
import hashlib
import json
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlsplit

import av
import requests

ROOT = Path(__file__).resolve().parents[2]
CAMERA_MOTIONS = ("Static", "Pan Up", "Pan Down", "Pan Left", "Pan Right", "Zoom In", "Zoom Out", "Anti Clockwise (ACW)", "ClockWise (CW)")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_prompt(config, story, shot, index, run_id, start_image=None):
    if config.get("generation_mode") == "h3":
        from h3_video import build_h3_prompt
        return build_h3_prompt(config, story, shot, index, run_id, [start_image] if start_image else [])
    directions = "\nScene direction: " + shot.get("description", "") + "\nCamera direction: " + shot.get("camera", "")
    characters = "\n".join(name + ": " + speaker["appearance"] for name, speaker in story.get("speakers", {}).items() if speaker.get("appearance"))
    graph = {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": config["diffusion_model"], "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": config["text_encoder"], "type": "wan", "device": "cpu"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": config["vae"]}},
        "48": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["37", 0], "shift": config["shift"]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": story["style"] + " " + shot["prompt"] + directions + ("\nCharacters: " + characters if characters else "")}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": story["negative_prompt"]}},
        "55": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["39", 0], "width": config["width"], "height": config["height"], "length": config["frames"], "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"model": ["48", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["55", 0], "seed": shot.get("seed", config["seed"] + index), "steps": config["steps"], "cfg": config["cfg"], "sampler_name": config["sampler"], "scheduler": config["scheduler"], "denoise": 1}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "57": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": config["fps"]}},
        "58": {"class_type": "SaveVideo", "inputs": {"video": ["57", 0], "filename_prefix": f"video/{run_id}/shot_{index:02d}", "format": "mp4", "format.codec": "h264", "format.codec.encoding": "auto"}},
    }
    if start_image:
        graph["56"] = {"class_type": "LoadImage", "inputs": {"image": start_image}}
        graph["55"]["inputs"]["start_image"] = ["56", 0]
    if config.get("generation_mode", "wan22") == "fun_camera":
        if not start_image:
            raise ValueError("Fun Camera 运镜模式需要起始参考图，请选择图片或接续上一镜头末帧")
        graph["60"] = {"class_type": "WanCameraEmbedding", "inputs": {"camera_pose": shot.get("camera_motion", "Static"), "speed": shot.get("camera_speed", 1.0), "width": config["width"], "height": config["height"], "length": config["frames"]}}
        graph["61"] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": config["clip_vision"]}}
        graph["62"] = {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["61", 0], "image": ["56", 0], "crop": "center"}}
        graph["55"] = {"class_type": "WanCameraImageToVideo", "inputs": {"positive": ["6", 0], "negative": ["7", 0], "vae": ["39", 0], "width": config["width"], "height": config["height"], "length": config["frames"], "batch_size": 1, "start_image": ["56", 0], "clip_vision_output": ["62", 0], "camera_conditions": ["60", 0]}}
        graph["3"]["inputs"].update(positive=["55", 0], negative=["55", 1], latent_image=["55", 2])
    return graph


def wait_for_result(session, base, prompt_id, timeout):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        response = session.get(f"{base}/history/{prompt_id}", timeout=30)
        response.raise_for_status()
        history = response.json()
        if prompt_id in history:
            return history[prompt_id]
        time.sleep(5)
    raise TimeoutError(f"Task {prompt_id} is still unresolved; resume this run to check it before generating again")


def inspect_clip(path, reference=None):
    with av.open(str(path)) as container:
        video = container.streams.video[0]
        count = 0
        last = None
        for frame in container.decode(video=0):
            count += 1
            last = frame
        if last is None:
            raise RuntimeError(f"Video contains no decodable frames: {path.name}")
        if reference:
            last.to_image().save(reference)
        return {"width": video.width, "height": video.height, "fps": float(video.average_rate), "frames": count, "duration_seconds": count / float(video.average_rate), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def concatenate(clips, target, fps, frames_per_clip=None):
    with av.open(str(clips[0])) as source:
        width, height = source.streams.video[0].width, source.streams.video[0].height
    with av.open(str(target), "w", options={"movflags": "+faststart"}) as output:
        stream = output.add_stream("libx264", rate=fps)
        stream.width, stream.height = width, height
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": "18", "preset": "medium"}
        position = 0
        for clip in clips:
            with av.open(str(clip)) as source:
                video = source.streams.video[0]
                if (video.width, video.height) != (width, height) or video.average_rate != fps:
                    raise RuntimeError(f"Clip specifications differ: {clip.name}")
                for clip_position, frame in enumerate(source.decode(video=0)):
                    if frames_per_clip is not None and clip_position >= frames_per_clip:
                        break
                    frame.pts = position
                    frame.time_base = Fraction(1, fps)
                    position += 1
                    for packet in stream.encode(frame):
                        output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/local_video.json")
    parser.add_argument("--retry-failed", action="store_true", help="Resubmit known failed shots after inspecting and correcting their error")
    parser.add_argument("--run-id", default=datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.run_id):
        parser.error("run-id must contain only letters, numbers, underscores, or hyphens")
    config, story = read_json(args.config.resolve()), read_json(args.storyboard.resolve())
    base = config["comfyui_url"].rstrip("/")
    if urlsplit(base).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("This producer only calls a local ComfyUI instance")
    if not story["shots"]:
        parser.error("The storyboard must contain at least one shot")
    run = ROOT / "runs" / args.run_id
    for folder in ("clips", "references", "prompts", "final", "logs"):
        (run / folder).mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(json.dumps({"config": config, "story": story}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    manifest_path = run / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if manifest["input_fingerprint"] != fingerprint:
            parser.error("This run has different inputs; use a new run-id")
    else:
        manifest = {"run_id": args.run_id, "title": story["title"], "input_fingerprint": fingerprint, "status": "generating", "shots": [{} for shot in story["shots"]]}
        write_json(manifest_path, manifest)
        write_json(run / "storyboard.json", story)
        write_json(run / "config.json", config)
        has_dialogue = any(shot.get("dialogue") for shot in story["shots"])
        script = [f"# {story['title']}", "", story["synopsis"], "", "对白配音和字幕在画面生成后合成。" if has_dialogue else "无对白；本次仅生成画面。", ""]
        for index, shot in enumerate(story["shots"], 1):
            script.extend([f"## 镜头 {index:02d}：{shot['title']}（约 {config['frames'] / config['fps']:.1f} 秒）", "", shot["description"], "", "镜头：" + shot["camera"], ""])
            for line in shot.get("dialogue", []):
                script.extend([f"{line['speaker']}：{line['text']}", ""])
        (run / "script.md").write_text("\n".join(script), encoding="utf-8")
    with requests.Session() as session:
        session.trust_env = False
        for index, shot in enumerate(story["shots"], 1):
            entry = manifest["shots"][index - 1]
            if entry.get("status") == "failed" and args.retry_failed:
                attempt = {key: value for key, value in entry.items() if key != "previous_attempts"}
                attempts = entry.setdefault("previous_attempts", [])
                attempts.append(attempt)
                history_path = run / "logs" / f"shot_{index:02d}_history.json"
                if history_path.exists():
                    shutil.copyfile(history_path, run / "logs" / f"shot_{index:02d}_attempt_{len(attempts):02d}_history.json")
                entry.pop("prompt_id", None)
                entry["status"] = "pending"
                manifest["status"] = "generating"
                write_json(manifest_path, manifest)
            clip = run / "clips" / f"shot_{index:02d}.mp4"
            reference = run / "references" / f"shot_{index:02d}_last.png"
            if entry.get("status") == "success" and clip.exists() and reference.exists():
                if hashlib.sha256(clip.read_bytes()).hexdigest() != entry["specs"]["sha256"]:
                    raise RuntimeError(f"Saved clip changed: {clip.name}")
                print(f"Reusing shot {index:02d}", flush=True)
                continue
            if entry.get("status") == "submitting" and not entry.get("prompt_id"):
                raise RuntimeError(f"Shot {index:02d} has an unknown submission result; inspect the ComfyUI queue before retrying")
            if not entry.get("prompt_id"):
                start_image = None
                reference_path = shot.get("start_image")
                if reference_path or (index > 1 and config["use_previous_frame"]):
                    previous = (ROOT / reference_path).resolve() if reference_path else run / "references" / f"shot_{index - 1:02d}_last.png"
                    if not previous.is_relative_to(ROOT):
                        raise RuntimeError("Reference image must be inside the project")
                    with previous.open("rb") as image:
                        response = session.post(base + "/upload/image", files={"image": (previous.name, image, "image/png")}, data={"subfolder": args.run_id, "type": "input"}, timeout=30)
                    response.raise_for_status()
                    uploaded = response.json()
                    start_image = "/".join(filter(None, [uploaded.get("subfolder"), uploaded["name"]]))
                graph = build_prompt(config, story, shot, index, args.run_id, start_image)
                write_json(run / "prompts" / f"shot_{index:02d}.json", graph)
                entry.update({"title": shot["title"], "status": "submitting"})
                write_json(manifest_path, manifest)
                response = session.post(base + "/prompt", json={"prompt": graph}, timeout=30)
                if response.status_code != 200:
                    entry["status"] = "rejected"
                    write_json(run / "logs" / f"shot_{index:02d}_rejected.json", response.json())
                    write_json(manifest_path, manifest)
                    response.raise_for_status()
                entry.update({"prompt_id": response.json()["prompt_id"], "status": "running", "started_at": datetime.now(timezone.utc).isoformat()})
                write_json(manifest_path, manifest)
            print(f"Generating shot {index:02d}/{len(story['shots'])}: {shot['title']}; prompt_id={entry['prompt_id']}", flush=True)
            result = wait_for_result(session, base, entry["prompt_id"], config["clip_timeout_seconds"])
            write_json(run / "logs" / f"shot_{index:02d}_history.json", result)
            if result.get("status", {}).get("status_str") != "success":
                entry["status"] = "failed"
                manifest["status"] = "failed"
                write_json(manifest_path, manifest)
                raise RuntimeError(f"Shot {index:02d} failed; inspect its saved history before retrying")
            saved = result["outputs"]["58"]
            items = saved.get("images", saved.get("videos", []))
            video = next(item for item in items if item["filename"].endswith(".mp4"))
            output_root = (ROOT / "ComfyUI/output").resolve()
            source = (output_root / video.get("subfolder", "") / video["filename"]).resolve()
            if not source.is_relative_to(output_root):
                raise RuntimeError("Unexpected ComfyUI output path")
            shutil.copyfile(source, clip)
            specs = inspect_clip(clip, reference)
            if (specs["width"], specs["height"], specs["frames"], specs["fps"]) != (config["width"], config["height"], config["frames"], config["fps"]):
                raise RuntimeError(f"Shot {index:02d} has unexpected video specifications")
            entry.update({"status": "success", "clip": str(clip.relative_to(run)), "reference": str(reference.relative_to(run)), "specs": specs, "completed_at": datetime.now(timezone.utc).isoformat()})
            write_json(manifest_path, manifest)
            print(f"Saved shot {index:02d}: {specs['duration_seconds']:.2f}s", flush=True)
    target = run / "final" / "film.mp4"
    print("Assembling final film", flush=True)
    concatenate([run / "clips" / f"shot_{index:02d}.mp4" for index in range(1, len(story["shots"]) + 1)], target, config["fps"], config.get("output_frames_per_clip"))
    manifest.update({"status": "complete", "final": "final/film.mp4", "final_specs": inspect_clip(target)})
    write_json(manifest_path, manifest)
    print(f"Completed: {target}; {manifest['final_specs']['duration_seconds']:.2f}s", flush=True)


if __name__ == "__main__":
    main()
