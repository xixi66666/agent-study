"""Install pinned planning sources in the project-local runtime directory."""
import io
import json
import shutil
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
REPOS = {
    "script-weaver": ("KKenny0/script-weaver", "9261b91f4e50f2d481c2ba0f24b7615c6b9edb45"),
    "video-claw": ("HITsz-TMG/VideoClaw", "16c1ce0b553e30eff90ff1274e8a8a63c1d548a3"),
}

def main():
    target = ROOT / ".runtime/integrations"
    target.mkdir(parents=True, exist_ok=True)
    for name, (repo, commit) in REPOS.items():
        destination = target / name
        if destination.exists():
            continue
        response = requests.get(f"https://codeload.github.com/{repo}/zip/{commit}", timeout=180)
        response.raise_for_status()
        destination.mkdir()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for entry in archive.infolist():
                relative = Path(*Path(entry.filename).parts[1:])
                path = (destination / relative).resolve()
                if not path.is_relative_to(destination.resolve()):
                    raise RuntimeError("Invalid upstream archive path")
                if entry.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as source, path.open("wb") as output:
                        shutil.copyfileobj(source, output)
        print(f"Installed {repo} @ {commit[:12]}", flush=True)
    (target / "sources.json").write_text(json.dumps(REPOS, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
