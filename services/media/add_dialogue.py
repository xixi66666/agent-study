"""Create MiMo dialogue, timed sentence subtitles and a voiced, subtitled film."""

import argparse
import base64
import hashlib
import json
import os
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlsplit

import av
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

from produce_video import ROOT, inspect_clip, read_json, write_json


def load_key():
    key = os.environ.get("MIMO_API_KEY")
    if not key and os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as environment:
                key = winreg.QueryValueEx(environment, "MIMO_API_KEY")[0]
        except FileNotFoundError:
            pass
    if not key:
        raise RuntimeError("MIMO_API_KEY is not configured")
    return key


def decode_audio(path, rate):
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
    chunks = []
    with av.open(str(path)) as source:
        for frame in source.decode(audio=0):
            chunks.extend(item.to_ndarray()[0] for item in resampler.resample(frame))
        chunks.extend(item.to_ndarray()[0] for item in resampler.resample(None))
    if not chunks:
        raise RuntimeError(f"Empty audio: {path.name}")
    return np.concatenate(chunks).astype(np.float32)


def speech_bounds(samples, rate):
    window = max(1, rate // 100)
    count = len(samples) // window
    energy = np.sqrt(np.mean(samples[:count * window].reshape(count, window) ** 2, axis=1))
    active = np.flatnonzero(energy > 0.004)
    if len(active) == 0:
        raise RuntimeError("The generated dialogue has no detectable speech")
    start = max(0, int(active[0] * window - rate * 0.05))
    end = min(len(samples), int((active[-1] + 1) * window + rate * 0.1))
    return start, end


def change_tempo(samples, rate, speed):
    frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="fltp", layout="mono")
    frame.sample_rate = rate
    frame.time_base = Fraction(1, rate)
    frame.pts = 0
    graph = av.filter.Graph()
    source = graph.add_abuffer(sample_rate=rate, format="fltp", layout="mono", time_base=Fraction(1, rate))
    tempo = graph.add("atempo", str(speed))
    sink = graph.add("abuffersink")
    source.link_to(tempo)
    tempo.link_to(sink)
    graph.configure()
    graph.push(frame)
    graph.push(None)
    chunks = []
    while True:
        try:
            chunks.append(graph.pull().to_ndarray()[0])
        except (av.error.BlockingIOError, av.error.EOFError):
            break
    if not chunks:
        raise RuntimeError("Audio tempo adjustment returned no samples")
    return np.concatenate(chunks).astype(np.float32)


def write_wave(path, samples, rate):
    with av.open(str(path), "w") as output:
        stream = output.add_stream("pcm_s16le", rate=rate)
        stream.layout = "mono"
        for position in range(0, len(samples), 1024):
            frame = av.AudioFrame.from_ndarray(samples[position:position + 1024].reshape(1, -1), format="fltp", layout="mono")
            frame.sample_rate = rate
            frame.pts = position
            frame.time_base = Fraction(1, rate)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)


