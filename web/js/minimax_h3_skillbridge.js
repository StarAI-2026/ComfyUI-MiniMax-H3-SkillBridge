import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const NODE_TYPE = "StariAI-MiniMaxH3-Skill";
const CHAT_NODE_TYPE = "StariAI-MiniMaxH3-Chat";
const INITIAL_VISIBLE_PORTS = 1;
const MAX_IMAGE_PORTS = 6;
const INPUT_LABELS = {
  skill: "技能",
  user_prompt: "用户要求",
  api_base: "API 地址",
  model: "云端模型",
  api_key: "API 密钥",
  images: "多图输入",
  video: "视频输入",
  run_mode: "运行模式",
  conversation_action: "对话操作",
  conversation_state: "会话状态",
  video_duration: "视频时长（秒）",
  cut_count: "切镜数量",
};

function applyInputLabels(node) {
  (node.inputs || []).forEach((input) => {
    const label = /^image_\d+$/.test(input.name)
      ? `参考图片 ${input.name.slice(6)}`
      : INPUT_LABELS[input.name];
    if (label) input.label = label;
  });
}

function imageInputs(node) {
  return (node.inputs || [])
    .filter((input) => /^image_\d+$/.test(input.name))
    .sort((a, b) => Number(a.name.slice(6)) - Number(b.name.slice(6)));
}

function imageIndex(input) {
  return Number(input.name.slice(6));
}

function moveImageBeforeOtherInputs(node, input) {
  const currentIndex = node.inputs.indexOf(input);
  const firstOtherIndex = node.inputs.findIndex(
    (candidate) => !/^image_\d+$/.test(candidate.name)
  );
  if (currentIndex >= 0 && firstOtherIndex >= 0 && currentIndex > firstOtherIndex) {
    node.inputs.splice(currentIndex, 1);
    node.inputs.splice(firstOtherIndex, 0, input);
  }
}

function addImageInput(node, index) {
  if (index > MAX_IMAGE_PORTS || imageInputs(node).some((input) => input.name === `image_${index}`)) {
    return false;
  }
  const input = node.addInput(`image_${index}`, "IMAGE");
  input.label = `参考图片 ${index}`;
  moveImageBeforeOtherInputs(node, input);
  return true;
}

function trimUnusedImageInputs(node) {
  const inputs = imageInputs(node);
  const highestConnected = inputs.reduce(
    (highest, input) => (input.link != null ? Math.max(highest, imageIndex(input)) : highest),
    0
  );
  const requiredCount = Math.min(
    MAX_IMAGE_PORTS,
    Math.max(INITIAL_VISIBLE_PORTS, highestConnected + 1)
  );

  for (let index = inputs.length; index > requiredCount; index -= 1) {
    const input = inputs.find((candidate) => imageIndex(candidate) === index);
    if (input && input.link == null) {
      node.removeInput(node.inputs.indexOf(input));
    }
  }

  for (let index = inputs.length + 1; index <= requiredCount; index += 1) {
    addImageInput(node, index);
  }
}

function updateDynamicImageInputs(node) {
  if (!node || (node.type !== NODE_TYPE && node.type !== CHAT_NODE_TYPE)) return;
  applyInputLabels(node);
  const inputs = imageInputs(node);
  const highestConnected = inputs.reduce(
    (highest, input) => (input.link != null ? Math.max(highest, imageIndex(input)) : highest),
    0
  );
  const requiredCount = Math.min(
    MAX_IMAGE_PORTS,
    Math.max(INITIAL_VISIBLE_PORTS, highestConnected + 1)
  );

  for (let index = inputs.length + 1; index <= requiredCount; index += 1) {
    addImageInput(node, index);
  }

  trimUnusedImageInputs(node);
  node.setSize(node.computeSize());
  if (typeof node.setDirtyCanvas === "function") node.setDirtyCanvas(true, true);
}

// Make the API key widget a one-time, masked input that is never written to the
// workflow JSON. widget.serialize=false skips workflow persistence (LGraphNode
// serialize/configure) but keeps options.serialize at its default true so the
// value is still sent to the backend on each queue.
function configureApiKeyWidget(node) {
  const widget = (node.widgets || []).find((w) => w.name === "api_key");
  if (!widget) return;
  widget.serialize = false;
  widget.options = widget.options || {};
  widget.options.serialize = true;
  if (widget.inputEl) widget.inputEl.type = "password";
  widget.value = "";
}

