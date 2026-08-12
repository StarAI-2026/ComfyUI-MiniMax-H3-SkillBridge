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

const CHAIN_STATUS_EVENT = "stariai_h3_chain_status";

function parseJson(value) {
  if (typeof value !== "string") return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function chainSummary(status) {
  if (!status?.chain_id) return "";
  const total = status.segment_count ?? 0;
  const accepted = status.accepted_count ?? 0;
  const current = status.current_segment_index ?? accepted;
  const label = {
    planned: "规划中",
    running: "运行中",
    scheduling: "排队中",
    pausing: "正在暂停",
    paused: "已暂停",
    cancelled: "已取消",
    completed: "已完成",
    composing: "正在合成最终视频",
    failed: "失败",
    detached: "需要恢复",
  }[status.state] || status.state;
  return `H3 自动续写：${label}，第 ${Math.min(current + 1, total)}/${total} 段，已完成 ${accepted} 段`;
}

function configureH3ChainStatus(node) {
  if (node.__staraiH3ChainStatus) return;
  node.__staraiH3ChainStatus = { element: null, widget: null, chainId: "" };
}

function ensureH3ChainStatusWidget(node) {
  if (node.__staraiH3ChainStatus?.widget) return node.__staraiH3ChainStatus;
  const element = document.createElement("div");
  element.style.minHeight = "0px";
  element.style.fontFamily = "sans-serif";
  element.style.fontSize = "12px";
  element.style.lineHeight = "1.4";
  element.style.color = "#b8d9ff";
  const widget = node.addDOMWidget("h3_chain_status", "customtext", element, {
    serialize: false,
    getValue: () => element.textContent,
    setValue: (value) => { element.textContent = value || ""; },
    getHeight: () => (element.textContent ? 40 : 0),
  });
  widget.label = "自动续写状态";
  widget.computeSize = () => (element.textContent ? [node.size?.[0] || 220, 40] : [0, -4]);
  node.__staraiH3ChainStatus = {
    element,
    widget,
    chainId: node.__staraiH3ChainStatus?.chainId || "",
  };
  return node.__staraiH3ChainStatus;
}

function updateH3ChainStatus(node, rawStatus) {
  const status = typeof rawStatus === "string" ? parseJson(rawStatus) : rawStatus;
  if (!status?.chain_id) return;
  const view = ensureH3ChainStatusWidget(node);
  view.chainId = status.chain_id;
  view.element.textContent = chainSummary(status);
  view.element.style.minHeight = view.element.textContent ? "34px" : "0px";
  node.setDirtyCanvas?.(true, true);
}

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
  configureH3ChainStatus(node);
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
  updateH3ChainStatus(node, view?.status);
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

const BASE_OUTPUT_COUNT = 5;
const MAX_CLONE_SLOTS = 8;
const CLONE_PROP = "starai_clones";
const EMPTY_CLONE_LABEL = "功能克隆";
const NATIVE_WIDGET_NAMES = new Set([
  "skill",
  "user_prompt",
  "api_base",
  "model",
  "api_key",
  "video_duration",
  "cut_count",
  "clone_functions",
  "h3_chain_status",
  "run_mode",
  "conversation_action",
  "conversation_state",
  "conversation_view",
]);

function hideCloneFunctionsWidget(node) {
  const widget = getWidget(node, "clone_functions");
  if (widget) {
    widget.options = widget.options || {};
    widget.options.serialize = true;
    widget.hidden = true;
    widget.type = "converted-widget";
    widget.computeSize = () => [0, -4];
    if (widget.element) widget.element.style.display = "none";
  }
  const input = (node.inputs || []).find((item) => item.name === "clone_functions");
  if (input) input.hidden = true;
}

function getCloneSpecs(node) {
  const raw = node.properties?.[CLONE_PROP];
  return Array.isArray(raw) ? raw.filter((item) => item && typeof item === "object") : [];
}

function writeCloneFunctions(node, specs) {
  const widget = getWidget(node, "clone_functions");
  if (widget) widget.value = JSON.stringify(specs || []);
}

function setCloneSpecs(node, specs) {
  node.properties = node.properties || {};
  node.properties[CLONE_PROP] = specs;
  writeCloneFunctions(node, specs);
}

function upsertCloneSpec(node, spec) {
  const specs = getCloneSpecs(node).filter((item) => Number(item.index) !== Number(spec.index));
  specs.push(spec);
  specs.sort((a, b) => Number(a.index) - Number(b.index));
  setCloneSpecs(node, specs);
  return specs;
}

function comboValuesFrom(source) {
  const values = source?.options?.values || source?.options || source?.values;
  if (Array.isArray(values)) {
    return values
      .map((value) => (value && typeof value === "object" && "value" in value ? value.value : value))
      .filter((value) => value != null && value !== "");
  }
  if (values && typeof values === "object") return Object.values(values).filter(Boolean);
  return [];
}

function findTargetCombo(targetNode, targetSlot) {
  const input = targetNode?.inputs?.[targetSlot];
  if (!input) return null;
  const widget = (targetNode.widgets || []).find((item) => item.name === input.name)
    || (targetNode.widgets || []).find((item) => item.name === input.widget?.name)
    || input.widget;
  const options = comboValuesFrom(widget) || comboValuesFrom(input);
  if (!options.length) return null;
  return {
    input,
    widget,
    options,
    name: input.name,
    label: input.label || input.localized_name || widget?.label || input.name,
    value: options.includes(widget?.value) ? widget.value : options[0],
  };
}

function cloneOutputIndex(output, slot) {
  const match = /^clone_(\d+)$/.exec(output?.name || "");
  if (match) return Number(match[1]);
  if (slot >= BASE_OUTPUT_COUNT) return slot - BASE_OUTPUT_COUNT;
  return -1;
}

function outputConnected(output, node = null) {
  const ids = Array.isArray(output?.links) ? output.links.filter((id) => id != null) : [];
  if (!ids.length) return false;
  const links = node?.graph?.links;
  if (!links) return true;
  return ids.some((id) => Boolean(links[id] || links.get?.(id)));
}

function findCloneOutput(node, index) {
  return (node.outputs || []).find((output) => output.name === `clone_${index}`);
}

function graphIsConfiguring() {
  return Boolean(app.configuringGraph);
}

function pruneDisconnectedClones(node, keepIndex = null) {
  if (graphIsConfiguring()) return getCloneSpecs(node);
  const remaining = getCloneSpecs(node).filter((spec) => {
    if (keepIndex != null && Number(spec.index) === Number(keepIndex)) return true;
    return outputConnected(findCloneOutput(node, spec.index), node);
  });
  setCloneSpecs(node, remaining);
  return remaining;
}

function removeWidgetSafe(node, widget) {
  if (!node?.widgets || !widget) return;
  if (typeof node.removeWidget === "function") {
    node.removeWidget(widget);
    return;
  }
  const index = node.widgets.indexOf(widget);
  if (index >= 0) node.widgets.splice(index, 1);
}

function isCloneWidget(widget) {
  if (!widget) return false;
  if (widget.__staraiCloneWidget || widget.__staraiCloneIndex != null) return true;
  return !NATIVE_WIDGET_NAMES.has(widget.name) && widget.type === "combo";
}

function removeStaleCloneWidgets(node, specs) {
  const keep = new Set(specs.map((item) => Number(item.index)));
  const keepNames = new Set(specs.map((item) => item.label || item.name));
  const stale = (node.widgets || []).filter((widget) => {
    if (!isCloneWidget(widget)) return false;
    const index = widget.__staraiCloneIndex;
    if (index != null) return !keep.has(Number(index));
    return !keepNames.has(widget.name);
  });
  stale.forEach((widget) => {
    widget.onRemove?.();
    removeWidgetSafe(node, widget);
  });
  if (stale.length && node.widgets) {
    node.widgets = node.widgets.filter((widget) => !stale.includes(widget));
  }
}

function applyCloneWidget(node, spec) {
  let widget = (node.widgets || []).find((item) => Number(item.__staraiCloneIndex) === Number(spec.index));
  if (!widget) {
    widget = node.addWidget(
      "combo",
      spec.label || spec.name,
      spec.value,
      (value) => {
        spec.value = value;
        upsertCloneSpec(node, spec);
      },
      { values: spec.options || [] },
    );
  }
  widget.type = "combo";
  widget.options = widget.options || {};
  widget.options.values = spec.options || [];
  widget.value = (spec.options || []).includes(spec.value) ? spec.value : ((spec.options || [])[0] || "");
  widget.label = spec.label || spec.name;
  widget.name = spec.label || spec.name;
  widget.__staraiCloneIndex = spec.index;
  widget.__staraiCloneWidget = true;
  widget.hidden = false;
  widget.serialize = true;
}

function placeCloneWidgetsAfterCutCount(node) {
  const widgets = node.widgets;
  if (!widgets?.length) return;
  const clones = widgets
    .filter((widget) => widget.__staraiCloneIndex != null)
    .sort((a, b) => Number(a.__staraiCloneIndex) - Number(b.__staraiCloneIndex));
  if (!clones.length) return;
  const rest = widgets.filter((widget) => widget.__staraiCloneIndex == null);
  const insertAt = rest.findIndex((widget) => widget.name === "cut_count") + 1;
  if (insertAt <= 0) return;
  rest.splice(insertAt, 0, ...clones);
  node.widgets = rest;
}

function highestCloneUsed(node, specs) {
  let highest = -1;
  for (const spec of specs) {
    const index = Number(spec.index);
    if (Number.isInteger(index)) highest = Math.max(highest, index);
  }
  (node.outputs || []).forEach((output) => {
    const match = /^clone_(\d+)$/.exec(output?.name || "");
    if (match && outputConnected(output)) highest = Math.max(highest, Number(match[1]));
  });
  return highest;
}

function updateCloneOutputs(node) {
  const specs = getCloneSpecs(node);
  const highestUsed = highestCloneUsed(node, specs);
  const needed = Math.min(MAX_CLONE_SLOTS, Math.max(1, highestUsed + 1, specs.length + 1));

  for (let index = (node.outputs || []).length - 1; index >= 0; index -= 1) {
    const output = node.outputs[index];
    const match = /^clone_(\d+)$/.exec(output?.name || "");
    if (!match) continue;
    const cloneIndex = Number(match[1]);
    if (cloneIndex >= needed && !outputConnected(output)) node.removeOutput(index);
  }

  for (let index = 0; index < needed; index += 1) {
    const exists = (node.outputs || []).some((output) => output.name === `clone_${index}`);
    if (!exists) node.addOutput(`clone_${index}`, "*");
  }

  (node.outputs || []).forEach((output) => {
    const match = /^clone_(\d+)$/.exec(output?.name || "");
    if (!match) return;
    const cloneIndex = Number(match[1]);
    const spec = specs.find((item) => Number(item.index) === cloneIndex);
    if (spec) {
      output.hidden = false;
      output.type = "COMBO";
      output.label = spec.label || spec.name;
    } else if (cloneIndex < needed) {
      output.hidden = false;
      output.type = "*";
      output.label = EMPTY_CLONE_LABEL;
    } else {
      output.hidden = true;
      output.type = "*";
      output.label = EMPTY_CLONE_LABEL;
    }
    output.localized_name = output.label;
  });
}

function shrinkNodeToContent(node) {
  const size = node.computeSize?.();
  if (!size || !node.setSize) return;
  const width = Math.max(node.size?.[0] || 0, size[0]);
  node.setSize([width, size[1]]);
}

function syncCloneUi(node, keepIndex = null) {
  if (!node || node.type !== NODE_TYPE) return;
  hideCloneFunctionsWidget(node);
  const specs = pruneDisconnectedClones(node, keepIndex);
  removeStaleCloneWidgets(node, specs);
  specs.forEach((spec) => applyCloneWidget(node, spec));
  placeCloneWidgetsAfterCutCount(node);
  updateCloneOutputs(node);
  writeCloneFunctions(node, specs);
  shrinkNodeToContent(node);
  node.setDirtyCanvas?.(true, true);
}

function removeCloneAtSlot(node, slot) {
  const output = node.outputs?.[slot];
  const cloneIndex = cloneOutputIndex(output, slot);
  if (cloneIndex >= 0 && !outputConnected(output, node)) {
    const remaining = getCloneSpecs(node).filter((item) => Number(item.index) !== cloneIndex);
    setCloneSpecs(node, remaining);
    if (output) {
      output.type = "*";
      output.label = EMPTY_CLONE_LABEL;
      output.localized_name = EMPTY_CLONE_LABEL;
    }
  }
  syncCloneUi(node);
}

function cloneFromConnection(node, slot, targetNode, targetSlot, linkInfo) {
  const output = node.outputs?.[slot];
  const cloneIndex = cloneOutputIndex(output, slot);
  if (cloneIndex < 0 || cloneIndex >= MAX_CLONE_SLOTS) return;
  const combo = findTargetCombo(targetNode, targetSlot);
  if (!combo) return;
  const spec = {
    index: cloneIndex,
    name: combo.name,
    label: combo.label,
    options: combo.options,
    value: combo.value,
  };
  upsertCloneSpec(node, spec);
  if (linkInfo) linkInfo.type = "COMBO";
  if (output) {
    output.type = "COMBO";
    output.label = spec.label;
    output.localized_name = spec.label;
  }
  syncCloneUi(node, spec.index);
}

function configureCloneOutputs(node) {
  if (!node || node.type !== NODE_TYPE) return;
  node.properties = node.properties || {};
  if (!Array.isArray(node.properties[CLONE_PROP])) {
    const stored = parseJson(getWidget(node, "clone_functions")?.value || "[]");
    node.properties[CLONE_PROP] = Array.isArray(stored) ? stored : [];
  }
  syncCloneUi(node);
}

function installClonePromptHook() {
  if (app.__staraiClonePromptHook || typeof app.graphToPrompt !== "function") return;
  const originalGraphToPrompt = app.graphToPrompt.bind(app);
  app.graphToPrompt = async function () {
    (app.graph?._nodes || []).forEach((node) => {
      if (node.type === NODE_TYPE) writeCloneFunctions(node, getCloneSpecs(node));
    });
    const prompt = await originalGraphToPrompt();
    (app.graph?._nodes || []).forEach((node) => {
      if (node.type !== NODE_TYPE) return;
      const entry = prompt?.output?.[String(node.id)] || prompt?.output?.[node.id];
      if (entry?.inputs) entry.inputs.clone_functions = JSON.stringify(getCloneSpecs(node));
    });
    return prompt;
  };
  app.__staraiClonePromptHook = true;
}

app.registerExtension({
  name: "MiniMaxH3.SkillBridge.DynamicImages",
  setup() {
    installQueueGuard();
    installClonePromptHook();
    const refreshCloneNodes = () => {
      (app.graph?._nodes || []).forEach((node) => {
        if (node.type === NODE_TYPE) syncCloneUi(node);
      });
    };
    api.addEventListener("graphLoaded", refreshCloneNodes);
    api.addEventListener(CHAIN_STATUS_EVENT, ({ detail }) => {
      const skillNodeId = String(detail?.skill_node_id ?? "");
      (app.graph?._nodes || []).forEach((node) => {
        if (
          (node.type === NODE_TYPE || node.type === CHAT_NODE_TYPE)
          && (String(node.id) === skillNodeId || node.__staraiH3ChainStatus?.chainId === detail?.chain_id)
        ) {
          updateH3ChainStatus(node, detail);
        }
      });
    });
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
        else {
          configureH3ChainStatus(this);
          configureCloneOutputs(this);
        }
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
    if (nodeData.name === NODE_TYPE) {
      const originalExecuted = nodeType.prototype.onExecuted;
      nodeType.prototype.onExecuted = function (output) {
        originalExecuted?.apply(this, arguments);
        updateH3ChainStatus(this, output?.["运行状态"]?.[0] || output?.[2]?.[0]);
      };
    }

    const originalConnections = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (side, slot, connected, linkInfo) {
      const result = originalConnections?.apply(this, arguments);
      queueMicrotask(() => {
        updateDynamicImageInputs(this);
        if (this.type !== NODE_TYPE) return;
        const isOutput = side === 2 || side === LiteGraph?.OUTPUT;
        if (connected && linkInfo) {
          const targetId = linkInfo.target_id;
          const originId = linkInfo.origin_id;
          const thisId = this.id;
          if (originId === thisId || linkInfo.origin_slot === slot || isOutput) {
            const target = this.graph?.getNodeById?.(targetId);
            const outputSlot = originId === thisId ? linkInfo.origin_slot : slot;
            cloneFromConnection(this, outputSlot, target, linkInfo.target_slot, linkInfo);
          } else {
            syncCloneUi(this);
          }
        } else {
          removeCloneAtSlot(this, slot);
          syncCloneUi(this);
        }
      });
      return result;
    };

    if (nodeData.name === NODE_TYPE) {
      const originalConnectOutput = nodeType.prototype.onConnectOutput;
      nodeType.prototype.onConnectOutput = function (slot, _type, _input, targetNode, targetSlot) {
        const result = originalConnectOutput?.apply(this, arguments);
        queueMicrotask(() => cloneFromConnection(this, slot, targetNode, targetSlot));
        return result === undefined ? true : result;
      };

      const originalDisconnectOutput = nodeType.prototype.disconnectOutput;
      nodeType.prototype.disconnectOutput = function (slot, targetNode) {
        const result = originalDisconnectOutput?.apply(this, arguments);
        queueMicrotask(() => {
          removeCloneAtSlot(this, slot);
          syncCloneUi(this);
        });
        return result;
      };

      const originalConfigure = nodeType.prototype.onConfigure;
      nodeType.prototype.onConfigure = function () {
        const result = originalConfigure?.apply(this, arguments);
        queueMicrotask(() => configureCloneOutputs(this));
        return result;
      };
    }
  },

  afterConfigureGraph() {
    (app.graph?._nodes || []).forEach((node) => {
      if (node.type === NODE_TYPE) configureCloneOutputs(node);
    });
  },
  loadedGraphNode(node) {
    if (node?.type === NODE_TYPE) {
      queueMicrotask(() => {
        updateDynamicImageInputs(node);
        configureApiKeyWidget(node);
        configureH3ChainStatus(node);
        configureCloneOutputs(node);
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

window.addEventListener(CHAIN_STATUS_EVENT, (event) => {
  const status = event.detail;
  (app.graph?._nodes || []).forEach((node) => {
    if ((node.type === NODE_TYPE || node.type === CHAT_NODE_TYPE) && node.__staraiH3ChainStatus?.chainId === status?.chain_id) {
      updateH3ChainStatus(node, status);
    }
  });
});
