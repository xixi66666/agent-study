# Seedance 2.5 MVP 样片记录 01

日期：2026-09-29。目的：阶段 A"首个 API 成功调用"，验证 ComfyUI Partner Node 全链路（提交 → 云端生成 → 下载 → 保存）。

## 参数

- 模型：Seedance 2.5（Comfy Partner Node，`ByteDance2TextToVideoNode`）
- 分辨率：480p；比例：9:16；时长：5 秒；生成音频：true
- 输出格式：mp4；水印：false；种子：1324629973（randomize）
- 提示词：模板自带演示词（西部喜剧：两只劫匪遇到戴警长帽的羊驼，慢动作、莫里康内风格配乐）
- 工作流：`workflows/comfyui/api_seedance2_5_t2v.json`
  - 来源：官方模板包 `comfyui-workflow-templates==0.11.69` / `comfyui-workflow-templates-json==0.1.95`
  - 本地改动：分辨率 720p→480p、比例 16:9→9:16（其余与官方一致）

## 环境

- ComfyUI v0.37.4（git 源码归档，CPU 模式，Windows）
- 前端 comfyui-frontend-package 1.52.7；Python 3.11.9 venv；PyTorch 2.14.0（CPU）
- 调用通道：Comfy 账号积分（Partner Node），服务 127.0.0.1:8188

## 结果

- prompt_id：402cf646-9a46-402c-88e9-030f45ec05d3；状态：success
- 成片：`samples/videos/2026-09-29_seedance25_t2v_480p_9x16_5s.mp4`
  - SHA256：2ED9C3B6671957F3526DB5FF83491651D6283EFCA6ED61388650C286DCA1CD0D
  - 规格实测：480×854、24fps、5.056s、H.264 + AAC（32kHz）
- 时间：提交 17:07:46 → 完成 17:13:15（本地时间），端到端耗时 328.6 秒
- 费用：156.38 credits ≈ $0.74（按公开换算口径估算，以 Comfy 账单为准）

## 发现与备注

- 节点标题显示"ByteDance Seedance 2.0 文本生成视频"为中文翻译未更新；实际以「模型」控件 `Seedance 2.5` 为准
- 节点内显示的预计剩余时间明显偏短（实际约 5.5 分钟），后续自动化按 5–8 分钟/条安排等待窗口
- Partner Node 不返回供应商任务 ID；`draft_task_id` 仅在 Draft 模型下输出
- 后续可选：改用 `Seedance 2.5 Draft`（480p 预览 + draft_task_id 转 1080p 终稿）省钱，待验证
