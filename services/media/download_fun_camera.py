"""Download verified Fun Camera weights from the official ModelScope repository."""

import hashlib
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
REPO = "PAI/Wan2.1-Fun-V1.1-1.3B-Control-Camera"
FILES = {
    "diffusion_pytorch_model.safetensors": "diffusion_models/wan2.1_fun_camera_v1.1_1.3B_bf16.safetensors",
    "Wan2.1_VAE.pth": "vae/Wan2.1_VAE.pth",
    "models_clip_open-clip-xlm-roberta-large-vit-huge-14.pth": "clip_vision/wan2.1_clip_vision_h.pth",
}
STATE = ROOT / ".cache/fun-camera-download.json"


def convert_vision(source, target):
    """Map Wan's CLIP-H vision tensors to ComfyUI's Transformers names, losslessly."""
    import torch
    from safetensors.torch import save_file
    if target.exists():
        return
    original = torch.load(source, map_location="cpu", weights_only=True, mmap=True)
    converted = {}
    names = {"cls_embedding":"vision_model.embeddings.class_embedding",
             "pos_embedding":"vision_model.embeddings.position_embedding.weight",
             "head":"visual_projection.weight",
             "patch_embedding.weight":"vision_model.embeddings.patch_embedding.weight",
             "pre_norm.weight":"vision_model.pre_layrnorm.weight", "pre_norm.bias":"vision_model.pre_layrnorm.bias",
             "post_norm.weight":"vision_model.post_layernorm.weight", "post_norm.bias":"vision_model.post_layernorm.bias"}
    for name, destination in names.items():
        value = original["visual." + name]
        if name == "cls_embedding":
            value = value.reshape(-1)
        elif name == "pos_embedding":
            value = value.squeeze(0)
        elif name == "head":
            value = value.transpose(0, 1)
        converted[destination] = value.contiguous()
    for index in range(32):
        source_prefix, destination = f"visual.transformer.{index}.", f"vision_model.encoder.layers.{index}."
        for source_name, destination_name in (("norm1","layer_norm1"),("norm2","layer_norm2"),("attn.proj","self_attn.out_proj"),("mlp.0","mlp.fc1"),("mlp.2","mlp.fc2")):
            for suffix in ("weight", "bias"):
                converted[destination + destination_name + "." + suffix] = original[source_prefix + source_name + "." + suffix].contiguous()
        for suffix in ("weight", "bias"):
            values = original[source_prefix + "attn.to_qkv." + suffix].chunk(3, dim=0)
            for name, value in zip(("q_proj", "k_proj", "v_proj"), values):
                converted[destination + "self_attn." + name + "." + suffix] = value.contiguous()
    # All vision tensors must be accounted for; text-encoder tensors are not used.
    assert len([name for name in original if name.startswith("visual.")]) == 32*12+8
    assert len(converted) == 32*16+8
    temporary = target.with_suffix(target.suffix + ".tmp")
    save_file(converted, str(temporary), metadata={"source_repository":REPO,"conversion":"Wan CLIP-H to Transformers; original tensor dtype preserved"})
    temporary.replace(target)
    print("Converted vision encoder: " + target.name, flush=True)


def save_state(value):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE)


def main():
    session = requests.Session()
    response = session.get("https://modelscope.cn/api/v1/models/" + REPO + "/repo/files",
                           params={"Recursive":"true", "Revision":"master"}, timeout=40)
    response.raise_for_status()
    metadata = {item["Path"]:item for item in response.json()["Data"]["Files"]}
    progress = {"repository":REPO, "status":"downloading", "files":[]}
    save_state(progress)
    for source, relative in FILES.items():
        target = ROOT / "ComfyUI/models" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        expected = metadata[source]
        entry = {"file":relative, "size":expected["Size"], "sha256":expected["Sha256"], "downloaded":0, "status":"downloading"}
        progress["files"].append(entry)
        if target.exists():
            with target.open("rb") as stream:
                if target.stat().st_size == expected["Size"] and hashlib.file_digest(stream,"sha256").hexdigest() == expected["Sha256"]:
                    entry.update(status="verified", downloaded=expected["Size"])
                    save_state(progress)
                    continue
            raise RuntimeError("Existing model does not match official checksum: " + relative)
        for attempt in range(5):
            offset = partial.stat().st_size if partial.exists() else 0
            try:
                # A query distinguishes the full download from cached range probes.
                url = "https://modelscope.cn/models/" + REPO + "/resolve/master/" + source + "?download=true"
                with session.get(url, headers={"Range":f"bytes={offset}-"} if offset else {},
                                 stream=True, timeout=(40,90)) as response:
                    response.raise_for_status()
                    if offset and response.status_code == 206:
                        if not response.headers.get("Content-Range","").startswith(f"bytes {offset}-"):
                            raise RuntimeError("Unexpected resume range")
                    elif offset:
                        offset = 0
                    last_report = 0
                    with partial.open("ab" if offset else "wb") as output:
                        for chunk in response.iter_content(4*1024*1024):
                            output.write(chunk)
                            offset += len(chunk)
                            if time.monotonic() - last_report > 10:
                                entry["downloaded"] = offset
                                save_state(progress)
                                print(f"{relative}: {offset/1024**2:.0f}/{expected['Size']/1024**2:.0f} MiB", flush=True)
                                last_report = time.monotonic()
                if partial.stat().st_size != expected["Size"]:
                    raise RuntimeError("Incomplete download: " + relative)
                break
            except (requests.RequestException, RuntimeError):
                if attempt == 4:
                    raise
                time.sleep(2)
        with partial.open("rb") as stream:
            digest = hashlib.file_digest(stream,"sha256").hexdigest()
        if digest != expected["Sha256"]:
            raise RuntimeError("Checksum mismatch: " + relative)
        partial.replace(target)
        entry.update(status="verified", downloaded=expected["Size"])
        save_state(progress)
        print("Verified: " + relative, flush=True)
    progress["status"] = "converting"
    save_state(progress)
    convert_vision(ROOT / "ComfyUI/models/clip_vision/wan2.1_clip_vision_h.pth",
                   ROOT / "ComfyUI/models/clip_vision/wan2.1_clip_vision_h.safetensors")
    progress["status"] = "complete"
    save_state(progress)
    print("Fun Camera models ready", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        current = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
        current["status"] = "failed"
        save_state(current)
        raise
