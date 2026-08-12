---
name: 高动态运镜
description: |
  为 MiniMax H3 图生视频生成高动态运镜 Ref2VA 提示词。基于插件自动加载的参考图（人物、场景、动作、风格），只输出可直接交给 H3 图生视频节点的六段式英文提示词，不生成角色卡或动作首帧文生图提示词。要求两轴位移、主动运镜、前景视差、障碍接触、尺度变化与物理反馈，使用官方镜头指令与自然语言弧线描述。无参考图时允许纯文字描述模式。
trigger-words: [高动态, 高速运镜, 快节奏动作, 追拍, 大景别变化, H3 图生视频, high motion, high-speed]
exported-by: StarAI
---

# 高动态运镜（H3 图生视频提示词）

将插件自动加载的参考图转换为一条完整的 MiniMax H3 图生视频 Ref2VA 提示词。本 Skill 只产出视频提示词，不生成角色卡、不生成动作首帧文生图提示词、不输出分镜表。

## 输入模式

- **有图模式（推荐）**：插件已自动加载 1-6 张参考图。用 `h3-ref2va-contract.md` 的标签规则定义每张图：`<Subject N>` 定义可复用内容（人物、场景、道具、风格），`<Picture N>` 只在图片作为首帧/关键帧锚点时使用。
- **纯文字模式**：没有提供任何参考图时，不得报错或拒绝。改为根据用户文字描述在 `subject_definitions` 中创建主体定义，例如 `<Subject 1> is a ... described by the user as ...`。不出现 `<Picture N>` 首帧锚点，`summary` 使用 `[reference generation]`；只有用户明确提供动作构图描述并希望作为起始画面时，才把该描述声明为起始画面锚点并加 `keyframe completion`。
- 两种模式都不输出角色卡或动作首帧文生图提示词。图片生成任务不在本 Skill 范围内。

## 参考文件

- `references/h3-ref2va-contract.md`：六段式 Ref2VA 结构、标签、保留标记、时间线与声音规则的唯一权威契约。
- `references/high-motion-h3.md`：高动态定义、镜头指令语法、运动密度与因果链、拒绝清单。
- `references/generalized-speed-grammar.md`：运动原型库、镜头模块库、弹性时间分配与高速词汇。

不读取 `visual-case-design.md` 与 `sample-motion-blueprint.md`。除非用户明确要求复刻 hoverboard 样例结构，否则不得套用其固定时间点、起跳、180 度环绕或落地漂移。

## 输出格式

严格按节点格式输出两段：

```text
[视觉分析]
用 2-3 句中文归纳参考图或文字描述中的主体、场景、动作与可用风格锚点。

[最终视频提示词]
英文六段式，字段名与顺序严格固定：
subject_definitions:
...
summary:
...
retention_analysis:
...
detailed_description:
...
overall_soundscape:
...
non_diegetic_music:
...
```

`detailed_description` 必须完整覆盖 H3 需要的构图、主体身份、环境与灯光、动作与状态变化、运镜、同步物理音效，以及参考内容生效的位置。不要为凑字数编造动作，时间可行性优先。

## 高动态硬性要求

每一条提示词必须同时满足：

1. 主体至少沿两个轴位移：前进+下降、侧移+上升、前进+横向旋转/压弯等。
2. 主体视在尺度或机位距离发生明显变化：充满画面、拉开、贴近镜头掠过、快速改变距离。
3. 前景结构、线缆、栏杆、碎片或粒子横穿画面，形成快速视差。
4. 主体与物理元素互动：穿门、越障、擦轨、绕车、撞面、偏转推力、超越车辆、擦肩而过。
5. 加速/减速可见：身体压缩、推力形态、尾流畸变、火花、扬尘、雨水剥离、冲击波、衣物/发丝滞后。
6. 镜头主动追拍：推近、拉开、横移、升降、变侧、变距离、跟随压弯，不得只是居中静止或匀速平行跟拍。

每个节拍写出因果链：`主体发力/动作 → 身体或装备响应 → 环境反应 → 镜头响应`。使用速度对比，禁止整条匀速平行跟拍。

## 镜头指令语法

- 官方括号指令：`[Truck left]`、`[Truck right]`、`[Pan left]`、`[Pan right]`、`[Push in]`、`[Pull out]`、`[Pedestal up]`、`[Pedestal down]`、`[Tilt up]`、`[Tilt down]`、`[Zoom in]`、`[Zoom out]`、`[Shake]`、`[Tracking shot]`、`[Static shot]`。
- 同时指令写进同一括号并用逗号分隔，如 `[Tracking shot,Push in]`；一个括号最多 3 个；不同时间点使用不同指令组。
- 高动态模式禁用 `[Static shot]`，禁止同时推近+拉开等相反指令。
- 弧线、环绕、摇臂、翻转、贴近掠过等无官方指令的运镜用自然英文描述，不得编造不存在的括号指令。
- 至少安排 2-3 组顺序镜头指令，覆盖追拍、变向和收尾。

## 时间分配

按视频时长分配节拍，不套固定时间戳：

- 约 5 秒：3 拍，0.0-0.5 立即进入高速，中段一次复合穿越或变向，结尾一个决定性空间收束。
- 6-8 秒：3-4 拍，允许一次额外反转、障碍或环境揭示。
- 约 10 秒：4-5 拍，包含一次大的速度对比和一次环境过渡。

## 时间线与声音

- `[Shot 1]` 开头不写 `At` 切割时间；后续镜头用 `At MM:SS.mmm` 严格递增且不超出总时长。
- 若以 `<Picture 1>` 为起始锚点，明确写出 `the shot begins from <Picture 1>`。
- 对话/歌词用 `<d>[语言] ...</d>` 并保留原语言；说话人用稳定的 `(S1)`、`(S2)` 标识。
- `detailed_description` 放同步对话、人声和镜头内声音事件；`overall_soundscape` 放持续环境与物理动作声；`non_diegetic_music` 只放观众可闻配乐，写明乐器、速度、节奏与动态，缺失时写 `N/A`。三部分不得互相重复。

## 自查清单（输出前逐项通过）

- 六字段各出现一次且顺序严格固定。
- 所有标签在 `subject_definitions` 定义后再使用，全程含义一致。
- `summary` 任务类型与输入模式一致：纯文字参考为 `[reference generation]`；有图首帧锚点为 `[keyframe completion + reference generation]`。
- 每个标签在 `retention_analysis` 恰好一行，使用固定标记（`fully_preserved`、`partially_preserved`、`attribute_transfer`、`weak_reference`；音频用 `fully_copy`、`partially_copy`、`reference`、`weak_reference`）。
- `detailed_description` 以 `[Shot 1]` 开场，`[Shot 1]` 无 `At` 时间戳，后续镜头时间递增且在时长内。
- 至少两组顺序官方镜头指令；无 `[Static shot]`；单括号不超过 3 个指令。
- 满足六项高动态硬性要求：两轴位移、尺度变化、前景视差、障碍接触、可见加速度、主动镜头。
- 因果链完整：动作 → 身体/装备响应 → 环境反应 → 镜头响应。
- 至少 3 个明确时间点覆盖开始、穿越与收束。
- `overall_soundscape` 与 `non_diegetic_music` 不重复对话，二者互不重复。
- 结尾从开头状态在给定时长内可实现，不用静态手势或眨眼充当收尾。
- 有图模式只用插件提供的参考图；纯文字模式以用户描述为准创建主体，不编造未描述的细节。
