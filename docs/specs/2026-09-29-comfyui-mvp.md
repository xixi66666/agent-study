# ComfyUI + Seedance 2.5 最小验证（MVP）设计

日期：2026-09-29。状态：已跑通（2026-09-29 17:13），验收记录见 `samples/2026-09-29-seedance25-mvp-run01.md`。
上位文档：docs/实施路线.md（第 2.1 节、第 7 节阶段 A）。

## 目标

在本机（Windows，无 NVIDIA GPU）安装 ComfyUI，通过官方 Partner Node 调用 Seedance 2.5 生成 1 条最短样片，完成阶段 A 的"首个 API 成功调用"。

## 范围

- 安装：git + venv 方式安装到 `D:\AIMedia\ComfyUI`，固定发布版本 v0.37.4（记录 commit 哈希）。
- 运行：CPU 模式，仅 API 节点调用云端生成；不下载本地模型、不做本地推理。
- 工作流：官方 Seedance 2.5 T2V 模板，固定版本保存到 `workflows\comfyui\`。
- 生成：480p / 5 秒 / 无参考素材，参数最小化，验证链路而非画质。
- 记录：调用参数、耗时、费用（Comfy 积分折算）、成片路径，存 `samples\`。

## 非目标

- 不接 n8n、不做脚本化提交（下一个增量）。
- 不做多镜头、参考图、音频方案对比。
- 不做题材与画风决策。

## 环境约束

- 无 NVIDIA GPU（AMD 集显）：ComfyUI 以 `--cpu` 运行。
- C 盘剩余空间紧张（约 6GB）：pip 缓存、临时目录、ComfyUI 全部放 D 盘。
- Python 3.11.9、git 2.36.1；GitHub / PyPI / PyTorch CPU 源均已验证可达。

## 验收标准

1. ComfyUI Web UI 本机可访问（127.0.0.1:8188），Seedance（bytedance）节点在 `/object_info` 中注册可见。
2. 官方 T2V 模板可在界面加载且校验通过。
3. 生成 1 条样片并转存到 `samples\`。
4. `samples\` 记录含：任务参数、提交与完成时间、耗时、费用、工作流文件名与版本。
5. 工作流 JSON、本 spec、记录均提交到 git。

## 成本

一次 480p/5s 生成约 $0.7–0.8（Comfy 积分计）。需账号已有积分；失败退回政策以 Comfy 账单为准。

## 风险与限制

- Comfy 账号登录、积分与"允许的网络环境"须实际验证；若不可达，本 MVP 停在生成前一步，方舟直连另立增量。
- Partner Node 不暴露供应商任务 ID；后续需要自动对账时再评估最小适配层。
