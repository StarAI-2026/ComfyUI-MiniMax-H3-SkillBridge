# ComfyUI-MiniMax-H3-SkillBridge

> **作者：StarAI** | ID: `StariAI`

ComfyUI 节点：结合本地 `SKILL.md` 规则（含 MiniMax H3 视频技能）、图片/视频参考和用户要求，调用 OpenAI 兼容的云端视觉模型生成视频提示词。

## 关于作者

- **官网**：https://staraigc.top
- **Bilibili**：https://space.bilibili.com/495356821
- **YouTube**：https://www.youtube.com/@StarAIGC
- **QQ 群**：https://qm.qq.com/q/lge501JeLY

## 特性

- 自动发现本地 `SKILL.md`，把技能规则注入系统提示词
- 内置 MiniMax H3 视频 prompt 写作技能，开箱即用
- `image_1` 至 `image_64` 动态图片输入，连接后逐个增加
- 支持 `images` 批次输入与 `video` 视频帧输入
- 调用 OpenAI 兼容的 Chat Completions 接口（支持视觉参数）
- 输出分为「视觉分析」和「最终视频提示词」两段

## 安装

把 `ComfyUI-MiniMax-H3-SkillBridge` 目录放到 ComfyUI 的 `custom_nodes` 下，开启依赖：

```bash
pip install -r requirements.txt
```

重启 ComfyUI 后，在节点搜索框输入 `MiniMax H3 SkillBridge`。

## 使用

节点参数：

| 参数 | 说明 |
| --- | --- |
| `skill` | 使用的 `SKILL.md` 技能名 |
| `user_prompt` | 用户要求 |
| `api_base` | OpenAI 兼容接口地址，例如 `https://api.openai.com/v1` |
| `model` | 服务商实际的视觉模型名 |

## API Key 配置

节点内置 **「API 密钥」** 输入框，实现一次性、不泄露的密钥输入：

- 输入后显示为 **密码（••••）**，不会明文显示。
- 该输入框设置 `serialize = false`，**不会写入工作流 JSON**，因此分享工作流文件/截图都不会泄露密钥。
- 每次重新加载工作流或刷新页面后需**重新输入**（一次性输入设计）。
- 输入框为空时，自动回退读取环境变量 `SKILLBRIDGE_API_KEY` 或插件目录 `.env` 中的密钥。

```powershell
# 可选：环境变量方式（Windows PowerShell）
$env:SKILLBRIDGE_API_KEY="your_api_key_here"
```

```bash
# 可选：插件目录 .env 方式（复制 .env.example 后填写）
SKILLBRIDGE_API_KEY=your_api_key_here
```

> 节点「API 密钥」输入框的值只存在于当前会话内存，运行时随 API 请求发送，**不落盘、不进工作流**。`.env` 已被 `.gitignore` 排除，不会提交。

图片输入：

```text
Load Image → image_1
Load Image → image_2
Image Batch → images
```

初始显示 4 个直接图片接口，连接最后一个可见接口后会自动出现下一个，最多 64 个；超量请用 `images` 批次接口。`video` 接收视频帧序列，按固定 8 帧、间隔 1 帧采样。

系统代理默认不继承；如需代理请自行在代码中配置，本节点不内置代理参数。

## Skill

节点扫描插件内置的 `skills/` 目录，把每个 `SKILL.md` 作为一条技能规则，在 `skill` 下拉框中列出。

内置技能：

- `3d-animation-short-generator`：3D 动画短片工作流
- `brand-promo-video-generator`：品牌宣传短片
- `co-op-game-intro-generator`：双人合作游戏开场动画
- `h3-prompt-writing`：MiniMax H3 视频提示词写作
- `handdrawn-live-video-generator`：手绘发光动画与实拍融合
- `minimalist-product-ad-generator`：极简产品广告片
- `mv-subtitle-skill-confirmed`：音乐 MV 与歌词字幕
- `paper-collage-explainer-generator`：纸质拼贴科普动画
- `papercraft-stop-motion-explainer`：纸艺定格科普视频

## 输出

- `analysis`：视觉分析
- `result`：最终视频提示词
- `status`：执行状态 JSON
- `model_info`：模型信息 JSON

## 依赖

- `requests`
- `Pillow`
- `numpy`

## License

[MIT](./LICENSE)