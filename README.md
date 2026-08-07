# StarAI-SkillBridge

ComfyUI 节点：结合本地 `SKILL.md` 规则、图片/视频参考和用户要求，调用 OpenAI 兼容的云端视觉模型生成视频提示词。

## 特性

- 自动发现本地 `SKILL.md`，把技能规则注入系统提示词
- `image_1` 至 `image_64` 动态图片输入，连接后逐个增加
- 支持 `images` 批次输入与 `video` 视频帧输入
- 调用 OpenAI 兼容的 Chat Completions 接口（支持视觉参数）
- 输出分为「视觉分析」和「最终视频提示词」两段

## 安装

把 `StarAI-SkillBridge` 目录放到 ComfyUI 的 `custom_nodes` 下，开启依赖：

```bash
pip install -r requirements.txt
```

重启 ComfyUI 后，在节点搜索框输入 `StarAI SkillBridge`。

## 使用

节点参数：

| 参数 | 说明 |
| --- | --- |
| `skill` | 使用的 `SKILL.md` 技能名 |
| `user_prompt` | 用户要求 |
| `api_base` | OpenAI 兼容接口地址，例如 `https://your-provider/v1` |
| `model` | 服务商实际的视觉模型名 |

## API Key 安全配置

为避免分享工作流时泄露密钥，节点**不提供** `api_key` 输入框，改为从以下任一来源读取：

1. 复制 `.env.example` 为插件目录下的 `.env`，填入 `SKILLBRIDGE_API_KEY`；`.env` 已被 `.gitignore` 排除，不会提交或随工作流分享。
2. 或设置系统环境变量 `SKILLBRIDGE_API_KEY`。

```bash
# .env 方式（插件目录下）
SKILLBRIDGE_API_KEY=your_api_key_here
```

```powershell
# 或环境变量方式（Windows PowerShell）
$env:SKILLBRIDGE_API_KEY="your_api_key_here"
```

API Key 只从环境/本地文件读取，**不会写入工作流 JSON**，因此分享工作流不会泄露密钥。

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