def srt_time(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def synthesize(run, story, video_config, config, regenerate_lines=(), style_override=None, cancel_requested=None, progress_callback=None):
    for name in ("audio", "subtitles"):
        (run / name).mkdir(exist_ok=True)
    rate = config["sample_rate"]
    shot_duration = video_config.get("output_frames_per_clip", video_config["frames"]) / video_config["fps"]
    total_duration = shot_duration * len(story["shots"])
    fingerprint = hashlib.sha256(json.dumps({"story": story, "tts": config, "shot_duration": shot_duration}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    manifest_path = run / "audio/manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if manifest["input_fingerprint"] != fingerprint:
            expected = [(line, story["speakers"][line["speaker"]]) for shot in story["shots"] for line in shot.get("dialogue", [])]
            if len(expected) != len(manifest["lines"]):
                raise RuntimeError("Dialogue inputs changed; select the edited lines with --regenerate-lines")
            if (manifest.get("duration_seconds"), manifest.get("sample_rate"), manifest["model"]) != (total_duration, rate, config["model"]):
                raise RuntimeError("Audio timeline or model changed; use a new batch")
            for index, ((line, speaker), old) in enumerate(zip(expected, manifest["lines"]), 1):
                if index not in regenerate_lines and (line["speaker"], line["text"], speaker["voice"]) != (old["speaker"], old["text"], old["voice"]):
                    raise RuntimeError(f"Changed dialogue {index} was not selected for regeneration")
            manifest.setdefault("previous_input_fingerprints", []).append(manifest["input_fingerprint"])
            manifest["input_fingerprint"] = fingerprint
            manifest["status"] = "generating"
            write_json(manifest_path, manifest)
    else:
        manifest = {"input_fingerprint": fingerprint, "model": config["model"], "status": "generating", "lines": []}
        write_json(manifest_path, manifest)
    endpoint = urlsplit(config["endpoint"])
    if endpoint.scheme != "https" or endpoint.hostname != "api.xiaomimimo.com":
        raise RuntimeError("Only the official MiMo HTTPS endpoint is allowed")
    timeline = np.zeros(round(total_duration * rate), dtype=np.float32)
    cues = []
    line_index = 0
    with requests.Session() as session:
        for shot_index, shot in enumerate(story["shots"]):
            offset = config["dialogue_start_offset_seconds"]
            for line in shot.get("dialogue", []):
                if cancel_requested and cancel_requested():
                    raise RuntimeError("Dialogue generation cancelled")
                line_index += 1
                if progress_callback:
                    progress_callback(line_index, line)
                speaker = story["speakers"][line["speaker"]]
                original = run / "audio" / f"line_{line_index:02d}_original.wav"
                fitted = run / "audio" / f"line_{line_index:02d}.wav"
                if len(manifest["lines"]) < line_index:
                    manifest["lines"].append({"speaker": line["speaker"], "text": line["text"], "voice": speaker["voice"]})
                entry = manifest["lines"][line_index - 1]
                if line_index in regenerate_lines and original.exists():
                    attempt = {key: value for key, value in entry.items() if key != "previous_attempts"}
                    attempts = entry.setdefault("previous_attempts", [])
                    attempts.append(attempt)
                    original.rename(original.with_name(f"line_{line_index:02d}_attempt_{len(attempts):02d}.wav"))
                    entry.pop("original_sha256", None)
                    entry["status"] = "regenerating"
                    write_json(manifest_path, manifest)
                entry.update({"speaker": line["speaker"], "text": line["text"], "voice": speaker["voice"]})
                if original.exists() and entry.get("original_sha256"):
                    if hashlib.sha256(original.read_bytes()).hexdigest() != entry["original_sha256"]:
                        raise RuntimeError(f"Audio changed: {original.name}")
                else:
                    print(f"MiMo dialogue {line_index:02d}: {line['speaker']}", flush=True)
                    style = style_override if line_index in regenerate_lines and style_override else speaker["style"]
                    payload = {"model": config["model"], "messages": [{"role": "user", "content": style}, {"role": "assistant", "content": line["text"]}], "audio": {"format": "wav", "voice": speaker["voice"]}}
                    try:
                        response = session.post(config["endpoint"], headers={"Authorization": "Bearer " + load_key()}, json=payload, timeout=config["timeout_seconds"], allow_redirects=False)
                    except requests.RequestException:
                        raise RuntimeError("MiMo request failed; check network connectivity") from None
                    if response.status_code != 200:
                        raise RuntimeError(f"MiMo returned HTTP {response.status_code}; check credentials, quota and service status")
                    data = response.json()
                    encoded = data.get("choices", [{}])[0].get("message", {}).get("audio", {}).get("data")
                    if not encoded:
                        raise RuntimeError("MiMo response contains no audio")
                    original.write_bytes(base64.b64decode(encoded, validate=True))
                    entry.update({"original_sha256": hashlib.sha256(original.read_bytes()).hexdigest(), "request_id": data.get("id"), "style": style, "status": "downloaded"})
                    write_json(manifest_path, manifest)
                if cancel_requested and cancel_requested():
                    raise RuntimeError("Dialogue generation cancelled")
                samples = decode_audio(original, rate)
                start, end = speech_bounds(samples, rate)
                samples = samples[start:end]
                available = shot_duration - offset - 0.2
                if available <= 0:
                    raise RuntimeError("Too many dialogue lines for this shot")
                speed = max(1.0, len(samples) / rate / available)
                if speed > 1.3:
                    raise RuntimeError(f"Dialogue {line_index:02d} is too long; shorten its text")
                if speed > 1:
                    samples = change_tempo(samples, rate, speed * 1.005)
                if len(samples) / rate > available + 0.02:
                    raise RuntimeError("Adjusted dialogue does not fit the shot")
                peak = float(np.max(np.abs(samples)))
                if peak > 0.98:
                    samples *= 0.98 / peak
                write_wave(fitted, samples, rate)
                cue_start = shot_index * shot_duration + offset
                cue_end = cue_start + len(samples) / rate
                position = round(cue_start * rate)
                timeline[position:position + len(samples)] += samples
                cues.append({"shot": shot_index + 1, "speaker": line["speaker"], "text": line["text"], "start": cue_start, "end": cue_end, "subtitle_end": min((shot_index + 1) * shot_duration, cue_end + 0.15)})
                entry.update({"status": "success", "audio": fitted.name, "duration_seconds": len(samples) / rate, "tempo": speed, "start_seconds": cue_start, "end_seconds": cue_end, "sha256": hashlib.sha256(fitted.read_bytes()).hexdigest()})
                write_json(manifest_path, manifest)
                print(f"Dialogue {line_index:02d} ready: {len(samples) / rate:.2f}s", flush=True)
                offset += len(samples) / rate + 0.15
    write_wave(run / "audio/dialogue.wav", timeline, rate)
    write_json(run / "subtitles/timeline.json", cues)
    entries = [f"{index}\n{srt_time(cue['start'])} --> {srt_time(cue['subtitle_end'])}\n{cue['speaker']}：{cue['text']}\n" for index, cue in enumerate(cues, 1)]
    (run / "subtitles/dialogue.srt").write_text("\n".join(entries), encoding="utf-8")
    manifest.update({"status": "audio_ready", "duration_seconds": total_duration, "sample_rate": rate, "line_count": line_index})
    write_json(manifest_path, manifest)
    return timeline, cues, manifest


def subtitle_overlay(cue, size, config):
    width, height = size
    font = ImageFont.truetype(config["subtitle_font"], config["subtitle_font_size"])
    text = cue["speaker"] + "：" + cue["text"]
    lines, current = [], ""
    for character in text:
        if current and font.getlength(current + character) > width - 64:
            lines.append(current)
            current = ""
        current += character
    if current:
        lines.append(current)
    if len(lines) > 2:
        raise RuntimeError("Subtitle exceeds two lines; shorten the dialogue")
    line_height = config["subtitle_font_size"] + 10
    box_height = len(lines) * line_height + 20
    band_height = config["subtitle_band_height"]
    top = height - band_height + 48 + (band_height - 48 - box_height) // 2
    overlay = Image.new("RGBA", size)
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle((20, top, width - 20, top + box_height), radius=12, fill=(15, 24, 30, 185))
    for index, line in enumerate(lines):
        x = (width - font.getlength(line)) / 2
        draw.text((x, top + 10 + index * line_height), line, font=font, fill=(255, 255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0, 255))
    return overlay


def render(source, target, audio, cues, config, fps, title=""):
    temporary = target.with_name(target.stem + ".partial.mp4")
    rate = config["sample_rate"]
    with av.open(str(source)) as video, av.open(str(temporary), "w", options={"movflags": "+faststart"}) as output:
        source_stream = video.streams.video[0]
        size = (source_stream.width, source_stream.height)
        band_height = config["subtitle_band_height"]
        band = Image.new("RGBA", size)
        band_draw = ImageDraw.Draw(band)
        band_draw.rectangle((0, size[1] - band_height, size[0], size[1]), fill=(255, 246, 231, 255))
        band_draw.line((0, size[1] - band_height, size[0], size[1] - band_height), fill=(197, 152, 95, 255), width=2)
        title_font = ImageFont.truetype(config["subtitle_font"], config["subtitle_title_font_size"])
        band_draw.text(((size[0] - title_font.getlength(title)) / 2, size[1] - band_height + 15), title, font=title_font, fill=(105, 78, 53, 255))
        overlays = [subtitle_overlay(cue, size, config) for cue in cues]
        stream = output.add_stream("libx264", rate=fps)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": "18", "preset": "medium"}
        sound = output.add_stream("aac", rate=rate)
        sound.layout = "mono"
        sound.bit_rate = 96000
        audio_position = 0
        frame_count = 0
        for index, frame in enumerate(video.decode(video=0)):
            image = Image.alpha_composite(frame.to_image().convert("RGBA"), band)
            for cue, overlay in zip(cues, overlays):
                if cue["start"] <= index / fps < cue["subtitle_end"]:
                    image = Image.alpha_composite(image, overlay)
                    break
            encoded_frame = av.VideoFrame.from_image(image.convert("RGB"))
            encoded_frame.pts = index
            encoded_frame.time_base = Fraction(1, fps)
            for packet in stream.encode(encoded_frame):
                output.mux(packet)
            while audio_position < len(audio) and audio_position / rate < (index + 1) / fps:
                samples = audio[audio_position:audio_position + 1024]
                audio_frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="fltp", layout="mono")
                audio_frame.sample_rate = rate
                audio_frame.pts = audio_position
                audio_frame.time_base = Fraction(1, rate)
                for packet in sound.encode(audio_frame):
                    output.mux(packet)
                audio_position += len(samples)
            frame_count += 1
        if abs(frame_count / fps - len(audio) / rate) > 1 / fps:
            raise RuntimeError("Video and dialogue timeline durations differ")
        for packet in stream.encode(None):
            output.mux(packet)
        for packet in sound.encode(None):
            output.mux(packet)
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/mimo_tts.json")
    parser.add_argument("--audio-only", action="store_true")
    parser.add_argument("--regenerate-lines", nargs="+", type=int, default=[], help="Regenerate selected dialogue lines, retaining previous attempts")
    parser.add_argument("--style-override", help="Style instruction for the selected regenerated lines")
    parser.add_argument("--dialogue-overrides", type=Path, help="JSON mapping dialogue line numbers to revised text")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if not run.is_relative_to((ROOT / "runs").resolve()):
        parser.error("The video batch must be inside the project's runs directory")
    story, video_config, config = read_json(run / "storyboard.json"), read_json(run / "config.json"), read_json(args.config.resolve())
    overrides_path = run / "audio/dialogue_overrides.json"
    overrides = read_json(args.dialogue_overrides.resolve()) if args.dialogue_overrides else read_json(overrides_path) if overrides_path.exists() else {}
    line_index = 0
    for shot in story["shots"]:
        for line in shot.get("dialogue", []):
            line_index += 1
            if str(line_index) in overrides:
                line["text"] = overrides[str(line_index)]
    if args.dialogue_overrides:
        write_json(overrides_path, overrides)
    audio, cues, manifest = synthesize(run, story, video_config, config, args.regenerate_lines, args.style_override)
    if args.audio_only:
        print("Dialogue and subtitles ready", flush=True)
        return
    source = run / "final/film.mp4"
    target = run / "final/film_with_dialogue.mp4"
    print("Rendering dialogue and subtitles", flush=True)
    render(source, target, audio, cues, config, video_config["fps"], story["title"])
    manifest.update({"status": "complete", "final": str(target.relative_to(run)), "final_specs": inspect_clip(target)})
    write_json(run / "audio/manifest.json", manifest)
    video_manifest = read_json(run / "manifest.json")
    video_manifest["postproduction"] = {"status": "complete", "final": manifest["final"], "final_specs": manifest["final_specs"], "audio_manifest": "audio/manifest.json", "subtitles": "subtitles/dialogue.srt"}
    write_json(run / "manifest.json", video_manifest)
    print(f"Completed voiced film: {target}", flush=True)


if __name__ == "__main__":
    main()