function getWidget(node, name) {
  if (!node) return undefined;
  return (node.widgets || []).find((widget) => widget.name === name);
}

function setWidgetValue(node, name, value) {
  const widget = getWidget(node, name);
  if (!widget) return;
  widget.value = value;
  widget.callback?.(value);
}

function parseState(node) {
  const widget = getWidget(node, "conversation_state");
  if (!widget || typeof widget.value !== "string") return {};
  try {
    return JSON.parse(widget.value || "{}");
  } catch {
    return {};
  }
}

function formatConversationView(state, view = null) {
  if (view && typeof view === "object") {
    const turns = Array.isArray(state?.turns) ? state.turns : [];
    const current = view.current_result || "";
    const analysis = view.analysis || "";
    const lines = turns.map((turn, index) => {
      return [
        `第 ${index + 1} 轮`,
        `用户：${turn.user || ""}`,
        `视觉分析：${turn.analysis || ""}`,
        `提示词：${turn.prompt || current || ""}`,
      ].join("\n");
    });
    if (analysis && !lines.length) lines.push(`视觉分析：${analysis}`);
    if (state?.confirmed_prompt) {
      lines.push(`\n已确认最终提示词：\n${state.confirmed_prompt}`);
    }
    return lines.join("\n\n") || "等待输入创作要求后开始对话。";
  }

  const turns = Array.isArray(state?.turns) ? state.turns : [];
  if (!turns.length) return "等待输入创作要求后开始对话。";
  return turns.map((turn, index) => [
    `第 ${index + 1} 轮`,
    `用户：${turn.user || ""}`,
    `视觉分析：${turn.analysis || ""}`,
    `提示词：${turn.prompt || ""}`,
  ].join("\n")).join("\n\n");
}

function configureConversationState(node) {
  const widget = getWidget(node, "conversation_state");
  if (!widget) return;
  widget.options = widget.options || {};
  widget.options.serialize = true;
  widget.type = "hidden";
  widget.computeSize = () => [0, 0];
}

function configureConversationView(node) {
  if (node.__staraiConversationView) return;
  const element = document.createElement("textarea");
  element.readOnly = true;
  element.placeholder = "对话结果会显示在这里";
  element.style.resize = "vertical";
  element.style.background = "rgba(20, 20, 20, 0.92)";
  element.style.color = "#e8e8e8";
  element.style.border = "1px solid #555";
  element.style.borderRadius = "6px";
  element.style.padding = "8px";
  element.style.fontFamily = "sans-serif";
  element.style.fontSize = "12px";
  element.style.lineHeight = "1.45";
  const widget = node.addDOMWidget("conversation_view", "customtext", element, {
    serialize: false,
    getValue: () => element.value,
    setValue: (value) => {
      element.value = value || "";
    },
    getHeight: () => 190,
    getMinHeight: () => 120,
  });
  widget.label = "对话结果";
  node.__staraiConversationView = { element, widget };
  element.value = formatConversationView(parseState(node));
}

async function queuePartialNode(node) {
  const prompt = await app.graphToPrompt();
  const response = await api.fetchApi("/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: api.clientId,
      prompt: prompt.output,
      partial_execution_targets: [String(node.id)],
      extra_data: { extra_pnginfo: { workflow: prompt.workflow } },
    }),
  });
  if (response.status !== 200) {
    const error = await response.json();
    throw { response: error };
  }
  return response.json();
}

async function runConversation(node, action) {
  setWidgetValue(node, "run_mode", "多轮对话");
  setWidgetValue(node, "conversation_action", action);
  try {
    if (action === "确认并生成") {
      node.__staraiQueueFullWorkflow = true;
      await app.queuePrompt(0, 1);
    } else {
      await queuePartialNode(node);
    }
  } catch (error) {
    console.error("SkillBridge conversation queue failed", error);
    const message = error?.response?.error?.message || error?.message || "提交工作流失败";
    window.alert(`SkillBridge：${message}`);
  } finally {
    node.__staraiQueueFullWorkflow = false;
  }
}

function addConversationControls(node) {
  if (node.__staraiConversationControls) return;
  node.addWidget("button", "发送本轮对话", null, () => runConversation(node, "继续对话"), {
    serialize: false,
  });
  node.addWidget("button", "确认并生成", null, () => runConversation(node, "确认并生成"), {
    serialize: false,
  });
  node.addWidget("button", "清空对话", null, () => runConversation(node, "清空对话"), {
    serialize: false,
  });
  node.__staraiConversationControls = true;
}

