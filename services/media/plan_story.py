"""Script-Weaver planning followed by VideoClaw continuity review for AIMedia."""
import argparse
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

from add_dialogue import load_key
from produce_video import ROOT, read_json, write_json

INTEGRATIONS = ROOT / ".runtime/integrations"


def parse_object(content):
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("Planner must return a JSON object")
    return result


def validate_story(story, seconds):
    count = seconds // 5
    if len(story["shots"]) != count or not 3 <= len(story["speakers"]) <= 5:
        raise ValueError(f"Need exactly {count} shots and 3–5 characters")
    for index, shot in enumerate(story["shots"], 1):
        if not shot.get("prompt") or not shot.get("camera") or not shot.get("description"):
            raise ValueError("Every shot needs action, camera and visual prompt")
        if len(shot.get("dialogue", [])) > 1:
            raise ValueError("Use at most one short dialogue line per shot")
        for line in shot.get("dialogue", []):
            if line["speaker"] not in story["speakers"] or len(line["text"]) > 22:
                raise ValueError("Unknown speaker or dialogue too long for five seconds")
        shot["reference_shots"] = [1] if index > 1 else []
    return story


async def plan(brief, folder, seconds=60, progress=print):
    folder.mkdir(parents=True, exist_ok=True)
    config = read_json(ROOT / "config/planning.json")
    if config["endpoint"] != "https://api.xiaomimimo.com/v1/chat/completions":
        raise ValueError("Planning endpoint must be the configured official MiMo service")
    if seconds % 5 or not 10 <= seconds <= 500:
        raise ValueError("Duration must be a multiple of five, between 10 and 500 seconds")
    for name in ("script-weaver", "video-claw"):
        if not (INTEGRATIONS / name).is_dir():
            raise RuntimeError("Install planning sources with services/media/install_planners.py")
    os.environ["SCRIPTWEAVER_DATA_DIR"] = str(ROOT / "workspace/planning-memory")
    os.environ["SCRIPTWEAVER_SKILLS_CUSTOM_DIR"] = str(ROOT / "workspace/planning-memory/skills")
    os.environ["SCRIPTWEAVER_LLM_MAX_TOKENS"] = str(config["max_tokens"])
    os.environ["SCRIPTWEAVER_AGENT_MAX_TOOL_ITERATIONS"] = "8"
    os.environ["SCRIPTWEAVER_AGENT_TIMEOUT_SECONDS"] = str(config["timeout_seconds"])
    from script_weaver.core.pipeline import PipelineEngine
    from script_weaver.core.types import ProjectState
    from script_weaver.llm.client import LLMClient
    from script_weaver.llm.providers import OpenAICompatibleBase
    import httpx

    usage = []

    class MiMoProvider(OpenAICompatibleBase):
        BASE_URL = config["endpoint"]
        REQUEST_OPTIONS = {"thinking": {"type": "disabled"}}

        def _build_headers(self):
            return {"api-key": self.api_key, "Content-Type": "application/json"}

        async def chat(self, messages, tools=None, temperature=0.7, max_tokens=16384):
            payload = {"model": self.model, "messages": messages, "temperature": temperature,
                       "max_tokens": max_tokens, **self.REQUEST_OPTIONS}
            if tools:
                payload["tools"] = [{"type": "function", "function": {"name": t["name"],
                    "description": t.get("description", ""), "parameters": t["parameters"]}} for t in tools]
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=config["timeout_seconds"]) as client:
                        response = await client.post(self.BASE_URL, headers=self._build_headers(), json=payload)
                    if response.status_code != 200:
                        raise RuntimeError(f"MiMo planning HTTP {response.status_code}")
                    data = response.json()
                    usage.append(data.get("usage", {}))
                    return self._parse_openai_response(data)
                except (httpx.HTTPError, RuntimeError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** attempt)

    provider = MiMoProvider(load_key(), config["model"])
    client = LLMClient(provider)
    engine = PipelineEngine(llm_client=client, auto_approve_gates=True,
                            progress_callback=lambda stage, message: progress(f"{stage}: {message}"))
    basis = hashlib.sha256((brief + str(seconds) + json.dumps(config)).encode()).hexdigest()
    checkpoint = folder / "script_weaver_checkpoint.json"
    saved = read_json(checkpoint) if checkpoint.exists() else {}
    if saved and saved["basis"] != basis:
        raise ValueError("Planning inputs changed; create a new planning run")
    completed = saved.get("completed_steps", [])

    async def on_stage(step, state):
        if step not in completed:
            completed.append(step)
        write_json(checkpoint, {"basis": basis, "completed_steps": completed, "state": state.model_dump(mode="json")})
        progress("完成规划阶段：" + step)

    state = await engine.run_full_pipeline(
        user_input=brief + f"\n硬性要求：全片总计{seconds}秒，{seconds//5}个5秒镜头。"
                          "同一物理地点和连续时间属于同一个ScriptScene，不能把镜头数当成场次数。"
                          "每场尽量控制在20个剧本块内，保留关键对白。分镜数量与时长约束适用于全片，禁止在每场重复整片镜头数。",
        initial_state=ProjectState.model_validate(saved["state"]) if saved else None,
        completed_steps=completed, on_stage_complete=on_stage)
    write_json(folder / "script_weaver.json", state.model_dump(mode="json"))
    progress("转换为 AIMedia 分镜与 H3 摄影提示词")
    schema = {"title": "中文标题", "synopsis": "完整故事和反转因果链", "style": "English realistic live-action visual style",
              "negative_prompt": "animation, cartoon, plastic skin, text, watermark",
              "speakers": {"中文角色名": {"voice": "苏打或茉莉", "style": "声音与情绪", "appearance": "Stable distinct English facial features, age, outfit"}},
              "shots": [{"title": "中文镜头名", "description": "中文场景、动作和面部微表情", "camera": "景别、角度、运镜、目的",
                         "prompt": "English dynamic cinematography prompt with detailed face, action, lighting, movement, exactly one 5-second shot",
                         "dialogue": [{"speaker": "中文角色名", "text": "一句8—16字中文对白"}]}]}
    story_path = folder / "storyboard.json"
    if story_path.exists():
        story = validate_story(read_json(story_path), seconds)
    else:
        instruction = (f"把以下上游剧本压缩成{seconds//5}个镜头，每个5秒；严格保留原始要求和反转因果链。"
                       "输出且只输出下列结构的JSON，不能添加额外字段。角色3—5位。每镜头至多一句22字符内对白。"
                       "人物首次出场写清外观；之后外观不变。第一镜头中广景看到所有角色和脸，至少一半镜头面部特写。"
                       "画面提示词英文且只写这个镜头出现的人物；对白保持中文。不要静态肖像描述，明确眼神、呼吸、嘴角、手部动作。"
                       "不要用文字展示关键线索。\n结构：" + json.dumps(schema, ensure_ascii=False))
        feedback = ""
        for attempt in range(3):
            response = await client.chat_simple(instruction + feedback, brief + "\n" + state.model_dump_json(ensure_ascii=False))
            try:
                story = validate_story(parse_object(response.content), seconds)
                break
            except (ValueError, KeyError, TypeError) as error:
                feedback = "\n上次输出不合格，请修正：" + str(error)
                if attempt == 2:
                    raise
        write_json(story_path, story)

    dramatic_path = folder / "dramatic_review.json"
    if not dramatic_path.exists():
        progress("检查悬疑反转的铺垫、因果和五秒对白节奏")
        instruction = (
            "你是短片剧本的终审编辑。依据原始要求审查并必要时重写候选剧本。"
            "悬疑反转必须改变已知事实，不能只是轮流指认嫌疑人。每个反转要有可拍摄的前置线索，"
            "后续揭示解释前面的动作或表情；最后一镜必须明确收束核心事件，不能让反派无代价离场。"
            "优先让骗局、证据、身份、动机形成清晰因果链，观众无需读手机或病历上的文字。"
            "人物限定原要求范围，录音、旁白也算发声角色；禁止增加无设定的第五个录音角色。"
            "对白短且自然，一镜最多一句，表情特写有具体变化，一镜只拍一个动作。"
            f"严格{seconds//5}镜，每镜5秒。第一镜看到全部角色的清晰脸，至少一半镜头面部特写。"
            "英文提示词必须写清本镜头出场人的固定外观、衣服和空间位置，镜头之间不改变服装。"
            "只返回JSON：{\"review\":{\"turns\":[{\"setup_shot\":1,\"reveal_shot\":3,"
            "\"cause\":\"中文因果说明\"}],\"resolution\":\"最后如何收束\"},"
            "\"story\":完整候选剧本同字段结构}。story内不得添加其他字段。")
        for attempt in range(3):
            response = await client.chat_simple(instruction, brief + "\n候选剧本：" + json.dumps(story, ensure_ascii=False))
            try:
                revision = parse_object(response.content)
                revised = validate_story(revision["story"], seconds)
                if not isinstance(revision["review"].get("turns"), list):
                    raise ValueError("Missing reversal causality review")
                story = revised
                break
            except (ValueError, KeyError, TypeError) as error:
                instruction += "\n修正上次格式问题：" + str(error)
                if attempt == 2:
                    raise
        write_json(dramatic_path, revision["review"])
        write_json(story_path, story)
        # A rewritten story needs a fresh staging review.
        (folder / "video_claw_review.json").unlink(missing_ok=True)

    review_path = folder / "video_claw_review.json"
    if not review_path.exists():
        progress("VideoClaw：检查人物站位、视线和场景连续性")
        template = (INTEGRATIONS / "video-claw/video-claw/video-claw/backend/prompts/storyboard/staging_continuity_zh.txt").read_text(encoding="utf-8-sig")
        segments = [{"segment_number": i, "scene_context": "同一封闭空间，夜，内景", "scene_space": "内",
                     "shots": [{"shot_number": 1, "content": shot["description"] + "\nCamera: " + shot["camera"]}]} for i, shot in enumerate(story["shots"], 1)]
        prompt = template.format(episode_number=1, episode_title=story["title"],
                                 retry_feedback="只修正必要的不连贯之处，保留全部对白和悬疑反转。", segments=json.dumps(segments, ensure_ascii=False))
        response = await client.chat_simple("请严格按给定规则执行连续性审查，只输出JSON。", prompt)
        review = parse_object(response.content)
        if not isinstance(review.get("patches"), list) or not isinstance(review.get("issues"), list):
            raise ValueError("Invalid VideoClaw continuity result")
        for patch in review["patches"]:
            index = patch["segment_number"] - 1
            if patch.get("shot_number") != 1 or not 0 <= index < len(story["shots"]):
                raise ValueError("Continuity patch points outside storyboard")
            # Include the corrected staging in both editable notes and rendered prompt.
            story["shots"][index]["description"] = patch["content"]
            story["shots"][index]["prompt"] += "\nStaging continuity: " + patch["content"]
        write_json(review_path, review)
        write_json(story_path, validate_story(story, seconds))
    write_json(folder / "manifest.json", {"status": "complete", "duration_seconds": seconds, "shots": len(story["shots"]),
               "sources": read_json(INTEGRATIONS / "sources.json"), "model": config["model"], "usage": usage})
    progress("剧本与分镜已完成，已保存到规划目录")
    return story


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    asyncio.run(plan(args.brief.read_text(encoding="utf-8"), args.output, args.seconds,
                     progress=lambda message: print(message, flush=True)))


if __name__ == "__main__":
    main()
