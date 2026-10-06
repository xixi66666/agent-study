"""Local AIMedia editing console. Reuses the existing Wan and MiMo media pipeline."""

import argparse
import asyncio
import copy
import hashlib
import io
import json
import mimetypes
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
WEB = Path(__file__).with_name("web")
sys.path.insert(0, str(ROOT / "services/media"))
from produce_video import CAMERA_MOTIONS, build_prompt, concatenate, inspect_clip, read_json, write_json
from add_dialogue import load_key, render, synthesize
from h3_video import build_h3_prompt, compose_native


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def clean_error(error):
    return re.sub(r"sk-[A-Za-z0-9_-]{12,}|Bearer\s+\S+", "<REDACTED>", str(error))[:800]


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise web.HTTPBadRequest(text="名称只能包含英文字母、数字、下划线和短横线")
    return value


def local_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise web.HTTPBadRequest(text="ComfyUI 地址必须是本机 HTTP 服务，例如 http://127.0.0.1:8189")
    try:
        parsed.port
    except ValueError:
        raise web.HTTPBadRequest(text="ComfyUI 端口无效") from None
    return value.rstrip("/")


class Studio:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.workspace = self.root / "workspace"
        for folder in ("projects", "assets", "jobs"):
            (self.workspace / folder).mkdir(parents=True, exist_ok=True)
        self.jobs = {}
        self.tasks = {}
        self.stops = {}
        self.session = None
        self.engine_process = None
        for file in (self.workspace / "jobs").glob("*.json"):
            job = read_json(file)
            if job["status"] in ("running", "queued", "stopping"):
                job.update(status="interrupted", stage="操作台上次退出，点击继续任务恢复", updated_at=now())
                write_json(file, job)
            self.jobs[job["id"]] = job

    def project_path(self, project_id):
        return self.workspace / "projects" / valid_id(project_id) / "project.json"

    def project(self, project_id):
        path = self.project_path(project_id)
        if not path.exists():
            raise web.HTTPNotFound(text="项目不存在")
        return read_json(path)

    def run_path(self, run_id):
        return self.root / "runs" / valid_id(run_id)

    def media_path(self, relative):
        path = (self.root / relative).resolve()
        roots = [self.root / "runs", self.root / "prompts/assets", self.workspace / "assets"]
        if not any(path.is_relative_to(item.resolve()) for item in roots) or path.suffix.lower() not in (".mp4", ".png", ".jpg", ".jpeg", ".webp", ".wav", ".mp3", ".srt"):
            raise web.HTTPForbidden(text="该文件不属于可访问的媒体目录")
        if not path.is_file():
            raise web.HTTPNotFound(text="媒体文件不存在")
        return path

    def validate(self, payload):
        story, config, tts = payload["story"], payload["video"], payload["tts"]
        if set(story)-{"title","synopsis","style","negative_prompt","speakers","shots","references"}:
            raise web.HTTPBadRequest(text="剧本包含未知字段，请使用操作台导出的分镜结构")
        def text(value, name, limit=16000, required=False):
            if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
                raise web.HTTPBadRequest(text=f"{name}为空或超出长度限制")
        text(story["title"], "标题", 120, True)
        text(story["synopsis"], "故事梗概")
        text(story["style"], "全局画面风格")
        text(story["negative_prompt"], "负面提示词")
        if not isinstance(story["shots"], list) or not 1 <= len(story["shots"]) <= 100:
            raise web.HTTPBadRequest(text="分镜数量应为 1～100")
        if not isinstance(story.get("speakers", {}), dict) or len(story.get("speakers", {})) > 20:
            raise web.HTTPBadRequest(text="角色数量超出限制")
        for name, speaker in story.get("speakers", {}).items():
            if set(speaker)-{"voice","style","appearance"}:
                raise web.HTTPBadRequest(text="角色设定包含未知字段")
            text(name, "角色名", 40, True)
            if name in ("__proto__","constructor","prototype"):
                raise web.HTTPBadRequest(text="这个角色名属于保留名称")
            text(speaker["voice"], "音色", 80, True)
            text(speaker["style"], "朗读风格", 2000)
            text(speaker.get("appearance",""),"角色外观",2000)
        for shot_index, shot in enumerate(story["shots"]):
            if set(shot)-{"title","description","camera","prompt","dialogue","start_image","seed","camera_motion","camera_speed","reference_shots"}:
                raise web.HTTPBadRequest(text="分镜包含未知字段")
            refs = shot.get("reference_shots", [])
            if not isinstance(refs, list) or len(refs) > 1 or any(type(i) is not int or not 1 <= i <= shot_index for i in refs):
                raise web.HTTPBadRequest(text="人物参考镜头必须指向一个已经生成的前序镜头")
            if shot.get("camera_motion", "Static") not in CAMERA_MOTIONS:
                raise web.HTTPBadRequest(text="运镜预设无效，请从相机运动列表选择")
            speed = shot.get("camera_speed", 1.0)
            if type(speed) not in (int, float) or not math.isfinite(speed) or not 0 <= speed <= 10:
                raise web.HTTPBadRequest(text="运镜速度需为 0～10 的有限数字")
            if "seed" in shot and (type(shot["seed"]) is not int or not 0 <= shot["seed"] <= 2**32-1):
                raise web.HTTPBadRequest(text="镜头种子需为 0～4294967295 的整数")
            for field in ("title", "description", "camera", "prompt"):
                text(shot[field], f"分镜 {field}", required=field in ("title", "prompt"))
            if shot.get("start_image"):
                self.media_path(shot["start_image"])
                if Path(shot["start_image"]).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                    raise web.HTTPBadRequest(text="参考素材必须是图片")
            if len(shot.get("dialogue", [])) > 10:
                raise web.HTTPBadRequest(text="单镜头对白不应超过十句")
            for line in shot.get("dialogue", []):
                if set(line)!={"speaker","text"}:
                    raise web.HTTPBadRequest(text="对白只需要角色和文本")
                if line["speaker"] not in story.get("speakers", {}):
                    raise web.HTTPBadRequest(text="对白使用了不存在的角色")
                text(line["text"], "对白", 500, True)
        required = set(read_json(self.root / "config/cat_comic_video.json"))
        if not required <= set(config) or set(config)-required-{"generation_mode", "clip_vision", "audio_vae", "text_encoder_device"}:
            raise web.HTTPBadRequest(text="视频参数字段不完整或包含未知字段")
        if config.get("generation_mode", "wan22") not in ("wan22", "fun_camera", "h3"):
            raise web.HTTPBadRequest(text="生成模式无效")
        h3 = config.get("generation_mode") == "h3"
        if h3:
            profile = read_json(self.root / "config/h3_studio_video.json")
            if any(config.get(field) != profile[field] for field in ("diffusion_model", "text_encoder", "vae", "audio_vae", "sampler", "scheduler")) or config.get("text_encoder_device") not in ("cpu", "default"):
                raise web.HTTPBadRequest(text="H3 请使用已安装的配套模型、双 VAE 和采样器")
            if config["fps"] != 24 or config["frames"] % 17 != 5 or not 124 <= config["frames"] <= 362 or config["width"] % 32 or config["height"] % 32:
                raise web.HTTPBadRequest(text="H3 固定 24fps，宽高需为 32 的倍数，帧数为 17n+5（124～362）")
        if config.get("generation_mode") == "fun_camera":
            profile = read_json(self.root / "config/fun_camera_video.json")
            if any(config.get(field) != profile[field] for field in ("diffusion_model", "vae", "clip_vision")):
                raise web.HTTPBadRequest(text="Fun Camera 需要配套的相机主模型、Wan2.1 VAE 和图像编码器，请重新选择运镜模式")
        config["comfyui_url"] = local_url(config["comfyui_url"])
        for field, low, high in (("width", 128, 1280), ("height", 128, 1280), ("frames", 5, 481), ("output_frames_per_clip", 1, 480), ("fps", 12, 60), ("steps", 1, 60), ("seed", 0, 2**32-101), ("clip_timeout_seconds", 60, 7200)):
            if type(config[field]) is not int or not low <= config[field] <= high:
                raise web.HTTPBadRequest(text=f"视频参数 {field} 超出可用范围")
        if config["width"] % 16 or config["height"] % 16 or (not h3 and config["frames"] % 4 != 1) or config["output_frames_per_clip"] >= config["frames"]:
            raise web.HTTPBadRequest(text="宽高需为 16 的倍数，生成帧数需为 4n+1，保留帧数应小于生成帧数")
        for field in ("cfg", "shift"):
            if type(config[field]) not in (int, float) or not 0.1 <= config[field] <= 20:
                raise web.HTTPBadRequest(text=f"{field} 超出范围")
        if type(config["use_previous_frame"]) is not bool:
            raise web.HTTPBadRequest(text="镜头连续性参数无效")
        for field in ("diffusion_model", "text_encoder", "vae", "sampler", "scheduler"):
            text(config[field], field, 200, True)
        if set(tts) != set(read_json(self.root / "config/mimo_tts.json")):
            raise web.HTTPBadRequest(text="配音字幕参数字段不完整或包含未知字段")
        if tts["endpoint"] != "https://api.xiaomimimo.com/v1/chat/completions" or tts["model"] != "mimo-v2.5-tts" or tts["sample_rate"] != 24000:
            raise web.HTTPBadRequest(text="当前操作台使用官方 MiMo TTS 服务和 24kHz 音轨")
        for field, low, high in (("subtitle_font_size", 16, 56), ("subtitle_band_height", 80, config["height"]//2), ("subtitle_title_font_size", 14, 36), ("timeout_seconds", 30, 300)):
            if type(tts[field]) is not int or not low <= tts[field] <= high:
                raise web.HTTPBadRequest(text=f"字幕或配音参数 {field} 超出范围")
        if tts["subtitle_font"] not in ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"):
            raise web.HTTPBadRequest(text="请选择已安装的微软雅黑字体")
        if type(tts["dialogue_start_offset_seconds"]) not in (int, float) or not 0 <= tts["dialogue_start_offset_seconds"] < config["output_frames_per_clip"] / config["fps"]:
            raise web.HTTPBadRequest(text="对白起始偏移需小于镜头时长")
        return payload

    def create_project(self, story, config, tts, base_run=None):
        project_id = uuid.uuid4().hex[:12]
        project = {"id": project_id, "story": copy.deepcopy(story), "video": copy.deepcopy(config), "tts": copy.deepcopy(tts), "revision": 1, "created_at": now(), "updated_at": now(), "base_run": base_run, "latest_run": None}
        self.validate(project)
        path = self.project_path(project_id)
        path.parent.mkdir(parents=True)
        write_json(path, project)
        return project

    def initialize(self):
        if any((self.workspace / "projects").glob("*/project.json")):
            return
        for run in sorted((self.root / "runs").glob("*")):
            if not (run / "storyboard.json").exists() or not (run / "config.json").exists():
                continue
            config = read_json(run / "config.json")
            config.setdefault("output_frames_per_clip", config["frames"] - 1)
            self.create_project(read_json(run / "storyboard.json"), config, read_json(self.root / "config/mimo_tts.json"), run.name)
        if not any((self.workspace / "projects").glob("*/project.json")):
            self.create_project(read_json(self.root / "prompts/stories/cat_biscuit_mystery.json"), read_json(self.root / "config/h3_studio_video.json"), read_json(self.root / "config/mimo_tts.json"))

    def list_projects(self):
        batches = {path.parent.name: read_json(path) for path in (self.root / "runs").glob("*/manifest.json")}
        result = []
        for path in (self.workspace / "projects").glob("*/project.json"):
            project = read_json(path)
            run_id = project["latest_run"] or project["base_run"]
            run = self.run_path(run_id) if run_id else None
            manifest = batches.get(run_id, {})
            completed = sum(entry.get("status") == "success" for entry in manifest.get("shots", []))
            final = next((str(file.relative_to(self.root)).replace("\\", "/") for file in (run / "final/film_with_dialogue.mp4", run / "final/film.mp4") if file.exists()), None) if run else None
            audio_ready = bool(run and (run / "audio/dialogue.wav").exists())
            cover = run / "references/shot_01_last.png" if run else None
            cover = str(cover.relative_to(self.root)).replace("\\", "/") if cover and cover.exists() else project["story"]["shots"][0].get("start_image")
            changed = False
            if run and (run / "storyboard.json").exists():
                previous_video = read_json(run / "config.json")
                previous_video.setdefault("output_frames_per_clip", previous_video["frames"] - 1)
                changed = project["story"] != read_json(run / "storyboard.json") or project["video"] != previous_video
                if (run / "tts.json").exists():
                    changed = changed or project["tts"] != read_json(run / "tts.json")
            jobs = sorted([job for job in self.jobs.values() if job["project_id"] == project["id"]], key=lambda job: job["created_at"], reverse=True)
            active = next((job for job in jobs if job["status"] in ("running", "queued", "stopping")), None)
            latest = next((job for job in jobs if job["action"] != "audition"), None)
            stage = "complete" if final else "audio_ready" if audio_ready else "visual_ready" if completed == len(project["story"]["shots"]) else "draft"
            if changed:
                stage = "changed"
            if latest and latest["status"] in ("failed", "interrupted", "stopped"):
                stage = "attention"
            if active:
                stage = "rendering"
            result.append({"id": project["id"], "title": project["story"]["title"], "synopsis": project["story"]["synopsis"], "shots": len(project["story"]["shots"]), "duration": len(project["story"]["shots"])*project["video"]["output_frames_per_clip"]/project["video"]["fps"], "updated_at": project["updated_at"], "run_id": run_id, "stage": stage, "completed_shots": completed, "cover": cover, "final": final, "audio_ready": audio_ready, "draft_changed": changed, "revision": project["revision"], "versions": sum(name == project["base_run"] or item.get("studio_project") == project["id"] for name, item in batches.items()), "active_job": active["id"] if active else None})
        return sorted(result, key=lambda item: item["updated_at"], reverse=True)

    def assets(self):
        return [{"path": str(path.relative_to(self.root)).replace("\\", "/"), "name": path.name} for folder in (self.root / "prompts/assets", self.workspace / "assets") for path in sorted(folder.glob("*")) if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]

    def run_info(self, run_id):
        if not run_id:
            return None
        run = self.run_path(run_id)
        if not (run / "manifest.json").exists():
            return None
        manifest = read_json(run / "manifest.json")
        def relative(path):
            return str(path.relative_to(self.root)).replace("\\", "/") if path.exists() else None
        shots = []
        for index, entry in enumerate(manifest["shots"], 1):
            shots.append({"index": index, "status": entry.get("status", "pending"), "clip": relative(run / "clips" / f"shot_{index:02d}.mp4"), "image": relative(run / "references" / f"shot_{index:02d}_last.png"), "specs": entry.get("specs"), "reused": entry.get("reused_from")})
        final = relative(run / "final/film_with_dialogue.mp4") or relative(run / "final/film.mp4")
        cues = read_json(run / "subtitles/timeline.json") if (run / "subtitles/timeline.json").exists() else []
        lines = read_json(run/"audio/manifest.json").get("lines",[]) if (run/"audio/manifest.json").exists() else []
        audio_lines = [{"speaker":line["speaker"],"text":line["text"],"audio":relative(run/"audio"/f"line_{index:02d}.wav"),"duration":line.get("duration_seconds")} for index,line in enumerate(lines,1)]
        return {"id": run_id, "status": manifest["status"], "shots": shots, "final": final, "voiced": bool(relative(run / "final/film_with_dialogue.mp4")), "specs": manifest.get("postproduction", {}).get("final_specs", manifest.get("final_specs")), "audio": relative(run / "audio/dialogue.wav"), "subtitles": relative(run / "subtitles/dialogue.srt"), "cues": cues, "audio_lines":audio_lines, "source_revision": manifest.get("studio_revision"), "story": read_json(run / "storyboard.json"),"video":read_json(run/"config.json")}

    def save_job(self, job):
        job["updated_at"] = now()
        write_json(self.workspace / "jobs" / (job["id"] + ".json"), job)

    def log(self, job, message):
        job.setdefault("logs", []).append({"time": now(), "message": clean_error(message)})
        job["logs"] = job["logs"][-150:]
        self.save_job(job)

    def visual_signature(self, config, story, index):
        visual = {key: value for key, value in config.items() if key not in ("comfyui_url", "clip_timeout_seconds", "output_frames_per_clip","seed","text_encoder_device")}
        visual["generation_mode"] = config.get("generation_mode", "wan22")
        if visual["generation_mode"] == "wan22":
            visual.pop("clip_vision", None)
        shot = story["shots"][index]
        if visual["generation_mode"] == "h3":
            visual["native_dialogue"] = shot.get("dialogue", [])
            visual["reference_shots"] = [{"index": ref, "shot": story["shots"][ref-1]} for ref in shot.get("reference_shots", [])]
        if visual["generation_mode"] == "fun_camera":
            visual.update(camera_motion=shot.get("camera_motion", "Static"), camera_speed=float(shot.get("camera_speed", 1.0)))
        reference = shot.get("start_image")
        image_hash = hashlib.sha256(self.media_path(reference).read_bytes()).hexdigest() if reference else None
        return fingerprint({"config": visual, "index": index, "seed":shot.get("seed",config["seed"]+index+1),"style": story["style"], "negative": story["negative_prompt"], "prompt": shot["prompt"],"description":shot.get("description",""),"camera":shot.get("camera",""),"characters":{name:speaker["appearance"] for name,speaker in story.get("speakers",{}).items() if speaker.get("appearance")}, "reference": reference, "image_hash": image_hash})

    def camera_status(self):
        profile = read_json(self.root / "config/fun_camera_video.json")
        missing = [profile[field] for field, folder in (("diffusion_model", "diffusion_models"), ("vae", "vae"), ("clip_vision", "clip_vision"), ("text_encoder", "text_encoders")) if not (self.root / "ComfyUI/models" / folder / profile[field]).is_file()]
        result = {"ready": not missing, "missing": missing}
        progress = self.root / ".cache/fun-camera-download.json"
        if progress.exists():
            download = read_json(progress)
            result.update(download_status=download["status"], downloaded_bytes=sum(item.get("downloaded", 0) for item in download["files"]), total_bytes=sum(item["size"] for item in download["files"]))
        return result

    def h3_status(self):
        profile = read_json(self.root / "config/h3_studio_video.json")
        missing = [profile[field] for field, folder in (("diffusion_model", "diffusion_models"), ("text_encoder", "text_encoders"), ("vae", "vae"), ("audio_vae", "vae")) if not (self.root / "ComfyUI/models" / folder / profile[field]).is_file()]
        return {"ready": not missing, "missing": missing}

    def prepare_run(self, project, action, selected):
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_studio_" + uuid.uuid4().hex[:6]
        run = self.run_path(run_id)
        for folder in ("clips", "references", "prompts", "final", "logs", "audio", "subtitles"):
            (run / folder).mkdir(parents=True)
        story, config = copy.deepcopy(project["story"]), copy.deepcopy(project["video"])
        if action == "audition":
            story["shots"] = [story["shots"][selected-1]]
        write_json(run / "storyboard.json", story)
        write_json(run / "config.json", config)
        write_json(run / "tts.json", project["tts"])
        manifest = {"run_id": run_id, "title": story["title"], "input_fingerprint": fingerprint({"config":config,"story":story}), "status": "pending", "studio_project": project["id"], "studio_revision": project["revision"], "shots": [{} for _ in story["shots"]]}
        source_id = project["latest_run"] or project["base_run"]
        source = self.run_path(source_id) if source_id else None
        if source and (source / "manifest.json").exists() and action != "plan":
            previous = read_json(source / "manifest.json")
            old_story, old_config = read_json(source / "storyboard.json"), read_json(source / "config.json")
            old_config.setdefault("output_frames_per_clip", old_config["frames"] - 1)
            invalid_previous = False
            if action != "audition":
                for index, shot in enumerate(story["shots"]):
                    direction = source / "prompts" / f"shot_{index+1:02d}_direction.json"
                    if direction.is_file():
                        shutil.copy2(direction, run / "prompts" / direction.name)
                    forced = action == "shot" and index == selected-1 or action == "from_shot" and index >= selected-1
                    explicit = bool(shot.get("start_image")) or config.get("generation_mode") == "h3" and bool(shot.get("reference_shots"))
                    same = index < len(old_story["shots"]) and self.visual_signature(config, story, index) == self.visual_signature(old_config, old_story, index)
                    changed_reference = any(not manifest["shots"][ref-1].get("status") == "success" or manifest["shots"][ref-1].get("reused_from") is None for ref in shot.get("reference_shots", []))
                    can_reuse = same and not forced and not changed_reference and not (config["use_previous_frame"] and invalid_previous and not explicit)
                    entry = previous["shots"][index] if index < len(previous["shots"]) else {}
                    clip, reference = source / "clips" / f"shot_{index+1:02d}.mp4", source / "references" / f"shot_{index+1:02d}_last.png"
                    if can_reuse and entry.get("status") == "success" and clip.exists() and reference.exists():
                        if hashlib.sha256(clip.read_bytes()).hexdigest() != entry["specs"]["sha256"]:
                            raise web.HTTPConflict(text="来源镜头文件已被修改，校验失败")
                        for folder, filename in (("clips",clip.name),("references",reference.name),("prompts",f"shot_{index+1:02d}.json"),("logs",f"shot_{index+1:02d}_history.json")):
                            if (source/folder/filename).exists():
                                shutil.copy2(source/folder/filename, run/folder/filename)
                        manifest["shots"][index] = {**copy.deepcopy(entry), "reused_from": source_id}
                        invalid_previous = False
                    else:
                        invalid_previous = True
                if action == "shot":
                    # Explicit single-shot rework keeps later completed shots for comparison.
                    for index in range(selected, min(len(story["shots"]), len(previous["shots"]))):
                        entry = previous["shots"][index]
                        if not manifest["shots"][index] and entry.get("status") == "success" and self.visual_signature(config, story, index) == self.visual_signature(old_config, old_story, index):
                            for folder, name in (("clips",f"shot_{index+1:02d}.mp4"),("references",f"shot_{index+1:02d}_last.png")):
                                if (source/folder/name).exists():
                                    shutil.copy2(source/folder/name, run/folder/name)
                            if (run/"clips"/f"shot_{index+1:02d}.mp4").exists() and (run/"references"/f"shot_{index+1:02d}_last.png").exists():
                                manifest["shots"][index] = {**copy.deepcopy(entry), "reused_from": source_id, "kept_after_rework":True}
            old_audio_path = source / "audio/manifest.json"
            if old_audio_path.exists():
                old_audio = read_json(old_audio_path)
                old_speakers = old_story.get("speakers", {})
                available = {}
                for entry in old_audio["lines"]:
                    name = entry["speaker"]
                    signature = fingerprint([name, entry["text"], entry["voice"], old_speakers.get(name, {}).get("style", "")])
                    available[signature] = entry
                lines = []
                for shot in story["shots"]:
                    for line in shot.get("dialogue", []):
                        speaker = story["speakers"][line["speaker"]]
                        signature = fingerprint([line["speaker"],line["text"],speaker["voice"],speaker["style"]])
                        entry = available.get(signature)
                        cached = source/"audio"/f"line_{old_audio['lines'].index(entry)+1:02d}_original.wav" if entry else None
                        valid = entry and cached.exists() and entry.get("original_sha256") == hashlib.sha256(cached.read_bytes()).hexdigest() and old_audio["model"] == project["tts"]["model"]
                        lines.append(copy.deepcopy(entry) if valid else {"speaker":line["speaker"],"text":line["text"],"voice":speaker["voice"]})
                        if valid:
                            shutil.copy2(cached, run/"audio"/f"line_{len(lines):02d}_original.wav")
                duration = config["output_frames_per_clip"] / config["fps"]
                write_json(run/"audio/manifest.json", {"input_fingerprint":fingerprint({"story":story,"tts":project["tts"],"shot_duration":duration}),"model":project["tts"]["model"],"status":"pending","lines":lines,"reused_from":source_id})
        write_json(run / "manifest.json", manifest)
        script = ["# " + story["title"], "", story["synopsis"], ""]
        for index, shot in enumerate(story["shots"], 1):
            script.extend([f"## {index:02d} · {shot['title']}", shot["description"], "镜头："+shot["camera"]])
            script.extend(line["speaker"]+"："+line["text"] for line in shot.get("dialogue", []))
            script.append("")
        (run/"script.md").write_text("\n".join(script), encoding="utf-8")
        return run

    async def comfy(self, base, route, method="GET", **kwargs):
        async with self.session.request(method, base + route, timeout=aiohttp.ClientTimeout(total=30), **kwargs) as response:
            data = await response.json()
            if response.status != 200:
                raise RuntimeError(f"ComfyUI 返回 HTTP {response.status}：工作流或模型参数未通过校验")
            return data

    async def observe(self, job, base):
        h3 = read_json(self.run_path(job["run_id"]) / "config.json").get("generation_mode") == "h3"
        stages = ({"2":"加载文本编码器", "5":"编码提示词与参考素材", "10":"视频与声音采样",
                   "11":"解码画面", "12":"解码声音", "13":"合并画面与声音", "58":"保存镜头"} if h3 else
                  {"38":"编码提示词","6":"编码提示词","7":"编码提示词","60":"准备相机轨迹","61":"加载图像编码器","62":"编码参考图","55":"准备视频条件","3":"视频采样","8":"解码画面","58":"保存镜头"})
        try:
            async with self.session.ws_connect(base + "/ws?clientId=" + job["id"], heartbeat=20) as socket:
                async for message in socket:
                    if message.type != aiohttp.WSMsgType.TEXT:
                        continue
                    event = message.json()
                    data = event.get("data", {})
                    if event.get("type") == "progress":
                        job["sampling"] = {"value":data.get("value",0),"max":data.get("max",1)}
                    elif event.get("type") == "executing" and data.get("node"):
                        job["stage"] = stages.get(str(data["node"]), "准备模型")
                        if str(data["node"]) != ("10" if h3 else "3"):
                            job.pop("sampling", None)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass

    async def generate(self, job, run, story, config, manifest):
        base = local_url(config["comfyui_url"])
        selected = range(1,len(story["shots"])+1) if job["action"] not in ("shot", "from_shot") else [job["selected"]] if job["action"] == "shot" else range(job["selected"],len(story["shots"])+1)
        for index in selected:
            self.check_stop(job)
            shot, entry = story["shots"][index-1], manifest["shots"][index-1]
            if entry.get("status") == "success":
                self.log(job, f"复用镜头 {index:02d} · {shot['title']}")
                continue
            job.update(shot=index, stage="准备镜头", sampling=None)
            if not entry.get("prompt_id"):
                start_image = None
                reference = self.media_path(shot["start_image"]) if shot.get("start_image") else None
                if not reference and config.get("generation_mode") == "h3" and shot.get("reference_shots"):
                    reference = run / "references" / f"shot_{shot['reference_shots'][0]:02d}_last.png"
                if not reference and index > 1 and config["use_previous_frame"]:
                    reference = run / "references" / f"shot_{index-1:02d}_last.png"
                if reference:
                    if not reference.exists():
                        raise RuntimeError(f"镜头 {index} 需要上一镜头的末帧，请先生成前一镜头或选择参考图")
                    form = aiohttp.FormData()
                    form.add_field("image", reference.read_bytes(), filename=reference.name, content_type=mimetypes.guess_type(reference.name)[0] or "image/png")
                    form.add_field("subfolder", run.name)
                    form.add_field("type", "input")
                    uploaded = await self.comfy(base, "/upload/image", "POST", data=form)
                    start_image = "/".join(filter(None,[uploaded.get("subfolder"),uploaded["name"]]))
                if config.get("generation_mode") == "h3":
                    self.log(job, f"准备镜头 {index:02d} 的英文画面指令，中文仅用于对白")
                    graph = await asyncio.to_thread(build_prompt, config, story, shot, index, run.name, start_image)
                else:
                    graph = build_prompt(config, story, shot, index, run.name, start_image)
                self.check_stop(job)
                write_json(run / "prompts" / f"shot_{index:02d}.json", graph)
                entry.update(title=shot["title"],status="submitting",prompt_id=str(uuid.uuid4()),started_at=now())
                write_json(run / "manifest.json", manifest)
                result = await self.comfy(base, "/prompt", "POST", json={"prompt":graph,"prompt_id":entry["prompt_id"],"client_id":job["id"]})
                entry["prompt_id"] = result["prompt_id"]
                entry["status"] = "running"
                write_json(run/"manifest.json",manifest)
                self.log(job, f"提交镜头 {index:02d} · {shot['title']}")
            started = time.monotonic()
            while True:
                self.check_stop(job)
                history = await self.comfy(base, "/history/" + entry["prompt_id"])
                if entry["prompt_id"] in history:
                    result = history[entry["prompt_id"]]
                    break
                if time.monotonic()-started > config["clip_timeout_seconds"]:
                    raise TimeoutError("等待镜头超时，任务 ID 已保存；继续任务会先检查结果")
                await asyncio.sleep(2)
            write_json(run/"logs"/f"shot_{index:02d}_history.json",result)
            if result.get("status",{}).get("status_str") != "success":
                entry["status"] = "failed"
                write_json(run/"manifest.json",manifest)
                error = next((message[1] for message in reversed(result.get("status", {}).get("messages", [])) if message[0] == "execution_error"), {})
                detail = clean_error(error.get("exception_message", "请检查任务日志后重做该镜头")).strip()
                raise RuntimeError(f"镜头 {index} 生成失败 · {error.get('node_type', 'ComfyUI')}：{detail}")
            saved = result["outputs"]["58"]
            output = next(item for item in saved.get("images",saved.get("videos",[])) if item["filename"].endswith(".mp4"))
            output_root = (self.root/"ComfyUI/output").resolve()
            source = (output_root / output.get("subfolder","") / output["filename"]).resolve()
            if not source.is_relative_to(output_root):
                raise RuntimeError("ComfyUI 返回了无效的文件路径")
            clip, reference = run/"clips"/f"shot_{index:02d}.mp4", run/"references"/f"shot_{index:02d}_last.png"
            shutil.copy2(source,clip)
            specs = await asyncio.to_thread(inspect_clip,clip,reference)
            if (specs["width"],specs["height"],specs["frames"],specs["fps"]) != (config["width"],config["height"],config["frames"],config["fps"]):
                raise RuntimeError("生成镜头规格与设置不一致")
            entry.update(status="success",clip=str(clip.relative_to(run)),reference=str(reference.relative_to(run)),specs=specs,completed_at=now())
            write_json(run/"manifest.json",manifest)
            self.log(job, f"镜头 {index:02d} 已完成")

    def check_stop(self, job):
        if self.stops[job["id"]].is_set():
            raise RuntimeError("任务已停止")

    async def execute(self, job):
        if job["action"] == "plan":
            await self.execute_plan(job)
            return
        run = self.run_path(job["run_id"])
        story, config, tts = read_json(run/"storyboard.json"), read_json(run/"config.json"), read_json(run/"tts.json")
        manifest = read_json(run/"manifest.json")
        observer = None
        try:
            job.update(status="running",stage="准备任务")
            manifest["status"] = "generating"
            write_json(run/"manifest.json",manifest)
            self.save_job(job)
            action = job["action"]
            if action in ("film","generate","shot","from_shot"):
                observer = asyncio.create_task(self.observe(job,local_url(config["comfyui_url"])))
                await self.generate(job,run,story,config,manifest)
            self.check_stop(job)
            all_ready = all(entry.get("status") == "success" for entry in manifest["shots"])
            if action in ("film","compose","generate") and all_ready:
                job["stage"] = "拼接画面"
                self.log(job,"拼接已完成的镜头")
                target = run/"final/film.mp4"
                await asyncio.to_thread(concatenate,[run/"clips"/f"shot_{i:02d}.mp4" for i in range(1,len(story["shots"])+1)],target,config["fps"],config["output_frames_per_clip"])
                manifest.update(status="complete",final="final/film.mp4",final_specs=await asyncio.to_thread(inspect_clip,target))
                write_json(run/"manifest.json",manifest)
            elif action in ("film","compose"):
                raise RuntimeError("部分镜头尚未生成，请先补齐画面")
            else:
                manifest["status"] = "clips_ready" if all_ready else "partial"
                write_json(run/"manifest.json",manifest)
            has_dialogue = any(shot.get("dialogue") for shot in story["shots"])
            if config.get("generation_mode") == "h3" and action in ("film", "compose") and all_ready:
                self.log(job, "保留 H3 原生对白与立体声，烧录中文字幕")
                specs = await asyncio.to_thread(compose_native, run, story, config, tts)
                manifest["postproduction"] = {"status":"complete", "final":"final/film_with_dialogue.mp4", "final_specs":specs, "audio_manifest":"audio/manifest.json", "subtitles":"subtitles/dialogue.srt"}
                write_json(run/"manifest.json", manifest)
            elif action in ("film","compose","voice","audition") and has_dialogue:
                def progress(index,line):
                    job.update(stage=f"处理配音 {index:02d} · {line['speaker']}",audio_line=index)
                audio, cues, audio_manifest = await asyncio.to_thread(synthesize,run,story,config,tts,cancel_requested=self.stops[job["id"]].is_set,progress_callback=progress)
                self.check_stop(job)
                if action in ("film","compose"):
                    job["stage"] = "合成配音与字幕"
                    self.log(job,"烧录中文字幕并合成音轨")
                    target = run/"final/film_with_dialogue.mp4"
                    await asyncio.to_thread(render,run/"final/film.mp4",target,audio,cues,tts,config["fps"],story["title"])
                    specs = await asyncio.to_thread(inspect_clip,target)
                    audio_manifest.update(status="complete",final="final/film_with_dialogue.mp4",final_specs=specs)
                    write_json(run/"audio/manifest.json",audio_manifest)
                    manifest["postproduction"] = {"status":"complete","final":"final/film_with_dialogue.mp4","final_specs":specs,"audio_manifest":"audio/manifest.json","subtitles":"subtitles/dialogue.srt"}
                    write_json(run/"manifest.json",manifest)
            self.check_stop(job)
            job.update(status="complete",stage="已完成",finished_at=now())
            self.log(job,"任务完成，素材已保存到独立批次")
        except Exception as error:
            stopped = self.stops[job["id"]].is_set()
            for entry in manifest["shots"]:
                if entry.get("prompt_id") in job.get("cancelled_prompts",[]):
                    entry["status"]="cancelled"
            job.update(status="stopped" if stopped else "failed",stage="已停止" if stopped else "任务失败",error=None if stopped else clean_error(error),finished_at=now())
            manifest["status"] = job["status"]
            write_json(run/"manifest.json",manifest)
            self.log(job,"任务已停止，已完成镜头仍可复用" if stopped else clean_error(error))
        finally:
            if observer:
                observer.cancel()
                await asyncio.gather(observer, return_exceptions=True)
            self.save_job(job)

    async def execute_plan(self, job):
        from plan_story import plan
        run = self.run_path(job["run_id"])
        manifest = read_json(run / "manifest.json")
        try:
            job.update(status="running", stage="自动编剧与分镜")
            self.save_job(job)
            def progress(message):
                self.check_stop(job)
                job["stage"] = message
                self.log(job, message)
            story = await plan(job["brief"], run / "planning", job["seconds"], progress)
            self.check_stop(job)
            project = self.project(job["project_id"])
            if project["revision"] != job["source_revision"]:
                raise RuntimeError("规划期间草稿已修改；新分镜保留在本批次 planning/storyboard.json，未覆盖草稿")
            config = read_json(self.root / "config/h3_studio_video.json")
            config["comfyui_url"] = project["video"]["comfyui_url"]
            payload = self.validate({"story": story, "video": config, "tts": project["tts"]})
            revisions = self.project_path(project["id"]).parent / "revisions"
            revisions.mkdir(exist_ok=True)
            write_json(revisions / f"{project['revision']:06d}.json", project)
            project.update(**payload, revision=project["revision"] + 1, updated_at=now())
            write_json(self.project_path(project["id"]), project)
            write_json(run / "storyboard.json", story)
            write_json(run / "config.json", config)
            manifest.update(title=story["title"], studio_revision=project["revision"], shots=[{} for _ in story["shots"]],
                            input_fingerprint=fingerprint({"config": config, "story": story}), status="planned")
            write_json(run / "manifest.json", manifest)
            script = ["# " + story["title"], "", story["synopsis"], ""]
            for i, shot in enumerate(story["shots"], 1):
                script.extend([f"## {i:02d} · {shot['title']}", shot["description"], "镜头：" + shot["camera"]])
                script.extend(line["speaker"] + "：" + line["text"] for line in shot.get("dialogue", []))
            (run / "script.md").write_text("\n".join(script), encoding="utf-8")
            if job["auto_generate"]:
                job.update(action="film", planning_completed=True)
                self.save_job(job)
                await self.execute(job)
            else:
                job.update(status="complete", stage="剧本和分镜已生成", finished_at=now())
                self.save_job(job)
        except Exception as error:
            stopped = self.stops[job["id"]].is_set()
            job.update(status="stopped" if stopped else "failed", stage="规划已停止" if stopped else "规划失败", error=clean_error(error))
            manifest["status"] = job["status"]
            write_json(run / "manifest.json", manifest)
            self.log(job, job["error"])

    async def cancel(self, job):
        self.stops.setdefault(job["id"],threading.Event()).set()
        run = self.run_path(job["run_id"])
        manifest = read_json(run/"manifest.json")
        config = read_json(run/"config.json")
        for entry in manifest["shots"]:
            if entry.get("status") in ("running","submitting") and entry.get("prompt_id"):
                await self.comfy(local_url(config["comfyui_url"]),"/api/jobs/"+entry["prompt_id"]+"/cancel","POST",json={})
                job.setdefault("cancelled_prompts",[]).append(entry["prompt_id"])
                entry["status"]="cancelled"
        if job["id"] not in self.tasks or self.tasks[job["id"]].done():
            manifest["status"]="stopped"
            write_json(run/"manifest.json",manifest)
        job.update(status="stopping" if job["id"] in self.tasks and not self.tasks[job["id"]].done() else "stopped",stage="正在停止当前任务" if job["id"] in self.tasks and not self.tasks[job["id"]].done() else "已停止")
        self.save_job(job)

    async def start_job(self, project_id, action, selected=1):
        if action not in ("film","generate","shot","from_shot","voice","compose","audition"):
            raise web.HTTPBadRequest(text="未知任务类型")
        if any(job["status"] in ("running","queued","stopping") for job in self.jobs.values()):
            raise web.HTTPConflict(text="已有任务正在运行，请等待完成或先停止它")
        if any(job["project_id"]==project_id and job["status"]=="interrupted" for job in self.jobs.values()):
            raise web.HTTPConflict(text="上次任务被中断，请先在任务中心继续或停止该任务")
        project = self.validate(self.project(project_id))
        if action in ("film", "generate", "shot", "from_shot") and project["video"].get("generation_mode") == "h3" and not self.h3_status()["ready"]:
            raise web.HTTPConflict(text="H3 配套模型不完整")
        if type(selected) is not int or not 1 <= selected <= len(project["story"]["shots"]):
            raise web.HTTPBadRequest(text="镜头编号无效")
        if action in ("film", "generate", "shot", "from_shot") and project["video"].get("generation_mode") == "fun_camera":
            readiness = self.camera_status()
            if not readiness["ready"]:
                raise web.HTTPConflict(text="Fun Camera 模型尚未就绪：" + "、".join(readiness["missing"]))
            first = selected-1 if action in ("shot", "from_shot") else 0
            if not project["story"]["shots"][first].get("start_image") and (first == 0 or not project["video"]["use_previous_frame"]):
                raise web.HTTPBadRequest(text=f"镜头 {first+1} 的运镜模式需要起始参考图，请先选择图片")
        if action in ("voice","audition"):
            shots=project["story"]["shots"] if action=="voice" else [project["story"]["shots"][selected-1]]
            if not any(shot.get("dialogue") for shot in shots):
                raise web.HTTPBadRequest(text="请先给分镜添加角色对白")
        if action=="compose":
            source_id=project["latest_run"] or project["base_run"]
            if not source_id:
                raise web.HTTPConflict(text="还没有画面，请先生成镜头或点击生成成片")
            source=self.run_path(source_id)
            previous=read_json(source/"manifest.json")
            old_story,old_config=read_json(source/"storyboard.json"),read_json(source/"config.json")
            old_config.setdefault("output_frames_per_clip",old_config["frames"]-1)
            for index in range(len(project["story"]["shots"])):
                if index>=len(previous["shots"]) or previous["shots"][index].get("status")!="success" or self.visual_signature(project["video"],project["story"],index)!=self.visual_signature(old_config,old_story,index):
                    raise web.HTTPConflict(text="草稿画面已变化，请先生成画面或点击生成成片")
        run = self.prepare_run(project,action,selected)
        if action == "compose" and any(entry.get("status") != "success" for entry in read_json(run/"manifest.json")["shots"]):
            raise web.HTTPConflict(text="草稿画面已变化，部分镜头需要重新生成。请先生成画面或点击生成成片")
        job = {"id":uuid.uuid4().hex,"project_id":project_id,"run_id":run.name,"action":action,"selected":selected,"status":"queued","stage":"等待执行","created_at":now(),"logs":[]}
        self.jobs[job["id"]] = job
        self.stops[job["id"]] = threading.Event()
        self.save_job(job)
        if action != "audition":
            project["latest_run"] = run.name
            write_json(self.project_path(project_id),project)
        self.tasks[job["id"]] = asyncio.create_task(self.execute(job))
        return job


@web.middleware
async def security(request, handler):
    host = urlsplit("http://"+request.host).hostname
    if host not in ("127.0.0.1","localhost","::1"):
        return web.json_response({"error":"仅允许本机访问"},status=403)
    origin = request.headers.get("Origin")
    if origin and origin != str(request.url.origin()):
        return web.json_response({"error":"请求来源不匹配"},status=403)
    if request.method not in ("GET","HEAD","OPTIONS") and request.headers.get("X-AIMedia-Client") != "studio":
        return web.json_response({"error":"请从操作台提交修改"},status=403)
    try:
        response = await handler(request)
    except web.HTTPException as error:
        return web.json_response({"error":error.text},status=error.status)
    except (KeyError,TypeError,ValueError):
        return web.json_response({"error":"提交内容不完整或格式有误，请检查编辑项"},status=400)
    except Exception as error:
        return web.json_response({"error":clean_error(error)},status=500)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def create_app(root=ROOT):
    studio = Studio(root)
    app = web.Application(middlewares=[security],client_max_size=22*1024*1024)
    app["studio"] = studio
    routes = web.RouteTableDef()

    @routes.get("/api/projects")
    async def projects(request):
        return web.json_response({"projects":studio.list_projects(),"assets":studio.assets()})

    @routes.post("/api/projects")
    async def create(request):
        payload = await request.json()
        source_id = payload.get("copy_from")
        source_run = payload.get("run_id")
        if source_id:
            source = studio.project(source_id)
            story,config,tts,base = source["story"],source["video"],source["tts"],source["latest_run"] or source["base_run"]
        elif source_run:
            run = studio.run_path(source_run)
            story,config,tts,base = read_json(run/"storyboard.json"),read_json(run/"config.json"),read_json(root/"config/mimo_tts.json"),source_run
            config.setdefault("output_frames_per_clip",config["frames"]-1)
        else:
            story,config,tts,base = read_json(root/"prompts/stories/cat_biscuit_mystery.json"),read_json(root/"config/h3_studio_video.json"),read_json(root/"config/mimo_tts.json"),None
            if payload.get("blank"):
                story = {"title":"未命名作品","synopsis":"","style":"Realistic live-action cinematography, natural skin texture, expressive faces, consistent characters, no text.","negative_prompt":"text, watermark, deformed, flicker","speakers":{},"shots":[{"title":"开场","description":"","camera":"固定中景","prompt":"A realistic cinematic opening shot in a quiet room.","dialogue":[]}]}
        story = copy.deepcopy(story)
        if payload.get("title"):
            story["title"] = payload["title"]
        return web.json_response(studio.create_project(story,config,tts,base),status=201)

    @routes.get("/api/projects/{id}")
    async def project(request):
        project = studio.project(request.match_info["id"])
        return web.json_response({"project":project,"run":studio.run_info(project["latest_run"] or project["base_run"]),"jobs":[job for job in studio.jobs.values() if job["project_id"]==project["id"]]})

    @routes.post("/api/projects/{id}/plan")
    async def plan_project(request):
        payload = await request.json()
        brief, seconds = payload.get("brief"), payload.get("seconds", 60)
        if not isinstance(brief, str) or not 10 <= len(brief.strip()) <= 16000 or type(seconds) is not int or seconds % 5 or not 10 <= seconds <= 500:
            raise web.HTTPBadRequest(text="请填写创作要求；时长需为 10～500 秒之间的 5 秒倍数")
        if any(job["status"] in ("running", "queued", "stopping") for job in studio.jobs.values()):
            raise web.HTTPConflict(text="已有任务运行，请等待完成或停止")
        auto_generate = payload.get("auto_generate", False)
        if type(auto_generate) is not bool:
            raise web.HTTPBadRequest(text="自动生成选项无效")
        load_key()
        project = studio.project(request.match_info["id"])
        if payload.get("revision") != project["revision"]:
            raise web.HTTPConflict(text="草稿版本已变化，请重新载入后规划")
        run = studio.prepare_run(project, "plan", 1)
        job = {"id":uuid.uuid4().hex,"project_id":project["id"],"run_id":run.name,"action":"plan","selected":1,
               "brief":brief,"seconds":seconds,"auto_generate":auto_generate,"source_revision":project["revision"],
               "status":"queued","stage":"等待自动编剧","created_at":now(),"logs":[]}
        studio.jobs[job["id"]] = job
        studio.stops[job["id"]] = threading.Event()
        studio.save_job(job)
        project["latest_run"] = run.name
        write_json(studio.project_path(project["id"]), project)
        studio.tasks[job["id"]] = asyncio.create_task(studio.execute(job))
        return web.json_response(job, status=202)

    @routes.put("/api/projects/{id}")
    async def save(request):
        project = studio.project(request.match_info["id"])
        payload = await request.json()
        if payload.get("revision") != project["revision"]:
            raise web.HTTPConflict(text="项目已在其他窗口修改，请重新载入后再保存")
        studio.validate(payload)
        if fingerprint([project["story"],project["video"],project["tts"]]) != fingerprint([payload["story"],payload["video"],payload["tts"]]):
            revisions = studio.project_path(project["id"]).parent/"revisions"
            revisions.mkdir(exist_ok=True)
            write_json(revisions/f"{project['revision']:06d}.json",project)
            project.update(story=payload["story"],video=payload["video"],tts=payload["tts"],revision=project["revision"]+1,updated_at=now())
            write_json(studio.project_path(project["id"]),project)
        return web.json_response(project)

    @routes.get("/api/projects/{id}/revisions")
    async def revisions(request):
        folder = studio.project_path(request.match_info["id"]).parent/"revisions"
        return web.json_response([{"revision":p["revision"],"title":p["story"]["title"],"updated_at":p["updated_at"]} for file in sorted(folder.glob("*.json"),reverse=True) for p in [read_json(file)]])

    @routes.get("/api/projects/{id}/revisions/{revision}")
    async def revision(request):
        number = int(request.match_info["revision"])
        path = studio.project_path(request.match_info["id"]).parent/"revisions"/f"{number:06d}.json"
        if not path.exists():
            raise web.HTTPNotFound(text="草稿版本不存在")
        return web.json_response(read_json(path))

    @routes.get("/api/runs")
    async def runs(request):
        result=[]
        for path in (studio.root/"runs").glob("*/manifest.json"):
            m=read_json(path)
            if not isinstance(m.get("shots"), list) or not (path.parent/"storyboard.json").is_file():
                continue
            if not isinstance(m.get("shots"), list) or not (path.parent/"storyboard.json").is_file():
                continue
            final=next((str(file.relative_to(root)).replace("\\","/") for file in (path.parent/"final/film_with_dialogue.mp4",path.parent/"final/film.mp4") if file.exists()),None)
            result.append({"id":path.parent.name,"title":m["title"],"status":m["status"],"shots":len(m["shots"]),"specs":m.get("postproduction",{}).get("final_specs",m.get("final_specs")),"project_id":m.get("studio_project"),"final":final,"updated_at":datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()})
        return web.json_response(sorted(result,key=lambda x:x["updated_at"],reverse=True))

    @routes.get("/api/runs/{id}")
    async def run(request):
        info=studio.run_info(request.match_info["id"])
        if not info:
            raise web.HTTPNotFound(text="生成批次不存在")
        return web.json_response(info)

    @routes.get("/api/jobs")
    async def jobs(request):
        return web.json_response(sorted(studio.jobs.values(),key=lambda x:x["created_at"],reverse=True))

    @routes.post("/api/projects/{id}/jobs")
    async def start(request):
        payload=await request.json()
        return web.json_response(await studio.start_job(request.match_info["id"],payload["action"],payload.get("selected",1)),status=202)

    @routes.post("/api/jobs/{id}/stop")
    async def stop(request):
        job=studio.jobs.get(request.match_info["id"])
        if not job:
            raise web.HTTPNotFound(text="任务不存在")
        await studio.cancel(job)
        return web.json_response(job)

    @routes.post("/api/jobs/{id}/resume")
    async def resume(request):
        if any(job["status"] in ("running","queued","stopping") for job in studio.jobs.values()):
            raise web.HTTPConflict(text="已有任务正在运行")
        job=studio.jobs.get(request.match_info["id"])
        if not job or job["status"] not in ("interrupted","failed","stopped"):
            raise web.HTTPBadRequest(text="这个任务不需要恢复")
        manifest=read_json(studio.run_path(job["run_id"])/"manifest.json")
        if any(entry.get("status")=="failed" for entry in manifest["shots"]):
            raise web.HTTPConflict(text="有镜头明确失败，请在分镜中修改后重做。继续任务用于恢复等待中的任务")
        for entry in manifest["shots"]:
            if entry.get("status")=="cancelled":
                entry.setdefault("previous_attempts",[]).append({key:value for key,value in entry.items() if key!="previous_attempts"})
                entry.pop("prompt_id",None)
                entry["status"]="pending"
        write_json(studio.run_path(job["run_id"])/"manifest.json",manifest)
        studio.stops[job["id"]]=threading.Event()
        job.update(status="queued",error=None,stage="恢复任务")
        studio.save_job(job)
        studio.tasks[job["id"]]=asyncio.create_task(studio.execute(job))
        return web.json_response(job)

    @routes.post("/api/assets")
    async def upload(request):
        reader=await request.multipart()
        part=await reader.next()
        if not part or part.name!="image":
            raise web.HTTPBadRequest(text="请选择图片")
        content=await part.read(decode=False)
        if len(content)>20*1024*1024:
            raise web.HTTPBadRequest(text="参考图片不能超过 20MB")
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
                extension={"PNG":"png","JPEG":"jpg","WEBP":"webp"}.get(image.format)
                if not extension or max(image.size)>8192:
                    raise ValueError()
        except (OSError,ValueError):
            raise web.HTTPBadRequest(text="请选择有效的 PNG、JPG 或 WebP 图片，边长不超过 8192 像素") from None
        path=studio.workspace/"assets"/(uuid.uuid4().hex[:16]+"."+extension)
        path.write_bytes(content)
        return web.json_response({"path":str(path.relative_to(studio.root)).replace("\\","/"),"name":part.filename or path.name},status=201)

    @routes.get("/api/status")
    async def status(request):
        project=studio.project(request.query["project"]) if request.query.get("project") else None
        base=local_url(project["video"]["comfyui_url"] if project else "http://127.0.0.1:8189")
        profiles = {"h3": read_json(studio.root / "config/h3_studio_video.json")}
        result={"app":"AIMedia Studio","comfyui_url":base,"connected":False,"mimo_configured":False,"models":{},"generation_profiles":profiles,"camera_motions":list(CAMERA_MOTIONS),"fun_camera":studio.camera_status(),"h3":studio.h3_status(),"planning":{"script_weaver":(studio.root/".runtime/integrations/script-weaver").is_dir(),"video_claw":(studio.root/".runtime/integrations/video-claw").is_dir()}}
        try:
            result["mimo_configured"]=bool(load_key())
        except RuntimeError:
            pass
        try:
            async with studio.session.get(base+"/system_stats",timeout=aiohttp.ClientTimeout(total=3)) as response:
                stats=await response.json()
                result.update(connected=response.status==200,devices=[{"name":d["name"],"vram_total":d.get("vram_total"),"vram_free":d.get("vram_free")} for d in stats.get("devices",[])])
            queue=await studio.comfy(base,"/queue")
            result.update(running=len(queue["queue_running"]),pending=len(queue["queue_pending"]))
            for node,field in (("UNETLoader","diffusion_model"),("CLIPLoader","text_encoder"),("VAELoader","vae"),("CLIPVisionLoader","clip_vision")):
                data=await studio.comfy(base,"/object_info/"+node)
                inputs=data[node]["input"]["required"]
                key={"UNETLoader":"unet_name","CLIPLoader":"clip_name","VAELoader":"vae_name","CLIPVisionLoader":"clip_name"}[node]
                result["models"][field]=inputs[key][0]
        except (aiohttp.ClientError,asyncio.TimeoutError,RuntimeError,KeyError):
            pass
        return web.json_response(result)

    @routes.post("/api/engine/start")
    async def start_engine(request):
        base="http://127.0.0.1:8189"
        try:
            async with studio.session.get(base+"/system_stats",timeout=aiohttp.ClientTimeout(total=2)) as response:
                if response.status==200:
                    return web.json_response({"status":"ready","url":base})
        except (aiohttp.ClientError,asyncio.TimeoutError):
            pass
        if studio.engine_process and studio.engine_process.poll() is None:
            return web.json_response({"status":"starting","url":base})
        python=studio.root/"ComfyUI/.venv-rocm/Scripts/python.exe"
        if not python.exists():
            raise web.HTTPBadRequest(text="本机 GPU 环境尚未安装")
        cache=studio.root/".cache"
        cache.mkdir(exist_ok=True)
        with (cache/"studio-engine.stdout.log").open("ab") as out,(cache/"studio-engine.stderr.log").open("ab") as err:
            studio.engine_process=subprocess.Popen([str(python),"-u","main.py","--listen","127.0.0.1","--port","8189","--reserve-vram","3","--database-url","sqlite:///user/comfyui-gpu.db"],cwd=studio.root/"ComfyUI",stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        (cache/"studio-engine.pid").write_text(str(studio.engine_process.pid),encoding="utf-8")
        return web.json_response({"status":"starting","url":base})

    @routes.get("/media/{path:.*}")
    async def media(request):
        path=studio.media_path(request.match_info["path"])
        response=web.FileResponse(path)
        if path.suffix==".srt":
            response.content_type="text/plain"
            response.charset="utf-8"
        if request.query.get("download"):
            response.headers["Content-Disposition"]="attachment"
        return response

    @routes.get("/")
    async def index(request):
        return web.FileResponse(WEB/"index.html",headers={"Cache-Control":"no-cache"})

    app.add_routes(routes)
    app.router.add_static("/static/",WEB,show_index=False)

    async def startup(app):
        studio.session=aiohttp.ClientSession(trust_env=False)
        try:
            studio.initialize()
        except Exception:
            await studio.session.close()
            raise

    async def cleanup(app):
        for job in studio.jobs.values():
            if job["status"] in ("running","queued","stopping"):
                studio.stops.setdefault(job["id"],threading.Event()).set()
        await asyncio.gather(*studio.tasks.values(),return_exceptions=True)
        await studio.session.close()

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=8190)
    args=parser.parse_args()
    web.run_app(create_app(),host="127.0.0.1",port=args.port,print=lambda message:print(message,flush=True),access_log=None)
