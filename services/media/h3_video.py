"""H3 graph adapter and native stereo sound/subtitle assembly."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

import av
import numpy as np
from PIL import ImageDraw, ImageFont

from validate_h3 import build_prompt as validation_graph


def english_direction(story, shot, index, run_id):
    """Keep Chinese production notes out of H3's spoken content."""
    from add_dialogue import load_key
    from produce_video import ROOT, read_json, write_json
    aliases = {name: f"Character {i}" for i, name in enumerate(story.get("speakers", {}), 1)}
    def renamed(value):
        for name, alias in sorted(aliases.items(), key=lambda item: -len(item[0])):
            value = value.replace(name, alias)
        return value
    source = {"style": renamed(story["style"]), "visual": renamed(shot["prompt"]),
              "notes": renamed(shot.get("description", "")), "camera": renamed(shot.get("camera", "")),
              "appearances": {aliases[name]: role.get("appearance", "") for name, role in story.get("speakers", {}).items()}}
    signature = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    if not re.search(r"[\u3400-\u9fff]", json.dumps(source, ensure_ascii=False)):
        return {"direction": "\n".join(source[key] for key in ("style", "visual", "notes", "camera")), "appearances": source["appearances"]}, aliases
    cache = ROOT / "runs" / run_id / "prompts" / f"shot_{index:02d}_direction.json"
    if cache.exists():
        saved = read_json(cache)
        if saved.get("signature") == signature:
            return saved["result"], aliases
    import requests
    config = read_json(ROOT / "config/planning.json")
    if config["endpoint"] != "https://api.xiaomimimo.com/v1/chat/completions":
        raise ValueError("Invalid H3 direction translation endpoint")
    instruction = (
        "Translate these visual production instructions into precise English for MiniMax H3. "
        "Return only JSON: {\"direction\":\"English visual description\",\"appearances\":{\"Character 1\":\"English appearance\",...}}. "
        "Keep the exact Character labels and <Picture 1> reference label. All strings must be English; no Chinese characters. "
        "Combine style, visual, notes and camera into one coherent shot, preserve facial detail, physical actions and restrained camera movement. "
        "The explicit reference-image spatial arrangement overrides generic seating positions. Do not invent speech, narration, text on screen or new actions. "
        "Do not include any dialogue or instructions to read the production notes aloud. Preserve every character appearance. Keep direction under 350 words.")
    for attempt in range(3):
        response = requests.post(config["endpoint"], headers={"api-key": load_key(), "Content-Type": "application/json"},
            json={"model": config["model"], "messages": [{"role":"system","content":instruction},
                {"role":"user","content":json.dumps(source, ensure_ascii=False)}],
                "thinking":{"type":"disabled"}, "max_tokens":4096, "temperature":0.2}, timeout=config["timeout_seconds"])
        if response.status_code != 200:
            raise RuntimeError(f"H3 direction translation HTTP {response.status_code}")
        data = response.json()
        try:
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", data["choices"][0]["message"]["content"].strip())
            result = json.loads(content)
            if not isinstance(result.get("direction"), str) or not result["direction"].strip() or set(result["appearances"]) != set(source["appearances"]):
                raise ValueError("Missing translated direction or cast")
            if re.search(r"[\u3400-\u9fff]|</?d>", json.dumps(result, ensure_ascii=False)) or any(not isinstance(value, str) for value in result["appearances"].values()):
                raise ValueError("Only English visual directions are allowed")
            break
        except (ValueError, KeyError, TypeError):
            if attempt == 2:
                raise
    cache.parent.mkdir(parents=True, exist_ok=True)
    write_json(cache, {"signature":signature, "result":result, "model":config["model"], "usage":data.get("usage",{})})
    return result, aliases


def build_h3_prompt(config, story, shot, index, run_id, reference_images=()):
    translated, aliases = english_direction(story, shot, index, run_id)
    dialogue = " ".join(
        f"{aliases[line['speaker']]} speaks with visible synchronized mouth movement: <d>[Chinese]{line['text']}</d>"
        for line in shot.get("dialogue", []))
    direction = (translated["direction"]
                 + "\n" + dialogue + " All speech finishes by 4.3 seconds. No additional speech, subtitles, title cards or logos."
                 + " Natural breathing, blinking, subtle facial muscle motion; camera movement remains restrained.")
    sound = "Quiet realistic room tone, low suspense drone beneath clear foreground dialogue, no sung lyrics."
    if reference_images:
        characters = "; ".join(name + ": " + appearance for name, appearance in translated["appearances"].items())
        prompt = ("subject_definitions:\n<Picture 1> is the identity and location reference for the cast. " + characters
                  + "\nsummary:\nA realistic suspense film shot with the same character identities and wardrobe, newly framed as described."
                  + "\nretention_analysis:\n<Picture 1>: reference only. Preserve identities, costume and room layout; change camera framing and expression. Do not copy a frozen still."
                  + "\ndetailed_description:\n[Shot 1] " + direction
                  + "\noverall_soundscape:\n" + sound + "\nnon_diegetic_music:\nVery quiet continuous tension drone.")
    else:
        prompt = "integrated_multimodal_description:\n[Shot 1] " + direction + "\noverall_soundscape:\n" + sound + "\nnon_diegetic_music:\nVery quiet tension drone."
    params = {**config, "video_vae": config["vae"], "seed": shot.get("seed", config["seed"] + index)}
    graph = validation_graph(params, prompt, run_id)
    for offset, image in enumerate(reference_images, 1):
        node = str(70 + offset)
        graph[node] = {"class_type": "LoadImage", "inputs": {"image": image}}
        graph["5"]["inputs"][f"ref_images.ref_image_{offset}"] = [node, 0]
    graph["58"] = graph.pop("14")
    graph["58"]["inputs"]["filename_prefix"] = f"video/{run_id}/shot_{index:02d}"
    return graph


