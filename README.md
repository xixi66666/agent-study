# AIMedia — AI 自媒体自动化管线

面向个人账号（后续可扩展）的 AI 视频自动化：**内容计划 → 视频生成 → 配音/字幕 → 合成 → 质检 → 全自动发布 → 数据回收**。

当前状态（2026-09-29）：**MVP 已跑通** —— ComfyUI 安装完成，通过官方 Partner Node 调用 Seedance 2.5 生成第一条样片（480p / 9:16 / 5s），参数、耗时、费用、成片全部存档。

- 完整方案（需求、架构、阶段计划、发布、成本、合规）：[`docs/实施路线.md`](docs/实施路线.md)
- MVP 设计与验收：[`docs/specs/2026-09-29-comfyui-mvp.md`](docs/specs/2026-09-29-comfyui-mvp.md)
- 首条样片记录：[`samples/2026-09-29-seedance25-mvp-run01.md`](samples/2026-09-29-seedance25-mvp-run01.md)

本机本地生成已跑通（2026-10-04）：Wan 2.2 TI2V 5B 在 RX 9070 XT 上生成六段约 5 秒的视频，拼接得到 30.25 秒的《竹林里的金色落叶》无声短片。启动 `start-comfyui-gpu.cmd` 后，运行 `generate-video.cmd` 可创建新批次。每次生成独立保存到 `runs/<批次名称>/`。剧本、参数、断点继续和目录约定见 [`docs/本地视频生产.md`](docs/本地视频生产.md)，安装记录见 [`docs/本机环境.md`](docs/本机环境.md)，本地成片验收见 [`samples/2026-10-04-wan22-local-run01.md`](samples/2026-10-04-wan22-local-run01.md)。

一分钟猫咪动画已完成验收（2026-10-04）：原创《小鱼饼失踪案》包含十二段本地生成画面、MiMo 双角色配音和同步中文字幕，成片为 480×832、24fps、60 秒。启动 GPU 服务后，运行 `generate-cat-comic.cmd` 可生成新批次。使用与修稿见 [`docs/配音字幕与猫咪动画.md`](docs/配音字幕与猫咪动画.md)，成片验收见 [`samples/2026-10-04-cat-comic-run01.md`](samples/2026-10-04-cat-comic-run01.md)。

本机操作台：双击 **`start-studio.cmd`**，打开 **http://127.0.0.1:8190**。一级总控台统一管理全部作品、全局任务、共享素材、成片版本与引擎状态；进入作品后，在二级制作台编辑剧本、角色、分镜、对白和字幕，逐镜头重做、试听、合成与导出。支持草稿历史、素材复用和任务恢复。ComfyUI 作为本地生成引擎，并嵌入高级节点工作区。使用与集成范围见 [`docs/操作台.md`](docs/操作台.md)。

当前本机默认使用 H3（2026-10-06）：Script-Weaver 已接入自动编剧与分镜，VideoClaw 连续性审查规则已接入站位、视线和物件检查。H3 同步生成画面和原生声音，再拼接并烧录中文字幕。Wan 两套模型已按用户要求移除，历史成片保留。使用范围和目录见 [`docs/H3自动编剧与制作.md`](docs/H3自动编剧与制作.md)。

H3 一分钟悬疑样片《死亡证明》已完成（2026-10-06）：四位写实人物、十二镜、原生中文对白和中文字幕，768×448、24fps、60 秒。成片与验证记录见 [`samples/2026-10-06-h3-suspense-run01.md`](samples/2026-10-06-h3-suspense-run01.md)。

