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
| `api_key` | API Key（密码显示，也可以设置环境变量 `SKILLBRIDGE_API_KEY`） |

图片输入：

```text
Load Image → image_1
Load Image → image_2
Image Batch → images
```

初始显示 4 个直接图片接口，连接最后一个可见接口后会自动出现下一个，最多 64 个；超量请用 `images` 批次接口。`video` 接收视频帧序列，按固定 8 帧、间隔 1 帧采样。

系统代理默认不继承；如需代理请自行在代码中配置，本节点不内置代理参数。

## Skill

`SKILL.md` 放在插件目录的 `skills/<技能名>/SKILL.md`，或旧目录 `ComfyUI-SkillBridge/skills/<技能名>/SKILL.md`，节点会自动扫描并在 `skill` 下拉框中列出。

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