def native_audio(path, sample_count, rate=32000):
    resampler = av.AudioResampler(format="fltp", layout="stereo", rate=rate)
    chunks = []
    with av.open(str(path)) as source:
        if not source.streams.audio:
            raise RuntimeError(f"H3 clip has no native audio: {path.name}")
        for frame in source.decode(audio=0):
            chunks.extend(part.to_ndarray() for part in resampler.resample(frame))
        chunks.extend(part.to_ndarray() for part in resampler.resample(None))
    audio = np.concatenate(chunks, axis=1) if chunks else np.zeros((2, 0), dtype=np.float32)
    if not np.isfinite(audio).all() or audio.shape[1] == 0:
        raise RuntimeError("H3 audio cannot be decoded")
    result = np.zeros((2, sample_count), dtype=np.float32)
    result[:, :min(sample_count, audio.shape[1])] = audio[:, :sample_count]
    return result


def compose_native(run, story, config, tts):
    from produce_video import inspect_clip, write_json
    from add_dialogue import srt_time
    fps, rate = config["fps"], 32000
    duration = config["output_frames_per_clip"] / fps
    clips = [run / "clips" / f"shot_{i:02d}.mp4" for i in range(1, len(story["shots"]) + 1)]
    tracks = []
    for clip in clips:
        track = native_audio(clip, round(duration * rate))
        fade = min(rate // 100, track.shape[1] // 2)
        ramp = np.linspace(0, 1, fade, dtype=np.float32)
        track[:, :fade] *= ramp
        track[:, -fade:] *= ramp[::-1]
        tracks.append(track)
    audio = np.concatenate(tracks, axis=1)
    cues = [{"shot": i + 1, "speaker": line["speaker"], "text": line["text"],
             "start": i * duration + 0.25, "end": (i + 1) * duration - 0.2, "subtitle_end": (i + 1) * duration - 0.2}
            for i, shot in enumerate(story["shots"]) for line in shot.get("dialogue", [])]
    write_json(run / "subtitles/timeline.json", cues)
    (run / "subtitles/dialogue.srt").write_text("\n".join(
        f"{i}\n{srt_time(cue['start'])} --> {srt_time(cue['end'])}\n{cue['speaker']}：{cue['text']}\n"
        for i, cue in enumerate(cues, 1)), encoding="utf-8")
    font = ImageFont.truetype(tts["subtitle_font"], min(tts["subtitle_font_size"], 26))
    destination = run / "final/film_with_dialogue.mp4"
    temporary = destination.with_suffix(".partial.mp4")
    with av.open(str(run / "final/film.mp4")) as source, av.open(str(temporary), "w", options={"movflags": "+faststart"}) as output:
        video = output.add_stream("libx264", rate=fps)
        video.width, video.height = config["width"], config["height"]
        video.pix_fmt = "yuv420p"
        video.options = {"crf": "18", "preset": "medium"}
        sound = output.add_stream("aac", rate=rate)
        sound.layout, sound.bit_rate = "stereo", 160000
        audio_position = 0
        for index, frame in enumerate(source.decode(video=0)):
            image = frame.to_image()
            cue = next((cue for cue in cues if cue["start"] <= index / fps < cue["end"]), None)
            if cue:
                draw = ImageDraw.Draw(image)
                text = cue["speaker"] + "：" + cue["text"]
                if font.getlength(text) > image.width - 32:
                    raise RuntimeError("Subtitle does not fit; shorten dialogue")
                draw.text(((image.width - font.getlength(text)) / 2, image.height - 44), text,
                          font=font, fill="white", stroke_width=2, stroke_fill="black")
            encoded = av.VideoFrame.from_image(image)
            encoded.pts, encoded.time_base = index, Fraction(1, fps)
            for packet in video.encode(encoded):
                output.mux(packet)
            while audio_position < audio.shape[1] and audio_position / rate < (index + 1) / fps:
                chunk = np.ascontiguousarray(audio[:, audio_position:audio_position + 1024])
                audio_frame = av.AudioFrame.from_ndarray(chunk, format="fltp", layout="stereo")
                audio_frame.sample_rate, audio_frame.pts, audio_frame.time_base = rate, audio_position, Fraction(1, rate)
                for packet in sound.encode(audio_frame):
                    output.mux(packet)
                audio_position += chunk.shape[1]
        for packet in video.encode(None):
            output.mux(packet)
        for packet in sound.encode(None):
            output.mux(packet)
    temporary.replace(destination)
    specs = inspect_clip(destination)
    specs.update(audio_sample_rate=rate, audio_channels=2, audio_source="H3 native", audio_rms=float(np.sqrt(np.mean(audio ** 2))))
    write_json(run / "audio/manifest.json", {"status": "complete", "model": "MiniMax H3 native audio",
               "duration_seconds": duration * len(clips), "sample_rate": rate, "channels": 2, "lines": []})
    return specs