function configureConversationNode(node) {
  configureConversationState(node);
  configureConversationView(node);
  addConversationControls(node);
}

function updateConversationOutput(node, output) {
  const stateText = output?.conversation_state?.[0];
  const viewText = output?.conversation_view?.[0];
  if (typeof stateText === "string") setWidgetValue(node, "conversation_state", stateText);
  let state = parseState(node);
  let view = null;
  if (typeof viewText === "string") {
    try {
      view = JSON.parse(viewText);
    } catch {
      view = null;
    }
  }
  if (node.__staraiConversationView?.element) {
    node.__staraiConversationView.element.value = formatConversationView(state, view);
  }
  node.setDirtyCanvas?.(true, true);
}

function findConversationNode() {
  const selected = Object.values(app.canvas?.selected_nodes || {})
    .find((node) => node.type === CHAT_NODE_TYPE);
  if (selected) return selected;
  const nodes = (app.graph?._nodes || []).filter((node) => node.type === CHAT_NODE_TYPE);
  return nodes.length === 1 ? nodes[0] : null;
}

function hasUnselectedConversationMode(nodes) {
  return nodes.some((node) => getWidget(node, "run_mode")?.value === "多轮对话");
}

function installQueueGuard() {
  if (app.__staraiSkillBridgeQueueGuard) return;
  const originalQueuePrompt = app.queuePrompt.bind(app);
  app.queuePrompt = async function (number, batchCount = 1) {
    const conversationNodes = (app.graph?._nodes || []).filter((candidate) => candidate.type === CHAT_NODE_TYPE);
    const node = conversationNodes.find((candidate) => candidate.__staraiQueueFullWorkflow)
      || findConversationNode();
    if (!node && hasUnselectedConversationMode(conversationNodes)) {
      window.alert("SkillBridge：请先选中要运行的多轮对话节点。");
      return true;
    }
    const mode = getWidget(node, "run_mode")?.value;
    const action = getWidget(node, "conversation_action")?.value;
    if (node && !node.__staraiQueueFullWorkflow && mode === "多轮对话" && (action === "继续对话" || action === "清空对话")) {
      try {
        for (let index = 0; index < batchCount; index += 1) {
          await queuePartialNode(node);
        }
      } catch (error) {
        console.error("SkillBridge partial queue failed", error);
        const message = error?.response?.error?.message || error?.message || "提交对话失败";
        window.alert(`SkillBridge：${message}`);
      }
      return true;
    }
    return originalQueuePrompt(number, batchCount);
  };
  app.__staraiSkillBridgeQueueGuard = true;
}

app.registerExtension({
  name: "MiniMaxH3.SkillBridge.DynamicImages",
  setup() {
    installQueueGuard();
  },
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE && nodeData.name !== CHAT_NODE_TYPE) return;

    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = originalCreated?.apply(this, arguments);
      queueMicrotask(() => {
        updateDynamicImageInputs(this);
        configureApiKeyWidget(this);
        if (this.type === CHAT_NODE_TYPE) configureConversationNode(this);
      });
      return result;
    };

    if (nodeData.name === CHAT_NODE_TYPE) {
      const originalExecuted = nodeType.prototype.onExecuted;
      nodeType.prototype.onExecuted = function (output) {
        originalExecuted?.apply(this, arguments);
        updateConversationOutput(this, output);
      };
    }

    const originalConnections = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function () {
      const result = originalConnections?.apply(this, arguments);
      queueMicrotask(() => updateDynamicImageInputs(this));
      return result;
    };
  },

  loadedGraphNode(node) {
    if (node?.type === NODE_TYPE) {
      queueMicrotask(() => {
        updateDynamicImageInputs(node);
        configureApiKeyWidget(node);
      });
    }
    if (node?.type === CHAT_NODE_TYPE) {
      queueMicrotask(() => {
        updateDynamicImageInputs(node);
        configureApiKeyWidget(node);
        configureConversationNode(node);
        const state = parseState(node);
        if (node.__staraiConversationView?.element) {
          node.__staraiConversationView.element.value = formatConversationView(state);
        }
      });
    }
  },
});