Fun Camera 运镜已接入（2026-10-04）：模型从魔搭下载并校验，操作台可选择 9 种相机运动预设、调节速度、固定种子比较效果。RX 9070 XT 已验证推近与固定两版猫咪视频，均为 384×640、16fps、5 秒；单段实测约 4～6 分钟。配套模型、调试步骤与限制见 [`docs/操作台.md`](docs/操作台.md#fun-camera-运镜调试)，验收记录见 [`samples/2026-10-04-fun-camera-run01.md`](samples/2026-10-04-fun-camera-run01.md)。

---

## 1. 样片档案（已验证）

| 项目 | 值 |
| --- | --- |
| 模型 | Seedance 2.5（Comfy 官方 Partner Node） |
| 参数 | 480p / 9:16 / 5 秒 / 生成音频 / mp4 / 无水印 |
| 成片 | [`samples/videos/2026-09-29_seedance25_t2v_480p_9x16_5s.mp4`](samples/videos/2026-09-29_seedance25_t2v_480p_9x16_5s.mp4) |
| 规格实测 | 480×854、24fps、5.056s、H.264 + AAC（32kHz） |
| 端到端耗时 | 5 分 29 秒（提交 17:07:46 → 完成 17:13:15） |
| 费用 | 156.38 credits ≈ $0.74（以 Comfy 账单为准） |
| SHA256 | 2ED9C3B6671957F3526DB5FF83491651D6283EFCA6ED61388650C286DCA1CD0D |

关键结论：**生成全部在云端完成，本地机器不需要独立显卡**（本 MVP 在一台无独显的机器上以 CPU 模式验证通过），因此复现门槛很低。

## 2. 仓库结构

```text
AIMedia/
├─ README.md                              ← 本文件：完整复现与迁移说明
├─ docs/
│  ├─ 实施路线.md                          ← 完整方案（架构/阶段/发布/成本/合规）
│  └─ specs/
│     └─ 2026-09-29-comfyui-mvp.md         ← MVP 设计、范围和验收标准
├─ workflows/comfyui/
│  ├─ api_seedance2_5_t2v.json             ← 云端 MVP 工作流
│  └─ local_wan22_5b_t2v.json              ← 本地 Wan 2.2 工作流
├─ config/local_video.json                ← 本地视频参数
├─ config/cat_comic_video.json             ← 一分钟猫咪动画参数
├─ config/fun_camera_video.json            ← Fun Camera 运镜采样与配套模型参数
├─ config/mimo_tts.json                    ← 配音与字幕参数（不含密钥）
├─ prompts/stories/                       ← 剧本和分镜
├─ prompts/assets/                        ← 角色与关键场景参考图
├─ services/media/produce_video.py        ← 分段生成与拼接
├─ services/media/download_fun_camera.py  ← 魔搭下载、校验与图像编码器转换
├─ services/media/add_dialogue.py         ← MiMo 配音、字幕时间轴与成片合成
├─ services/studio/                       ← 本地操作台后端、网页和启动器
├─ workspace/                             ← 作品草稿、修改历史、上传素材和任务记录（不进入 Git）
├─ runs/                                 ← 按批次归档的片段、日志、成片（不进入 Git）
├─ start-studio.cmd                       ← 启动操作台及 GPU 引擎
├─ start-comfyui-gpu.cmd                  ← 启动本地 GPU 服务
├─ generate-video.cmd                    ← 创建一条新视频
├─ generate-cat-comic.cmd                 ← 创建带配音和字幕的猫咪动画
├─ samples/
│  ├─ 2026-09-29-seedance25-mvp-run01.md   ← 样片验收记录
│  └─ videos/
│     └─ 2026-09-29_seedance25_t2v_480p_9x16_5s.mp4
└─ .gitignore
```

说明：**ComfyUI 本体不进入 Git**（体积大、需随版本更新），安装到 `AIMedia\ComfyUI\`（已被 `.gitignore` 排除）。本地重复生成的完整目录约定见 `docs/本地视频生产.md`；后续管线规划见 `docs/实施路线.md` 第 9 节。

## 3. 复现（任意 Windows 机器，CPU 即可）

> 以下命令均为 PowerShell（Windows 10/11 自带）。实测环境：Windows + Python 3.11.9 + git 2.36。

### 3.1 前置

```powershell
git --version        # 需要 git
python --version     # 需要 Python >= 3.10（实测 3.11.9）
```

### 3.2 取本仓库

```powershell
git clone https://github.com/xixi66666/agent-study.git AIMedia
cd AIMedia
New-Item -ItemType Directory -Force .cache | Out-Null
```

### 3.3 安装 ComfyUI（固定 v0.37.4）

国内直连 github.com 可能超时，推荐走官方 codeload 压缩包（已实测）：

```powershell
curl.exe -L --retry 3 -o .cache\comfyui-v0.37.4.tar.gz "https://codeload.github.com/comfyanonymous/ComfyUI/tar.gz/refs/tags/v0.37.4"
tar -xzf .cache\comfyui-v0.37.4.tar.gz
Rename-Item ComfyUI-0.37.4 ComfyUI
# 网络好的情况也可以用：git clone --depth 1 --branch v0.37.4 https://github.com/comfyanonymous/ComfyUI.git ComfyUI
```

### 3.4 Python 环境（venv + 清华源）

```powershell
python -m venv ComfyUI\.venv
$py = "ComfyUI\.venv\Scripts\python.exe"

# 升级 pip
& $py -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

# PyTorch（Windows 上 PyPI 版即 CPU 版；实测 torch 2.14.0）
& $py -m pip install torch torchvision torchaudio -i https://pypi.tuna.tsinghua.edu.cn/simple

# 其余依赖（实测可用；见下方说明为何要剔除一行）
$req = (Get-Content ComfyUI\requirements.txt) | Where-Object { $_ -notmatch '^comfyui-workflow-templates==' }
$req | Set-Content .cache\requirements-no-templates.txt -Encoding UTF8
& $py -m pip install -r .cache\requirements-no-templates.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**关于 `comfyui-workflow-templates`**：该元包会连带下载约 **934MB** 的模板预览媒体包，且清华源缺其中 `media-assets-02`。本仓库已把需要的工作流 JSON 提取好（`workflows/comfyui/`），所以**不装它也能跑**。若想要 UI 里的模板浏览器，再执行（会下载约 0.9GB）：

```powershell
& $py -m pip install comfyui-workflow-templates==0.11.69 -i https://pypi.tuna.tsinghua.edu.cn/simple --extra-index-url https://pypi.org/simple
```

### 3.5 启动、登录

```powershell
# 启动（CPU 模式；有 AMD ROCm 见第 4 节）
cd ComfyUI
.\.venv\Scripts\python.exe main.py --cpu --listen 127.0.0.1 --port 8188
```

浏览器打开 `http://127.0.0.1:8188`：

1. 右上角**注册/登录 Comfy 账号**（Partner Node 按账号积分计费；充值入口在 comfy.org，积分也可用于 Comfy Desktop 的 Partner Nodes）
2. 节点生成在云端，全程不需要本地 GPU

### 3.6 跑一条样片

1. 把 `workflows/comfyui/api_seedance2_5_t2v.json` 拖进页面（或菜单 Workflow → Open）
2. 确认参数：模型 `Seedance 2.5`、分辨率 `480p`、比例 `9:16`、时长 `5`、生成音频 `true`
3. 点 **Run**，等待约 5–8 分钟（云端排队 + 生成；节点内显示的预计剩余时间不准）
4. 产物位置：`ComfyUI/output/video/Seedance2.5_t2v_00001_.mp4`

**下载成片的三种方式**：

- UI 里视频预览面板右上角下载按钮
- 浏览器直接打开（已验证可用）：
  `http://127.0.0.1:8188/view?filename=Seedance2.5_t2v_00001_.mp4&subfolder=video&type=output`
- 直接去磁盘复制：`AIMedia\ComfyUI\output\video\`

> 若在别的电脑上远程操作该机器：上面链接下载到的是"远程机"的磁盘；拿回本地请用远程软件的互传功能。

### 3.7 已知坑（都实测过）

- 节点标题显示"ByteDance Seedance **2.0** 文本生成视频"是**界面中文翻译未更新**，实际模型以「模型」下拉框为准（本次实测是 `Seedance 2.5`）
- Partner Node 不返回供应商任务 ID；`draft_task_id` 只有 `Seedance 2.5 Draft` 模型才有
- 失败不计费政策以 Comfy 账单页为准；重复运行前先在草案档（480p）验证提示词
- `git clone` github.com 超时时改用 codeload 压缩包；pip 慢时统一加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`

## 4. 迁移到 9950X3D + RX 9070 XT（16GB）+ 96GB 内存

两种玩法可以在同一台机器、同一个 ComfyUI 里共存：

| 路线 | 用途 | 成本 | 质量 |
| --- | --- | --- | --- |
| A. API（Seedance 2.5 等） | 定稿、正式样片 | 按次付费（480p/5s ≈ $0.74） | 商业级（原生音频、30s 长镜） |
| B. 本地模型（Wan 2.2 等） | 免费抽卡、草稿、B-roll、封面 | 电费 | 差一档（无原生音频，需另配 TTS） |

### 4.1 方案 A：API 路线（先照第 3 节跑通）

与第 3 节完全相同，唯一区别：这台机器有显卡，ComfyUI 可以不用 `--cpu`（走 ROCm 时用下面 4.2 的方式装 torch），但**调用云端 Partner Node 时依然不需要本地算力**。

### 4.2 方案 B：本地视频模型（ROCm）

9070 XT 属于官方支持范围，2026 年 AMD 在 Windows 上的 ROCm 已可用：

**最省事**：装 ComfyUI Desktop v0.7.0+，安装时选择 AMD ROCm（官方版基于 ROCm 7.1.1，Desktop / portable / git 三个版本都支持）。

**与仓库一致的手动方式**（下载源码包到 `ComfyUI\`，替换 torch 安装）：

```powershell
python -m venv ComfyUI\.venv
$py = "ComfyUI\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip

# AMD 官方 ROCm wheels（gfx1201 = RX 9000 系列）。版本会滚动，以 AMD 官方文档为准
& $py -m pip install --index-url https://repo.amd.com/rocm/whl-multi-arch/ `
  "torch[device-gfx1201]==2.12.0+rocm7.14.0" `
  "torchvision[device-gfx1201]==0.27.0+rocm7.14.0" `
  "torchaudio==2.11.0+rocm7.14.0"

& $py -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # 期望 True

# 其余依赖同上（3.4 的过滤版 requirements）
# 启动（16GB 显存建议预留 2-3GB 给系统）
.\.venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188 --reserve-vram 3
```

**推荐的本地模型（16GB 显存）**：

| 模型 | 文件 | 说明 |
| --- | --- | --- |
| **Wan 2.2 TI2V-5B**（首选） | Q8_0 GGUF ≈5.4GB / FP16 10GB | 文生+图生视频，720p@24fps、5s 片段；8GB 显存即可跑 |
| Wan 2.2 14B（质量档） | GGUF Q5_K_M 10.8GB×2（两个专家） | 720p 可跑（社区实测），更慢 |
| LTX 系列 | 视版本 | 出片更快、显存占用更低，适合快速抽卡 |

放置与工作流按 ComfyUI 官方 Wan2.2 教程操作（`models/diffusion_models/`、`models/text_encoders/`、`models/vae/`；GGUF 需装 ComfyUI-GGUF 自定义节点）。先用 **480p 长边**抽卡，选中再拉高分辨率。

**预期**：单条 5s 720p 几分钟级（类似 4090 的官方基线还要慢一些）；Windows ROCm 仍处于快速迭代阶段，遇到问题可换 Linux/WSL2（AMD 官方指南以 Ubuntu 为基准，9070 XT 在官方测试列表内）。

### 4.3 两条线怎么分工（建议）

1. 本地 Wan 2.2 **免费迭代提示词**（每次 480p 抽 3-5 个版本）
2. 定稿用 Seedance 2.5（480p 草案 → 需要时 1080p/30s）
3. 封面/参考图用本地图像模型（Z-Image、Flux 量化版在 16GB 上都很顺）
4. 所有费用记到 `samples/`，按 `docs/实施路线.md` 第 5 节的预算规则执行

### 4.4 硬件与系统注意

- 96GB 内存是优势：可放心用 CPU offload（T5 文本编码器等）
- 页面文件放有空间的 SSD（模型 offload 会吃大量内存+页面文件）
- 系统盘别塞满；模型目录建议放 D 盘
- 同一条 5s 片段别同时开多任务，16GB 显存会互相挤

## 5. 成本与模型对比（2026-09 快照）

| 模型 / 档位 | 渠道 | 价格（每秒） | 30 秒成片约 | 备注 |
| --- | --- | --- | --- | --- |
| **Seedance 2.5** | Comfy 节点（本仓库路线） | 480p/5s 实测 **156.38 credits ≈ $0.74** | 720p/30s ≈ $9.93 | 30s 单段、原生音频 |
| Seedance 2.5 | 火山方舟直连 | ¥70/百万 tokens（纯文生） | 以计费器为准 | 需实名 + 开通（余额 ≥200 元）；2026-08-07 公测 |
| Seedance 2.0 | Comfy 节点 | — | 720p ≈ $6.49 | 同族省钱档 |
| Wan 3.0 | 阿里云百炼 | ¥0.42–0.6（720P） | ≈¥12.6–18 | 30s 单段、原生音频、失败不计费 |
| Kling 3.0 | 可灵开放平台 | ¥0.6–1.2 | ¥18–36（两段） | 15s 上限 |
| Vidu Q3-turbo | Vidu 开放平台 | ¥0.375（错峰 ¥0.19） | ¥5.6（错峰） | 16s、原生音频 |
| Hailuo 03 | MiniMax | $0.04–0.05（768p） | ≈$1.2–1.5 | 单段短（10s） |
| Veo 3.1 Fast | Gemini API | $0.10–0.12 | ≈$3.6 | 约 8s/段 |
| 本地 Wan 2.2 TI2V-5B | 本机 9070 XT | 0 | 0 | 质量差一档，无原生音频 |

完整对比与选择原则见 [`docs/实施路线.md`](docs/实施路线.md) 第 2.1 节。

## 6. 工作流文件详解（`workflows/comfyui/api_seedance2_5_t2v.json`）

- 来源：官方模板包 `comfyui-workflow-templates==0.11.69` / `comfyui-workflow-templates-json==0.1.95` 中的 `api_seedance2_5_t2v.json`
- 本地改动仅两处：分辨率 `720p → 480p`、比例 `16:9 → 9:16`（其余与官方一致，便于回归）
- 节点链：`ByteDance2TextToVideoNode` → `SaveVideo`
- 关键参数：

| 参数 | 值 | 说明 |
| --- | --- | --- |
| 模型 | Seedance 2.5 | 可选 2.5 Draft（480p 预览+draft_task_id）、2.0 / Fast / Mini |
| prompt | 模板自带演示词 | 换真实文案时替换 |
| 分辨率 / 比例 / 时长 | 480p / 9:16 / 5 | 时长 4–30 秒 |
| 生成音频 | true | 原生音画同生 |
| 种子 | randomize | 复现问题时可固定 |
| 保存前缀 | video/Seedance2.5_t2v | 决定输出路径 `output/video/` |

## 7. 常见问题（FAQ）

**Q：ComfyUI 不是本地软件吗，为什么还要登录？**
A：ComfyUI 本体是本地开源软件。但 Seedance 是闭源云模型，Partner Node 运行时把参数发到 Comfy 云端（api.comfy.org）由字节生成，登录是给云端计费定位账号。本地开源的视频模型（Wan 2.2 等）不需要登录、不花钱。

**Q：显示的是 2.0 还是 2.5？**
A：节点标题的中文翻译滞后显示"2.0"，实际以「模型」下拉框为准（本样片为 Seedance 2.5）。

**Q：没有独立显卡能跑吗？**
A：能。生成在云端，本 MVP 就是无独显机器 CPU 模式验证的。只有"本地模型路线"才需要 16GB 级别显卡。

**Q：生成要多久？**
A：本样片 480p/5s 端到端 5 分 29 秒（含排队）。节点内显示的预计剩余时间不准，按 5–8 分钟规划。

**Q：视频在哪/怎么下载？**
A：`ComfyUI/output/video/` 下；或浏览器打开 `/view?filename=...&subfolder=video&type=output`；或在 UI 预览面板点下载。

**Q：如何省钱？**
A：先 480p 抽卡；用 `Seedance 2.5 Draft`（480p 预览 → 满意后再转 1080p 终稿，待验证）；本地模型做免费迭代。

**Q：密钥/凭据放哪？**
A：一律不进 Git。Comfy 登录在浏览器会话；git 凭据在 Windows 凭据管理器；后续方舟/百炼 Key 用环境变量或凭据存储（见 `docs/实施路线.md` 第 8 节）。

## 8. 路线图（详见 `docs/实施路线.md` 第 7 节）

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| A. 接入验证与样片标准 | 工作流固定、首个 API 调用、3–5 条样片、外观/声音校准 | 进行中（首个调用已完成） |
| B. 单条自动生产闭环 | 自动规划→生成→合成→质检→archive | 未开始 |
| C. 可靠性与预算 | 持久化、防重提交、限并发、预算预留、故障演练 | 未开始 |
| D. 发布与数据回收 | 一个主平台全自动发布 + 指标回收（发布栈届时选型） | 未开始 |
| E. 持续运行与扩量 | 定时生产、异常提醒、成本/质量统计 | 未开始 |

近期可选下一步（按需选择）：

1. 用真实题材跑 3–5 条正式样片，校准画风/声音（阶段 A 验收）
2. 同文案对比 Wan 3.0 / Kling 3.0，按合格率与实际费用定主力模型
3. Python 脚本直调 ComfyUI HTTP API（`extra_data` 带 `api_key_comfy_org`），为 n8n 编排铺路
4. 9950X3D 本地草稿档：ROCm ComfyUI + Wan 2.2 TI2V-5B
5. 方舟直连评估（长期主力候选：原生 task_id、人民币直连）

## 9. 参考链接

- ComfyUI 仓库：https://github.com/comfyanonymous/ComfyUI
- ComfyUI 安装文档：https://docs.comfy.org/installation
- Seedance 2.5 官方工作流介绍：https://blog.comfy.org/p/seedance-25-is-now-available-via
- Comfy Partner Node 定价：https://docs.comfy.org/tutorials/partner-nodes/pricing
- Comfy 积分说明：https://support.comfy.org/articles/5846341390-how-credits-work-in-comfy
- AMD ROCm on Windows（ComfyUI 官方公告）：https://blog.comfy.org/p/official-amd-rocm-support-arrives
- ComfyUI on AMD RX 9000（AMD 官方指南）：https://rocm.blogs.amd.com/artificial-intelligence/comfyui-radeon-9000/README.html
- Wan 2.2 开源仓库：https://github.com/Wan-Video/Wan2.2
- MiniMax H3 魔搭权重：https://modelscope.cn/models/Comfy-Org/MiniMax-H3
- H3 INT8 本机下载、验证工作流与目录说明：[H3 本地部署](docs/H3本地部署.md)
- 火山方舟 Seedance 定价：https://www.volcengine.com/docs/82379/1099320
- 完整参考列表见 `docs/实施路线.md` 第 11 节

---

*资料核验日期：2026-09-29。价格与版本会变化，接入前以各平台控制台为准。*
