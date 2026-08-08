import { app } from "/scripts/app.js";

const NODE_TYPE = "MiniMaxH3SkillBridge";
const INITIAL_VISIBLE_PORTS = 4;
const MAX_IMAGE_PORTS = 64;
const INPUT_LABELS = {
  skill: "技能",
  user_prompt: "用户要求",
  api_base: "API 地址",
  model: "云端模型",
  api_key: "API 密钥",
  images: "多图输入",
  video: "视频输入",
};

function applyInputLabels(node) {
  (node.inputs || []).forEach((input) => {
    const label = /^image_\\d+$/.test(input.name)
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
  if (!node || node.type !== NODE_TYPE) return;
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

app.registerExtension({
  name: "MiniMaxH3.SkillBridge.DynamicImages",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;

    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = originalCreated?.apply(this, arguments);
      queueMicrotask(() => {
        updateDynamicImageInputs(this);
        configureApiKeyWidget(this);
      });
      return result;
    };

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
  },
});
