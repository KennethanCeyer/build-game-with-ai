import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const canvas = document.querySelector("#scene");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0f14);

const camera = new THREE.PerspectiveCamera(52, window.innerWidth / window.innerHeight, 0.1, 100);
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.25));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = false;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const clock = new THREE.Clock();
const actorMeshes = new Map();
const zoneMeshes = new Map();
const mazeWallMeshes = new Map();
const puzzlePadMeshes = new Map();
const puzzleGaugeMeshes = [];
const zoneDisplayNames = new Map();
const puzzlePadOrder = ["red", "green", "blue", "yellow", "purple"];
let navigationObstacles = [];
let worldFlags = {};
const gltfLoader = new GLTFLoader();
const pressedKeys = new Set();
const audio = createAudioBus();
let puzzleGate = null;
const questApples = [];
let lastPuzzleCue = "";
let agentPlaybackActive = false;
let puzzleCueActive = false;
let currentTurnModel = null;
let currentTurnAgentName = "";
let statePollPending = false;
let lastCameraCommandId = 0;

const cameraControl = {
  yaw: -2.35,
  pitch: 0.74,
  distance: 10.4,
  target: new THREE.Vector3(-2.5, 1.1, 1.0),
  pointerActive: false,
  lastPointer: new THREE.Vector2(),
};
const driveSync = {
  elapsed: 0,
  interval: 0.42,
  pending: false,
  lastPayload: "",
  queuedPayload: null,
  localControlUntil: 0,
};
const worldBounds = {
  x: 17.2,
  z: 9.7,
};
const mazeLayout = {
  cols: 7,
  rows: 5,
  cell: 1.85,
  originX: -17.05,
  originZ: -8.75,
  startCol: 6,
  startRow: 4,
  exitCol: 0,
  exitRow: 0,
};

const hud = {
  scenarioName: document.querySelector("#scenarioName"),
  statusBadge: document.querySelector("#statusBadge"),
  goals: document.querySelector("#goals"),
  events: document.querySelector("#events"),
  interactionHint: document.querySelector("#interactionHint"),
};
const dialogueBox = {
  root: document.querySelector("#dialogueBox"),
  speaker: document.querySelector("#dialogueSpeaker"),
  line: document.querySelector("#dialogueLine"),
  lastKey: "",
  zoneId: null,
  closeAt: 0,
};
const inventoryPanel = {
  root: document.querySelector("#inventoryPanel"),
  items: document.querySelector("#inventoryItems"),
};
const consolePanel = document.querySelector("#console");
const consoleLog = document.querySelector("#consoleLog");
const consoleForm = document.querySelector("#consoleForm");
const consoleInput = document.querySelector("#consoleInput");
const consoleToggle = document.querySelector("#consoleToggle");
const consoleClose = document.querySelector("#consoleClose");

initLighting();
initGround();
initWorldProps();
bindUi();
refreshState();
startRuntimePolling();
writeConsole("처음이면 /help 를 입력하세요. 핵심 실습은 NPC 퀘스트, 미로, 퍼즐입니다.");
animate();

function initLighting() {
  const hemi = new THREE.HemisphereLight(0xd7ecff, 0x1b2230, 1.75);
  scene.add(hemi);
  const key = new THREE.DirectionalLight(0xffffff, 1.8);
  key.position.set(4, 8, 5);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x78b8ff, 0.75);
  fill.position.set(-5, 4, -4);
  scene.add(fill);
}

function initGround() {
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x202936, roughness: 0.86, metalness: 0.02 });
  const slabMat = new THREE.MeshStandardMaterial({ color: 0x2b3645, roughness: 0.82, metalness: 0.03 });
  const pathMat = new THREE.MeshStandardMaterial({ color: 0x334256, roughness: 0.78, metalness: 0.04 });
  const edgeMat = new THREE.MeshStandardMaterial({ color: 0x151e2d, roughness: 0.78 });

  const ground = new THREE.Mesh(new THREE.BoxGeometry(36, 0.16, 21), baseMat);
  ground.position.y = -0.1;
  scene.add(ground);

  for (const x of [-15.2, -12.0, -8.8, -5.6, -2.4, 0.8, 4.0, 7.2, 10.4, 13.6, 16.2]) {
    for (const z of [-8.2, -5.5, -2.8, -0.1, 2.6, 5.3, 8.0]) {
      addBox(`floor_slab_${x}_${z}`, [x, 0.005, z], [2.95, 0.035, 2.05], slabMat);
    }
  }

  addBox("main_walkway", [-0.2, 0.035, 0.12], [30.8, 0.05, 1.18], pathMat);
  addBox("maze_walkway", [-10.58, 0.05, -4.13], [13.6, 0.06, 9.7], pathMat);
  addBox("puzzle_walkway", [7.25, 0.045, 3.45], [4.5, 0.055, 5.8], pathMat);
  addBox("north_edge", [0, 0.22, -10.35], [36.0, 0.44, 0.28], edgeMat);
  addBox("south_edge", [0, 0.18, 10.35], [36.0, 0.36, 0.22], edgeMat);
  addBox("west_edge", [-17.65, 0.18, 0], [0.22, 0.36, 21.0], edgeMat);
  addBox("east_edge", [17.65, 0.18, 0], [0.22, 0.36, 21.0], edgeMat);
}

function initWorldProps() {
  const matDark = new THREE.MeshStandardMaterial({ color: 0x121a27, roughness: 0.78 });
  const matTrim = new THREE.MeshStandardMaterial({ color: 0x3a86ff, roughness: 0.54, emissive: 0x061a38 });
  const matPlant = new THREE.MeshStandardMaterial({ color: 0x2f8f6b, roughness: 0.82 });
  const matWood = new THREE.MeshStandardMaterial({ color: 0x8a6744, roughness: 0.8 });
  const matMaze = new THREE.MeshStandardMaterial({ color: 0x223149, roughness: 0.82 });
  const matMazeTrim = new THREE.MeshStandardMaterial({ color: 0x7dd3fc, roughness: 0.42, emissive: 0x082a35 });
  const matRed = new THREE.MeshStandardMaterial({ color: 0xef5b5b, roughness: 0.54, emissive: 0x2a0505 });
  const matBlue = new THREE.MeshStandardMaterial({ color: 0x44a8ff, roughness: 0.54, emissive: 0x06162a });
  const matGreen = new THREE.MeshStandardMaterial({ color: 0x55d887, roughness: 0.54, emissive: 0x052a12 });
  const matYellow = new THREE.MeshStandardMaterial({ color: 0xf5d15f, roughness: 0.54, emissive: 0x2b2104 });
  const matPurple = new THREE.MeshStandardMaterial({ color: 0xb58cff, roughness: 0.54, emissive: 0x180a2d });
  const matGlass = new THREE.MeshStandardMaterial({
    color: 0x47caff,
    transparent: true,
    opacity: 0.26,
    roughness: 0.16,
    metalness: 0.1,
  });

  addMaze(matMaze, matMazeTrim);
  addPuzzleYard(matDark, matRed, matGreen, matBlue, matYellow, matPurple, matTrim);
  addQuestArea(matWood, matPlant, matDark);

  addTree(-15.25, 7.45, matWood, matPlant);
  addTree(10.9, 6.25, matWood, matPlant);
  addTree(13.9, -6.45, matWood, matPlant);
  addBench(-1.1, 6.75, matWood, matDark);
  addBench(3.0, 6.75, matWood, matDark);
  addLamp(-2.0, 1.35, matDark, matGlass);
  addLamp(9.8, 0.75, matDark, matGlass);
}

function addBox(name, position, scale, material) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(scale[0], scale[1], scale[2]), material);
  mesh.name = name;
  mesh.position.set(position[0], position[1], position[2]);
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  scene.add(mesh);
  return mesh;
}

function addCylinder(name, position, radiusTop, radiusBottom, height, material, segments = 18) {
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radiusTop, radiusBottom, height, segments),
    material,
  );
  mesh.name = name;
  mesh.position.set(position[0], position[1], position[2]);
  scene.add(mesh);
  return mesh;
}

function addTextLabel(text, position, options = {}) {
  const texture = makeTextTexture(text, options);
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(material);
  sprite.name = options.name || `label_${text}`;
  sprite.position.set(position[0], position[1], position[2]);
  const width = options.width || 1.8;
  sprite.scale.set(width, width * 0.34, 1);
  scene.add(sprite);
  return sprite;
}

function makeTextTexture(text, options = {}) {
  const canvas2d = document.createElement("canvas");
  canvas2d.width = 512;
  canvas2d.height = 160;
  const ctx = canvas2d.getContext("2d");
  ctx.clearRect(0, 0, canvas2d.width, canvas2d.height);
  ctx.fillStyle = options.background || "rgba(8, 13, 20, 0.84)";
  roundRect(ctx, 18, 26, 476, 104, 18);
  ctx.fill();
  ctx.strokeStyle = options.border || "rgba(125, 211, 252, 0.72)";
  ctx.lineWidth = 4;
  roundRect(ctx, 18, 26, 476, 104, 18);
  ctx.stroke();
  ctx.fillStyle = options.color || "#eaf7ff";
  ctx.font = "700 48px 'Plus Jakarta Sans', system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas2d.width / 2, 80);
  const texture = new THREE.CanvasTexture(canvas2d);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function addTree(x, z, trunkMat, leafMat) {
  addCylinder(`tree_trunk_${x}_${z}`, [x, 0.42, z], 0.12, 0.16, 0.84, trunkMat, 10);
  const crown = new THREE.Mesh(new THREE.DodecahedronGeometry(0.62, 0), leafMat);
  crown.position.set(x, 1.15, z);
  crown.scale.set(1.0, 1.18, 0.95);
  scene.add(crown);
}

function addQuestArea(trunkMat, leafMat, trimMat) {
  addBox("quest_plaza_floor", [9.4, 0.058, -1.0], [11.0, 0.055, 4.6], new THREE.MeshStandardMaterial({
    color: 0x263449,
    roughness: 0.82,
  }));
  addBox("mira_marker", [4.3, 0.07, -2.25], [1.2, 0.055, 1.2], new THREE.MeshStandardMaterial({
    color: 0x6ee7b7,
    roughness: 0.5,
    emissive: 0x052418,
  }));
  addBox("toma_market_mat", [0.0, 0.07, -1.0], [1.25, 0.055, 1.25], new THREE.MeshStandardMaterial({
    color: 0xffb454,
    roughness: 0.5,
    emissive: 0x241205,
  }));
  addBox("fruit_stall_counter", [-0.65, 0.48, -1.75], [1.7, 0.46, 0.42], trimMat);
  addBox("fruit_stall_awning", [-0.65, 1.05, -1.75], [1.95, 0.16, 0.72], new THREE.MeshStandardMaterial({
    color: 0xd96b43,
    roughness: 0.56,
  }));
  addTree(14.35, 6.45, trunkMat, leafMat);
  [
    [14.12, 1.2, 6.22],
    [14.5, 1.34, 6.4],
    [14.25, 1.48, 6.72],
  ].forEach((position, index) => {
    const apple = new THREE.Mesh(
      new THREE.SphereGeometry(0.13, 16, 12),
      new THREE.MeshStandardMaterial({ color: 0xd84e3f, roughness: 0.48, emissive: 0x220304 }),
    );
    apple.name = `quest_visible_apple_${index}`;
    apple.position.set(position[0], position[1], position[2]);
    questApples.push(apple);
    scene.add(apple);
  });
}

function addBench(x, z, seatMat, legMat) {
  addBox(`bench_seat_${x}_${z}`, [x, 0.36, z], [1.35, 0.16, 0.42], seatMat);
  addBox(`bench_back_${x}_${z}`, [x, 0.68, z + 0.22], [1.35, 0.38, 0.12], seatMat);
  addBox(`bench_leg_l_${x}_${z}`, [x - 0.45, 0.16, z], [0.12, 0.32, 0.34], legMat);
  addBox(`bench_leg_r_${x}_${z}`, [x + 0.45, 0.16, z], [0.12, 0.32, 0.34], legMat);
}

function addLamp(x, z, postMat, glassMat) {
  addCylinder(`lamp_post_${x}_${z}`, [x, 0.72, z], 0.05, 0.06, 1.42, postMat, 10);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.18, 14, 10), glassMat);
  head.position.set(x, 1.48, z);
  scene.add(head);
  const light = new THREE.PointLight(0x7bc8ff, 3.2, 2.6);
  light.position.set(x, 1.48, z);
  scene.add(light);
}

function addMaze(wallMat, trimMat) {
  const start = mazeStartPosition();
  const exit = mazeExitPosition();
  const center = {
    x: mazeLayout.originX + (mazeLayout.cols * mazeLayout.cell) / 2,
    z: mazeLayout.originZ + (mazeLayout.rows * mazeLayout.cell) / 2,
  };
  addBox("maze_floor", [center.x, 0.06, center.z], [13.85, 0.05, 10.15], new THREE.MeshStandardMaterial({
    color: 0x1d293a,
    roughness: 0.84,
  }));
  addBox("maze_start_pad", [start.x, 0.08, start.z], [0.95, 0.06, 0.95], trimMat);
  addTextLabel("미로 시작", [start.x, 1.55, start.z], { name: "maze_start_label", width: 1.9 });
  addBox("maze_start_gate_l", [start.x + 0.55, 0.5, start.z - 0.55], [0.18, 1.0, 0.18], trimMat);
  addBox("maze_start_gate_r", [start.x + 0.55, 0.5, start.z + 0.55], [0.18, 1.0, 0.18], trimMat);
  addBox("maze_exit_pad", [exit.x, 0.08, exit.z], [1.05, 0.06, 1.05], trimMat);
  addTextLabel("미로 출구", [exit.x, 1.55, exit.z], { name: "maze_exit_label", width: 1.9 });
  addBox("maze_exit_gate_l", [exit.x - 0.55, 0.5, exit.z - 0.55], [0.18, 1.0, 0.18], trimMat);
  addBox("maze_exit_gate_r", [exit.x - 0.55, 0.5, exit.z + 0.55], [0.18, 1.0, 0.18], trimMat);
  mazeWallMeshes.material = wallMat;
}

function mazeCellCenter(col, row) {
  return {
    x: mazeLayout.originX + col * mazeLayout.cell + mazeLayout.cell / 2,
    z: mazeLayout.originZ + row * mazeLayout.cell + mazeLayout.cell / 2,
  };
}

function mazeStartPosition() {
  const center = mazeCellCenter(mazeLayout.startCol, mazeLayout.startRow);
  return {
    x: mazeLayout.originX + mazeLayout.cols * mazeLayout.cell + 0.62,
    z: center.z,
  };
}

function mazeExitPosition() {
  return mazeCellCenter(mazeLayout.exitCol, mazeLayout.exitRow);
}

function addPuzzleYard(baseMat, redMat, greenMat, blueMat, yellowMat, purpleMat, gateMat) {
  addBox("puzzle_floor", [7.25, 0.065, 3.25], [4.45, 0.06, 5.45], baseMat);
  addCylinder("puzzle_console", [7.25, 0.36, 1.25], 0.36, 0.48, 0.72, gateMat, 28);
  addCylinder("puzzle_play_button", [7.25, 0.78, 1.25], 0.28, 0.28, 0.08, gateMat, 28);
  puzzlePadMeshes.set("puzzle_red", addCylinder("puzzle_red_pad", [6.05, 0.14, 2.72], 0.52, 0.52, 0.14, redMat.clone(), 28));
  puzzlePadMeshes.set("puzzle_green", addCylinder("puzzle_green_pad", [7.25, 0.14, 3.55], 0.52, 0.52, 0.14, greenMat.clone(), 28));
  puzzlePadMeshes.set("puzzle_blue", addCylinder("puzzle_blue_pad", [8.45, 0.14, 2.72], 0.52, 0.52, 0.14, blueMat.clone(), 28));
  puzzlePadMeshes.set("puzzle_yellow", addCylinder("puzzle_yellow_pad", [6.55, 0.14, 4.28], 0.52, 0.52, 0.14, yellowMat.clone(), 28));
  puzzlePadMeshes.set("puzzle_purple", addCylinder("puzzle_purple_pad", [7.95, 0.14, 4.28], 0.52, 0.52, 0.14, purpleMat.clone(), 28));
  puzzlePadMeshes.forEach((mesh) => {
    mesh.userData.defaultY = mesh.position.y;
    mesh.userData.defaultColor = mesh.material.color.clone();
    mesh.userData.defaultEmissive = mesh.material.emissive.clone();
  });
  [-0.84, -0.42, 0, 0.42, 0.84].forEach((offset, index) => {
    const gauge = addBox(`puzzle_gauge_${index}`, [7.25 + offset, 1.12, 1.05], [0.28, 0.16, 0.14], baseMat);
    gauge.material = baseMat.clone();
    puzzleGaugeMeshes.push(gauge);
  });
  addBox("puzzle_gate_post_l", [6.15, 0.58, 5.0], [0.12, 1.16, 0.12], gateMat);
  addBox("puzzle_gate_post_r", [8.35, 0.58, 5.0], [0.12, 1.16, 0.12], gateMat);
  const gateFieldMat = gateMat.clone();
  gateFieldMat.transparent = true;
  gateFieldMat.opacity = 0.48;
  puzzleGate = addBox("puzzle_gate_field", [7.25, 0.58, 5.0], [2.1, 1.02, 0.08], gateFieldMat);
}

function bindUi() {
  window.addEventListener("resize", onResize);
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  window.addEventListener("blur", releaseAllMovementKeys);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) releaseAllMovementKeys();
  });
  window.addEventListener("pointerdown", () => audio.unlock(), { once: true });

  canvas.addEventListener("pointerdown", (event) => {
    cameraControl.pointerActive = true;
    cameraControl.lastPointer.set(event.clientX, event.clientY);
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!cameraControl.pointerActive) return;
    const dx = event.clientX - cameraControl.lastPointer.x;
    const dy = event.clientY - cameraControl.lastPointer.y;
    cameraControl.lastPointer.set(event.clientX, event.clientY);
    cameraControl.yaw -= dx * 0.006;
    cameraControl.pitch = THREE.MathUtils.clamp(cameraControl.pitch + dy * 0.004, 0.22, 1.12);
  });
  canvas.addEventListener("pointerup", (event) => {
    cameraControl.pointerActive = false;
    canvas.releasePointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointercancel", () => {
    cameraControl.pointerActive = false;
  });
  canvas.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      cameraControl.distance = THREE.MathUtils.clamp(
        cameraControl.distance + event.deltaY * 0.006,
        3.6,
        11.5,
      );
    },
    { passive: false },
  );

  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", () => {
      audio.play("click");
      runConsoleCommand(button.dataset.command);
    });
  });
  document.querySelector("#resetButton").addEventListener("click", async () => {
    audio.play("open");
    await fetch("/api/reset", { method: "POST" });
    dialogueBox.lastKey = "";
    closeDialogue();
    releaseAllMovementKeys();
    await refreshState();
  });
  consoleToggle.addEventListener("click", () => {
    audio.play("open");
    openConsole(true);
  });
  consoleClose.addEventListener("click", () => {
    audio.play("click");
    openConsole(false);
  });
  consoleForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const command = consoleInput.value.trim();
    if (!command) return;
    consoleInput.value = "";
    await runConsoleCommand(command);
    consoleInput.focus();
  });
}

function onKeyDown(event) {
  audio.unlock();

  if (event.key === "`") {
    event.preventDefault();
    audio.play("open");
    openConsole(!consolePanel.classList.contains("open"));
    return;
  }

  if (isTypingInConsole() || agentPlaybackActive) return;
  if (event.code === "KeyI") {
    event.preventDefault();
    toggleInventory();
    return;
  }
  if (event.code === "KeyE") {
    event.preventDefault();
    contextInteract();
    return;
  }
  if (["KeyW", "KeyA", "KeyS", "KeyD", "ShiftLeft", "ShiftRight", "Space"].includes(event.code)) {
    event.preventDefault();
    pressedKeys.add(event.code);
    if (event.code === "Space") startJump();
  }
}

function onKeyUp(event) {
  if (pressedKeys.delete(event.code)) syncIdleIfStopped();
}

function releaseAllMovementKeys() {
  if (pressedKeys.size === 0) return;
  pressedKeys.clear();
  cameraControl.pointerActive = false;
  const actor = actorMeshes.get("rhea");
  if (!actor) return;
  actor.userData.behavior = actor.userData.jumpElapsed > 0 ? "jump" : "idle";
  actor.userData.gait = "walk";
  actor.userData.stepTimer = 0;
  syncDrive(actor, false, actor.userData.jumpElapsed > 0, false);
}

function syncIdleIfStopped() {
  const actor = actorMeshes.get("rhea");
  if (!actor || hasMovementKeys() || actor.userData.jumpElapsed > 0) return;
  actor.userData.behavior = "idle";
  actor.userData.gait = "walk";
  actor.userData.stepTimer = 0;
  syncDrive(actor, false, false, false);
}

function hasMovementKeys() {
  return ["KeyW", "KeyA", "KeyS", "KeyD"].some((key) => pressedKeys.has(key));
}

function isTypingInConsole() {
  const open = consolePanel.classList.contains("open");
  if (!open) return false;
  // 입력창에 실제 포커스가 있는 경우에만 '타이핑 중'으로 판단
  return document.activeElement === consoleInput;
}

function openConsole(open) {
  consolePanel.classList.toggle("open", open);
  if (open) {
    consoleInput.focus();
  } else {
    document.body.classList.remove("console-maximized");
    if (consoleMaximize) consoleMaximize.textContent = "최대화";
    onResize();
  }
}

function toggleInventory() {
  inventoryPanel.root?.classList.toggle("open");
}

async function runConsoleCommand(command) {
  openConsole(true);
  audio.play("click");
  currentTurnModel = null;
  appendConsoleMessage("user", command);
  if (command === "/help") {
    appendConsoleMessage("system", helpText());
    return;
  }
  const screenshotDataUrl = captureSceneDataUrl();
  appendAgentInputPacket(command, screenshotDataUrl);
  const pending = appendConsoleMessage("agent", "ADK 요청 접수 중...", { variant: "thinking" });
  try {
    const response = await fetch("/api/console/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, screenshot_data_url: screenshotDataUrl }),
    });
    if (!response.body) throw new Error("stream response body is missing");
    await readConsoleStream(response, pending);
  } catch (error) {
    pending.remove();
    appendConsoleMessage("system", `요청 실패: ${error}`);
  }
}

function helpText() {
  return [
    "자연어로 요청하면 실제 ADK Agent에게 현재 캔버스 이미지와 게임 state가 전달됩니다.",
    "예시:",
    "- NPC 퀘스트를 대화와 화면 단서만 보고 입력 버퍼로 완료해봐",
    "- 미로를 입력만으로 탈출해봐",
    "- 퍼즐을 화면 단서 기반으로 풀고 호출 그래프를 보여줘",
    "",
    "Agent가 이동할 때는 apply_input_buffer tool이 보낸 WASD/Shift/Space/E 프레임을 화면에서 그대로 재생합니다.",
    "adk web에서 같은 MCP runtime을 쓰는 경우에도 이 브라우저는 /api/state를 폴링해서 캐릭터 이동을 따라갑니다.",
  ].join("\n");
}

async function readConsoleStream(response, pending) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffered += decoder.decode(value, { stream: true });
    const lines = buffered.split("\n");
    buffered = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      await handleConsoleStreamEvent(JSON.parse(line), pending);
    }
  }
  if (buffered.trim()) await handleConsoleStreamEvent(JSON.parse(buffered), pending);
}

async function handleConsoleStreamEvent(event, pending) {
  // 새로운 메시지가 추가될 때마다 pending(생각 중) 메시지를 최하단으로 이동시켜 시각적 연속성 유지
  const ensurePendingAtBottom = () => {
    if (pending && pending.parentElement === consoleLog) {
      consoleLog.append(pending);
      scrollConsole();
    }
  };

  if (event.type === "accepted") {
    setConsoleMessageText(pending, event.screenshot_attached
      ? "요청 접수: 캔버스 이미지를 Gemini 입력으로 첨부했습니다."
      : "요청 접수: 이미지 없이 ADK turn을 시작합니다.");
    ensurePendingAtBottom();
    return;
  }
  if (event.type === "model_start") {
    currentTurnModel = event.model;
    currentTurnAgentName = event.agent_name || "";
    setConsoleMessageModel(pending, event.model, currentTurnAgentName);
    pending.classList.add("thinking");
    setConsoleMessageText(pending, "모델이 화면과 상태를 보고 다음 입력을 고르는 중입니다...");
    ensurePendingAtBottom();
    return;
  }
  if (event.type === "tool_call") {
    appendConsoleMessage(
      "tool",
      compactText(formatJson(event.args || {}), 1100),
      { 
        label: `Tool Call · ${event.name}`, 
        model: currentTurnModel, 
        agentName: currentTurnAgentName,
        variant: "tool-call" 
      },
    );
    ensurePendingAtBottom();
    return;
  }
  if (event.type === "input_buffer") {
    const playbackMessage = appendConsoleMessage(
      "tool",
      `입력 재생 시작: ${event.frames.length} frames · ${summarizeFrames(event.frames)}`,
      { 
        label: "Input Replay", 
        model: currentTurnModel, 
        agentName: currentTurnAgentName,
        variant: "input-playback" 
      },
    );
    ensurePendingAtBottom();
    await playAgentInputBuffer(event.frames, event.camera_yaw_degrees || 0, playbackMessage);
    setConsoleMessageText(playbackMessage, `입력 재생 완료: ${event.frames.length} frames · tool response를 기다립니다.`);
    ensurePendingAtBottom();
    return;
  }
  if (event.type === "tool_response") {
    if (event.name?.endsWith("adjust_camera_view") && event.response?.command) {
      lastCameraCommandId = Math.max(lastCameraCommandId, event.response.command.id || 0);
      applyCameraCommand(event.response.command);
    }
    const observationMessage = appendObservationResponse(event);
    
    setConsoleMessageText(pending, "도구 결과를 분석하여 다음 최적의 행동(이동/관찰)을 계획하고 있습니다...");
    pending.classList.add("thinking"); 
    
    await refreshState();

    const freshScreenshot = captureSceneDataUrl();
    if (freshScreenshot && observationMessage) {
      const img = document.createElement("img");
      img.src = freshScreenshot;
      img.className = "console-observation-image";
      img.onload = scrollConsole;
      observationMessage.append(img);
    }
    ensurePendingAtBottom();
    return;
  }
  if (event.type === "final_text") {
    pending.classList.remove("thinking");
    setConsoleMessageText(pending, event.answer || "ADK turn이 완료되었습니다. 결과를 보고합니다.");
    ensurePendingAtBottom();
    return;
  }
  if (event.type === "final") {
    pending.remove();
    appendAgentResponse(event.payload);
    
    // 실제 미션 성공 여부에 따라 소리 분기 (단순 턴 완료는 click, 미션 성공은 confirm)
    const isSuccess = event.payload?.maze_escaped || event.payload?.quest_complete || event.payload?.puzzle_solved;
    const isError = event.payload?.ok === false;
    audio.play(isError ? "error" : (isSuccess ? "confirm" : "click"));
    
    await refreshState();
    return;
  }
  if (event.type === "error") {
    pending.remove();
    appendConsoleMessage("system", `ADK error: ${event.message}`);
  }
}

async function refreshState() {
  const response = await fetch("/api/state");
  const payload = await response.json();
  drawState(payload.state);
}

function startRuntimePolling() {
  setInterval(async () => {
    if (statePollPending || pressedKeys.size > 0 || agentPlaybackActive || driveSync.pending) {
      return;
    }
    statePollPending = true;
    try {
      await refreshState();
      await pollCameraCommands();
    } catch {
      // The page can be opened before the dev server is fully restarted.
    } finally {
      statePollPending = false;
    }
  }, 700);
}

async function pollCameraCommands() {
  const response = await fetch(`/api/camera-commands?after=${lastCameraCommandId}`);
  const payload = await response.json();
  for (const command of payload.commands || []) {
    lastCameraCommandId = Math.max(lastCameraCommandId, command.id || 0);
    applyCameraCommand(command);
  }
}

function drawState(state) {
  hud.scenarioName.textContent = state.display_name;
  hud.statusBadge.textContent = state.status;
  hud.goals.replaceChildren(...state.goals.map((goal) => goalLine(goal)));
  zoneDisplayNames.clear();
  state.zones.forEach((zone) => zoneDisplayNames.set(zone.id, zone.name));
  hud.events.replaceChildren(
    ...state.events
      .slice()
      .reverse()
      .map((event) => {
        const li = document.createElement("li");
        li.textContent = event.message;
        return li;
      }),
  );

  state.zones.forEach((zone) => updateZone(zone));
  navigationObstacles = state.obstacles || [];
  worldFlags = state.flags || {};
  syncMazeWalls(navigationObstacles);
  if (puzzleGate) puzzleGate.visible = !worldFlags.puzzle_solved;
  updateQuestApples();
  updateInventory(state.inventory || []);
  updatePuzzleVisuals();
  replayPuzzleCue(state.events || []);
  updateDialogue(state.events || []);
  state.actors.forEach((actor) => updateActor(actor));
}

function updateQuestApples() {
  questApples.forEach((apple, index) => {
    apple.visible = index > 0 || !worldFlags.apple_harvested;
  });
}

function updateInventory(items) {
  if (!inventoryPanel.items) return;
  const normalized = Array.isArray(items) ? items : [];
  if (normalized.length === 0) {
    const empty = document.createElement("div");
    empty.className = "inventory-empty";
    empty.textContent = "비어 있음";
    inventoryPanel.items.replaceChildren(empty);
    return;
  }
  inventoryPanel.items.replaceChildren(
    ...normalized.map((item) => {
      const row = document.createElement("div");
      row.className = "inventory-item";
      row.textContent = item === "사과" ? "🍎 사과" : item === "오렌지" ? "🍊 오렌지" : item;
      return row;
    }),
  );
}

function goalLine(goal) {
  const div = document.createElement("div");
  const [rawName, rawState] = goal.split(":").map((item) => item.trim());
  const done = rawState === "done";
  div.className = `goal-card ${done ? "done" : "pending"}`;
  const icon = document.createElement("span");
  icon.className = "goal-icon";
  icon.textContent = done ? "✓" : goalIcon(rawName);
  const text = document.createElement("span");
  text.className = "goal-name";
  text.textContent = rawName;
  const state = document.createElement("span");
  state.className = "goal-state";
  state.textContent = done ? "완료" : "진행 전";
  div.append(icon, text, state);
  return div;
}

function goalIcon(goalName) {
  if (goalName.includes("NPC")) return "Q";
  if (goalName.includes("Maze") || goalName.includes("미로")) return "M";
  if (goalName.includes("Puzzle") || goalName.includes("퍼즐")) return "P";
  return "•";
}

function updateZone(zone) {
  const interactiveZone =
    zone.radius > 0 && (
      zone.required_behavior
      || zone.id.startsWith("puzzle_")
      || zone.id === "maze_exit"
      || zone.id === "maze_start"
      || zone.id === "npc1"
      || zone.id === "npc2"
      || zone.id === "apple_tree"
    );
  if (!interactiveZone) return;
  if (zoneMeshes.has(zone.id)) return;
  const color = zone.id === "puzzle_red"
    ? 0xef5b5b
    : zone.id === "puzzle_green"
        ? 0x55d887
        : zone.id === "puzzle_blue"
          ? 0x44a8ff
          : zone.id === "puzzle_yellow"
            ? 0xf5d15f
            : zone.id === "puzzle_purple"
              ? 0xb58cff
              : zone.id === "puzzle_play"
                ? 0xf5d15f
                : zone.id === "maze_exit"
                  ? 0x7dd3fc
                  : zone.id === "maze_start"
                    ? 0x67e8f9
                    : zone.id === "npc1"
                      ? 0x6ee7b7
                      : zone.id === "npc2"
                        ? 0xffb454
                        : zone.id === "apple_tree"
                          ? 0xf87171
                          : 0x6da8ff;
  const ring = new THREE.Mesh(
    new THREE.CylinderGeometry(zone.radius, zone.radius, 0.035, 40),
    new THREE.MeshStandardMaterial({
      color,
      transparent: true,
      opacity: 0.22,
      roughness: 0.58,
    }),
  );
  ring.position.set(zone.center.x, 0.02, zone.center.z);
  scene.add(ring);
  zoneMeshes.set(zone.id, ring);
}

function syncMazeWalls(obstacles) {
  const wallMat = mazeWallMeshes.material || new THREE.MeshStandardMaterial({ color: 0x223149, roughness: 0.82 });
  const activeIds = new Set();
  obstacles
    .filter((obstacle) => obstacle.id.startsWith("maze_wall_"))
    .forEach((obstacle) => {
      activeIds.add(obstacle.id);
      if (mazeWallMeshes.has(obstacle.id)) return;
      const width = obstacle.half_extent_x * 2;
      const depth = obstacle.half_extent_z * 2;
      const mesh = addBox(obstacle.id, [obstacle.center.x, 0.58, obstacle.center.z], [width, 1.16, depth], wallMat);
      mazeWallMeshes.set(obstacle.id, mesh);
    });
  mazeWallMeshes.forEach((mesh, id) => {
    if (id !== "material" && !activeIds.has(id)) mesh.visible = false;
  });
}

function updatePuzzleVisuals() {
  puzzlePadOrder.forEach((_, index) => {
    const flag = `puzzle_phase_${index + 1}`;
    const gauge = puzzleGaugeMeshes[index];
    if (!gauge) return;
    const active = Boolean(worldFlags[flag]);
    gauge.material.color.setHex(active ? 0x6fffc0 : 0x27344a);
    gauge.material.emissive?.setHex(active ? 0x0b3a24 : 0x000000);
  });
  if (puzzleCueActive) return;
  puzzlePadMeshes.forEach((mesh, padId) => {
    mesh.scale.y = worldFlags[padId] ? 1.6 : 1;
    mesh.position.y = mesh.userData.defaultY;
    restorePuzzlePadMaterial(mesh);
  });
}

function replayPuzzleCue(events) {
  const cue = events
    .slice()
    .reverse()
    .find((event) => event.data?.type === "puzzle_cue");
  if (!cue) return;
  const cueKey = JSON.stringify([cue.tick, cue.data.sequence]);
  if (cueKey === lastPuzzleCue) return;
  lastPuzzleCue = cueKey;
  const names = cue.data.sequence || [];
  setPuzzleDimmed(true);
  puzzleCueActive = true;
  const initialDelay = names.length > 1 ? 780 : 260;
  names.forEach((name, index) => {
    setTimeout(() => flashPuzzlePad(`puzzle_${name}`), initialDelay + index * 1180);
  });
  setTimeout(() => {
    puzzleCueActive = false;
    setPuzzleDimmed(false);
  }, initialDelay + names.length * 1180 + 420);
}

function updateDialogue(events) {
  if (!dialogueBox.root) return;
  const dialogue = events
    .slice()
    .reverse()
    .find((event) => event.data?.type === "dialogue");
  if (!dialogue) {
    closeDialogue();
    return;
  }
  const key = `${dialogue.tick}:${dialogue.data.speaker}:${dialogue.data.line}`;
  if (key === dialogueBox.lastKey) return;
  dialogueBox.speaker.textContent = dialogue.data.speaker || "NPC";
  dialogueBox.line.textContent = dialogue.data.line || "";
  dialogueBox.zoneId = dialogue.data.zone_id || null;
  dialogueBox.closeAt = performance.now() + Number(dialogue.data.close_after_ms || 5200);
  dialogueBox.root.classList.add("open");
  dialogueBox.lastKey = key;
  audio.play("open", 0.42);
}

function updateDialogueVisibility() {
  if (!dialogueBox.root?.classList.contains("open")) return;
  if (dialogueBox.closeAt && performance.now() > dialogueBox.closeAt) {
    closeDialogue();
    return;
  }
  if (!dialogueBox.zoneId) return;
  const nearest = nearestInteractionZone();
  if (!nearest || nearest.zoneId !== dialogueBox.zoneId || nearest.distance > 1.4) {
    closeDialogue();
  }
}

function closeDialogue() {
  dialogueBox.root?.classList.remove("open");
  dialogueBox.zoneId = null;
  dialogueBox.closeAt = 0;
}

function flashPuzzlePad(padId) {
  const mesh = puzzlePadMeshes.get(padId);
  if (!mesh) return;
  audio.play("confirm", 0.36);
  mesh.scale.y = 5.4;
  mesh.position.y = mesh.userData.defaultY + 0.34;
  mesh.material.color.copy(mesh.userData.defaultColor);
  mesh.material.emissive.copy(mesh.userData.defaultColor).multiplyScalar(1.05);
  setTimeout(() => {
    mesh.scale.y = 1;
    mesh.position.y = mesh.userData.defaultY;
    if (puzzleCueActive) dimPuzzlePadMaterial(mesh);
  }, 860);
}

function setPuzzleDimmed(dimmed) {
  puzzlePadMeshes.forEach((mesh) => {
    if (dimmed) dimPuzzlePadMaterial(mesh);
    else restorePuzzlePadMaterial(mesh);
  });
}

function dimPuzzlePadMaterial(mesh) {
  mesh.scale.y = 0.72;
  mesh.position.y = mesh.userData.defaultY - 0.035;
  mesh.material.color.copy(mesh.userData.defaultColor).multiplyScalar(0.16);
  mesh.material.emissive.setHex(0x000000);
}

function restorePuzzlePadMaterial(mesh) {
  mesh.scale.y = worldFlags[mesh.name.replace("_pad", "")] ? 2.4 : 1;
  mesh.position.y = mesh.userData.defaultY + (mesh.scale.y > 1 ? 0.16 : 0);
  mesh.material.color.copy(mesh.userData.defaultColor);
  mesh.material.emissive.copy(mesh.userData.defaultEmissive);
}

function updateActor(actor) {
  let mesh = actorMeshes.get(actor.id);
  if (!mesh) {
    mesh = createActorShell(actor);
    actorMeshes.set(actor.id, mesh);
    scene.add(mesh);
    loadActorModel(mesh, actor);
  }
  if (actor.id === "rhea" && shouldKeepLocalPlayerPose()) return;
  mesh.userData.behavior = actor.behavior;
  mesh.userData.gait = actor.gait;
  mesh.userData.targetPosition.set(actor.position.x, actor.position.y, actor.position.z);
  mesh.rotation.y = THREE.MathUtils.degToRad(actor.facing_degrees);
}

function shouldKeepLocalPlayerPose() {
  return (
    pressedKeys.size > 0
    || agentPlaybackActive
    || driveSync.pending
    || performance.now() < driveSync.localControlUntil
  );
}

function createActorShell(actor) {
  const group = new THREE.Group();
  const config = actorModelConfig(actor.id);
  group.position.set(actor.position.x, actor.position.y, actor.position.z);
  group.userData = {
    behavior: actor.behavior,
    gait: actor.gait,
    targetPosition: new THREE.Vector3(actor.position.x, actor.position.y, actor.position.z),
    mixer: null,
    actions: {},
    currentAction: null,
    usingFallback: true,
    jumpElapsed: 0,
    stepTimer: 0,
    fallback: createHumanoid(config.fallbackColor),
    visualRoot: null,
    visualBaseScale: 1,
  };
  group.add(group.userData.fallback);
  group.userData.visualRoot = group.userData.fallback;
  return group;
}

function loadActorModel(shell, actor) {
  const config = actorModelConfig(actor.id);
  gltfLoader.load(
    config.path,
    (gltf) => {
      shell.remove(shell.userData.fallback);
      const model = gltf.scene;
      model.name = `${actor.id}_${config.name}`;
      model.scale.setScalar(config.scale);
      model.rotation.y = config.rotationY;
      model.traverse((child) => {
        if (child.isMesh) {
          child.castShadow = false;
          child.receiveShadow = false;
        }
      });
      if (config.staticPose) poseStaticNpc(model);
      const actions = {};
      if (gltf.animations.length > 0) {
        const mixer = new THREE.AnimationMixer(model);
        gltf.animations.forEach((clip) => {
          actions[clip.name.toLowerCase()] = mixer.clipAction(clip);
        });
        aliasAction(actions, "walking", "walk");
        aliasAction(actions, "running", "run");
        aliasAction(actions, "standing", "idle");
        shell.userData.mixer = mixer;
        shell.userData.actions = actions;
      }
      shell.userData.usingFallback = false;
      shell.userData.visualRoot = model;
      shell.userData.visualBaseScale = config.scale;
      shell.add(model);
      setActorAction(shell, "idle");
      const clips = gltf.animations.map((clip) => clip.name).join(", ") || "static rigged character";
      writeConsole(`loaded ${config.name} for ${actor.id}: ${clips}`);
    },
    undefined,
    () => {
      writeConsole(`failed to load ${config.path}; using procedural fallback for ${actor.id}`);
    },
  );
}

function aliasAction(actions, sourceName, aliasName) {
  if (actions[aliasName] || !actions[sourceName]) return;
  actions[aliasName] = actions[sourceName];
}

function poseStaticNpc(model) {
  const upperLeft = model.getObjectByName("upperarm_l");
  const upperRight = model.getObjectByName("upperarm_r");
  const lowerLeft = model.getObjectByName("lowerarm_l");
  const lowerRight = model.getObjectByName("lowerarm_r");
  const handLeft = model.getObjectByName("hand_l");
  const handRight = model.getObjectByName("hand_r");
  if (upperLeft) {
    upperLeft.rotation.z += 1.15;
    upperLeft.rotation.x += 0.08;
  }
  if (upperRight) {
    upperRight.rotation.z -= 1.15;
    upperRight.rotation.x += 0.08;
  }
  if (lowerLeft) lowerLeft.rotation.z += 0.18;
  if (lowerRight) lowerRight.rotation.z -= 0.18;
  if (handLeft) handLeft.rotation.z += 0.08;
  if (handRight) handRight.rotation.z -= 0.08;
}

function actorModelConfig(actorId) {
  if (actorId === "npc1") {
    return {
      name: "threejs_xbot",
      path: "/static/assets/vendor/threejs/Xbot.glb",
      scale: 0.96,
      rotationY: Math.PI,
      fallbackColor: 0x69d9a7,
    };
  }
  if (actorId === "npc2") {
    return {
      name: "threejs_robot_expressive",
      path: "/static/assets/vendor/threejs/RobotExpressive/RobotExpressive.glb",
      scale: 0.42,
      rotationY: Math.PI,
      fallbackColor: 0xff9b54,
    };
  }
  return {
    name: "threejs_soldier",
    path: "/static/assets/vendor/threejs/Soldier.glb",
    scale: 1.05,
    rotationY: Math.PI,
    fallbackColor: 0x6fc7ff,
  };
}

function createHumanoid(color) {
  const group = new THREE.Group();
  const outfit = new THREE.MeshStandardMaterial({ color, roughness: 0.55 });
  const gear = new THREE.MeshStandardMaterial({ color: 0x172033, roughness: 0.78 });
  const skin = new THREE.MeshStandardMaterial({ color: 0xc89664, roughness: 0.62 });
  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.62, 0.3), outfit);
  torso.position.y = 0.9;
  const chest = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.18, 0.34), gear);
  chest.position.y = 1.14;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.19, 18, 14), skin);
  head.position.y = 1.38;
  const helmet = new THREE.Mesh(new THREE.SphereGeometry(0.205, 18, 8, 0, Math.PI * 2, 0, Math.PI / 2), gear);
  helmet.position.y = 1.43;
  const armL = limb(-0.38, 0.82, gear);
  const armR = limb(0.38, 0.82, gear);
  const legL = limb(-0.16, 0.28, gear);
  const legR = limb(0.16, 0.28, gear);
  group.add(torso, chest, head, helmet, armL, armR, legL, legR);
  group.userData = { armL, armR, legL, legR, behavior: "idle", gait: "walk" };
  return group;
}

function limb(x, y, material) {
  const mesh = new THREE.Mesh(new THREE.CapsuleGeometry(0.08, 0.48, 6, 10), material);
  mesh.position.set(x, y, 0);
  mesh.castShadow = true;
  return mesh;
}

function animate() {
  requestAnimationFrame(animate);
  const delta = Math.min(clock.getDelta(), 0.05);
  const elapsed = clock.elapsedTime;
  tickPlayerInput(delta);
  actorMeshes.forEach((actor) => animateActor(actor, elapsed, delta));
  updateInteractionHint(elapsed);
  updateDialogueVisibility();
  updateCamera(delta);
  renderer.render(scene, camera);
}

function tickPlayerInput(delta) {
  const actor = actorMeshes.get("rhea");
  if (!actor) return;
  if (agentPlaybackActive) return;

  const moved = moveActorWithKeys(actor, pressedKeys, delta, cameraControl.yaw);
  if (moved) {
    const running = pressedKeys.has("ShiftLeft") || pressedKeys.has("ShiftRight");
    maybePlayFootstep(actor, delta, running);
  } else if (actor.userData.jumpElapsed <= 0) {
    actor.userData.behavior = "idle";
    actor.userData.gait = "walk";
    actor.userData.stepTimer = 0;
  }

  driveSync.elapsed += delta;
  if ((moved || actor.userData.jumpElapsed > 0) && driveSync.elapsed >= driveSync.interval) {
    driveSync.elapsed = 0;
    syncDrive(
      actor,
      pressedKeys.has("ShiftLeft") || pressedKeys.has("ShiftRight"),
      actor.userData.jumpElapsed > 0,
      moved,
    );
  }
}

function moveActorWithKeys(actor, keys, delta, yawRadians) {
  const move = getMovementVectorForKeys(keys, yawRadians);
  if (move.lengthSq() === 0) {
    if (actor.userData.behavior !== "jump") {
      actor.userData.behavior = "idle";
      actor.userData.gait = "walk";
    }
    return false;
  }
  move.normalize();
  
  // Shift, ShiftLeft, ShiftRight 모두 달리기로 인식
  const running = keys.has("Shift") || keys.has("ShiftLeft") || keys.has("ShiftRight");
  const speed = running ? 7.5 : 3.8;
  const current = actor.userData.targetPosition.clone();
  const next = current.clone().addScaledVector(move, speed * delta);
  next.x = THREE.MathUtils.clamp(next.x, -worldBounds.x, worldBounds.x);
  next.z = THREE.MathUtils.clamp(next.z, -worldBounds.z, worldBounds.z);
  resolveNavigationCollision(current, next);
  actor.userData.targetPosition.copy(next);

  // 부드러운 회전 처리
  const targetRotation = Math.atan2(move.x, move.z);
  let deltaRotation = targetRotation - actor.rotation.y;
  while (deltaRotation < -Math.PI) deltaRotation += Math.PI * 2;
  while (deltaRotation > Math.PI) deltaRotation -= Math.PI * 2;
  actor.rotation.y += deltaRotation * Math.min(1, delta * 12);

  actor.userData.gait = running ? "run" : "walk";
  actor.userData.behavior = running ? "running" : "walking";
  driveSync.localControlUntil = performance.now() + 700;
  return true;
}

function maybePlayFootstep(actor, delta, running) {
  actor.userData.stepTimer -= delta;
  if (actor.userData.stepTimer <= 0 && actor.userData.jumpElapsed <= 0) {
    audio.play("step", running ? 0.78 : 0.55);
    actor.userData.stepTimer = running ? 0.24 : 0.42;
  }
}

function getMovementVectorForKeys(keys, yawRadians) {
  const forward = new THREE.Vector3(-Math.sin(yawRadians), 0, -Math.cos(yawRadians));
  const right = new THREE.Vector3(Math.cos(yawRadians), 0, -Math.sin(yawRadians));
  const move = new THREE.Vector3();
  if (keys.has("KeyW")) move.add(forward);
  if (keys.has("KeyS")) move.sub(forward);
  if (keys.has("KeyD")) move.add(right);
  if (keys.has("KeyA")) move.sub(right);
  return move;
}

async function playAgentInputBuffer(frames, cameraYawDegrees, playbackMessage = null) {
  const actor = actorMeshes.get("rhea");
  if (!actor) return;
  agentPlaybackActive = true;
  const yawRadians = THREE.MathUtils.degToRad(cameraYawDegrees);
  syncCameraYawForPlayback(yawRadians);
  try {
    for (const [index, frame] of frames.entries()) {
      const keys = new Set(frame.keys || []);
      const durationMs = Math.max(60, Math.min(1200, Number(frame.duration_ms || 100)));
      if (playbackMessage) {
        setConsoleMessageText(
          playbackMessage,
          `입력 재생 중 ${index + 1}/${frames.length}: ${(frame.keys || []).join("+") || "idle"} ${durationMs}ms`,
        );
      }
      if (keys.has("KeyE")) {
        actor.userData.behavior = "inspect";
        audio.play("confirm", 0.5);
        await delay(Math.max(180, durationMs));
        continue;
      }
      if (keys.has("Space")) startAgentJump(actor);
      const stepMs = 50;
      let elapsed = 0;
      const startPos = actor.position.clone();
      let lastPos = startPos.clone();
      let stuckCheckTime = 0;

      while (elapsed < durationMs) {
        const dt = Math.min(stepMs, durationMs - elapsed) / 1000;
        const moved = moveActorWithKeys(actor, keys, dt, yawRadians);
        
        if (moved) {
          const isRunning = keys.has("Shift") || keys.has("ShiftLeft") || keys.has("ShiftRight");
          maybePlayFootstep(actor, dt, isRunning);
          
          // 충돌 및 끼임 감지 (0.8초간 이동이 미미하면 중단)
          if (actor.position.distanceTo(lastPos) < 0.01) {
            stuckCheckTime += dt;
            if (stuckCheckTime > 0.8) {
              if (playbackMessage) {
                const currentText = playbackMessage.querySelector(".console-message-body").textContent;
                setConsoleMessageText(playbackMessage, `${currentText} (벽 충돌 감지로 중단)`);
              }
              return; // 전체 버퍼 중단
            }
          } else {
            stuckCheckTime = 0;
            lastPos.copy(actor.position);
          }
        }

        elapsed += stepMs;
        if (playbackMessage && elapsed % 200 === 0) {
          const progress = Math.round((elapsed / durationMs) * 100);
          setConsoleMessageText(
            playbackMessage,
            `입력 재생 중 ${index + 1}/${frames.length}: ${(frame.keys || []).join("+") || "idle"} (${progress}%)`
          );
        }
        await delay(stepMs);
      }
    }
  } finally {
    // 이동 루프 종료 후, 시각적 위치를 논리적 위치와 강제로 일치시켜 누적 오차 제거
    actor.position.copy(actor.userData.targetPosition);
    
    // 매쉬가 완전히 정착하고 카메라가 안정화될 때까지 아주 짧게 대기
    await delay(120);

    agentPlaybackActive = false;
    
    // 이동 완료 후 최신 화면을 서버에 동기화하여 에이전트의 다음 턴 시야를 확보
    const afterMovementScreenshot = captureSceneDataUrl();
    if (afterMovementScreenshot) {
      fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: "sync_screenshot", screenshot_data_url: afterMovementScreenshot }),
      }).catch(() => {});
    }

    if (!hasMovementKeys()) {
      actor.userData.behavior = "idle";
      actor.userData.gait = "walk";
      actor.userData.stepTimer = 0;
      // 최종 위치를 서버에 즉시 전송
      await syncDrive(actor, false, false, false);
    }
  }
}

function syncCameraYawForPlayback(yawRadians) {
  if (!Number.isFinite(yawRadians)) return;
  cameraControl.yaw = THREE.MathUtils.lerp(cameraControl.yaw, yawRadians, 0.65);
}

function applyCameraCommand(command) {
  const yawDelta = THREE.MathUtils.degToRad(Number(command.yaw_delta_degrees || 0));
  const pitchDelta = THREE.MathUtils.degToRad(Number(command.pitch_delta_degrees || 0));
  const zoomDelta = Number(command.zoom_delta || 0);
  const targetYaw = cameraControl.yaw + yawDelta;
  const targetPitch = THREE.MathUtils.clamp(cameraControl.pitch + pitchDelta, 0.22, 1.12);
  const targetDistance = THREE.MathUtils.clamp(cameraControl.distance + zoomDelta, 3.6, 11.5);
  const steps = 12;
  let step = 0;
  const lerpFactor = 0.22;
  function tick() {
    step++;
    cameraControl.yaw = THREE.MathUtils.lerp(cameraControl.yaw, targetYaw, lerpFactor);
    cameraControl.pitch = THREE.MathUtils.lerp(cameraControl.pitch, targetPitch, lerpFactor);
    cameraControl.distance = THREE.MathUtils.lerp(cameraControl.distance, targetDistance, lerpFactor);
    if (step < steps) requestAnimationFrame(tick);
    else {
      cameraControl.yaw = targetYaw;
      cameraControl.pitch = targetPitch;
      cameraControl.distance = targetDistance;
    }
  }
  requestAnimationFrame(tick);
}

function startAgentJump(actor) {
  if (actor.userData.jumpElapsed > 0) return;
  actor.userData.jumpElapsed = 0.001;
  actor.userData.behavior = "jump";
  actor.userData.jumpStartY = actor.position.y;
  audio.play("jump", 0.5);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function resolveNavigationCollision(current, next) {
  if (!isBlocked(next)) return;

  const xOnly = current.clone();
  xOnly.x = next.x;
  if (!isBlocked(xOnly)) {
    next.copy(xOnly);
    return;
  }

  const zOnly = current.clone();
  zOnly.z = next.z;
  if (!isBlocked(zOnly)) {
    next.copy(zOnly);
    return;
  }

  next.copy(current);
}

function isBlocked(position) {
  const actorRadius = 0.32;
  return navigationObstacles.some((obstacle) => {
    if (obstacle.disabled_by_flag && worldFlags[obstacle.disabled_by_flag]) return false;
    const center = obstacle.center;
    return (
      Math.abs(position.x - center.x) <= obstacle.half_extent_x + actorRadius &&
      Math.abs(position.z - center.z) <= obstacle.half_extent_z + actorRadius
    );
  });
}

function nearestInteractionZone() {
  const actor = actorMeshes.get("rhea");
  if (!actor) return null;
  let nearest = null;
  let nearestDistance = Infinity;
  zoneMeshes.forEach((mesh, zoneId) => {
    const distance = actor.position.distanceTo(mesh.position);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearest = { zoneId, mesh, distance };
    }
  });
  return nearest && nearest.distance <= 1.25 ? nearest : null;
}

function updateInteractionHint(elapsed) {
  const nearest = nearestInteractionZone();
  zoneMeshes.forEach((mesh) => {
    mesh.material.opacity = 0.2;
    mesh.scale.setScalar(1);
  });
  if (!nearest) {
    hud.interactionHint.textContent = "가까운 상호작용 대상 없음";
    hud.interactionHint.classList.remove("ready");
    return;
  }
  nearest.mesh.material.opacity = 0.38 + Math.sin(elapsed * 5) * 0.08;
  nearest.mesh.scale.setScalar(1.04);
  hud.interactionHint.textContent = `E 누르기: ${zoneDisplayNames.get(nearest.zoneId) || nearest.zoneId}`;
  hud.interactionHint.classList.add("ready");
}

async function contextInteract() {
  const actor = actorMeshes.get("rhea");
  if (!actor) return;
  await syncDrive(actor, actor.userData.gait === "run", actor.userData.jumpElapsed > 0, false);
  const response = await fetch("/api/input-buffer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      actor_id: "rhea",
      camera_yaw_degrees: THREE.MathUtils.radToDeg(cameraControl.yaw),
      frames: [{ keys: ["KeyE"], duration_ms: 80 }],
    }),
  });
  const payload = await response.json();
  const latestEvent = payload.state?.events?.at(-1)?.message || "";
  audio.play(latestEvent.includes("nothing") || latestEvent.includes("가까운 대상이 없습니다") ? "error" : "confirm", 0.62);
  await refreshState();
}

function startJump() {
  const actor = actorMeshes.get("rhea");
  if (!actor || actor.userData.jumpElapsed > 0) return;
  actor.userData.jumpElapsed = 0.001;
  actor.userData.behavior = "jump";
  actor.userData.jumpStartY = actor.position.y;
  audio.play("jump", 0.62);
  syncDrive(actor, actor.userData.gait === "run", true, false);
}

async function syncDrive(actor, running, jumping, moving = true) {
  const payload = {
    actor_id: "rhea",
    x: Number(actor.userData.targetPosition.x.toFixed(2)),
    z: Number(actor.userData.targetPosition.z.toFixed(2)),
    facing_degrees: Number(THREE.MathUtils.radToDeg(actor.rotation.y).toFixed(1)),
    gait: running ? "run" : "walk",
    jumping,
    moving,
  };
  const payloadKey = JSON.stringify(payload);
  if (!jumping && !moving && payloadKey === driveSync.lastPayload) return;
  if (driveSync.pending) {
    driveSync.queuedPayload = payload;
    return;
  }
  await sendDrivePayload(payload);
}

async function sendDrivePayload(payload) {
  const payloadKey = JSON.stringify(payload);
  if (!payload.jumping && payloadKey === driveSync.lastPayload) return;
  driveSync.lastPayload = payloadKey;
  driveSync.pending = true;
  try {
    await fetch("/api/drive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payloadKey,
    });
  } finally {
    driveSync.pending = false;
    if (driveSync.queuedPayload) {
      const nextPayload = driveSync.queuedPayload;
      driveSync.queuedPayload = null;
      await sendDrivePayload(nextPayload);
    }
  }
}

function animateActor(actor, elapsed, delta) {
  actor.position.lerp(actor.userData.targetPosition, Math.min(1, delta * 8.5));
  if (actor.userData.jumpElapsed > 0) {
    actor.userData.jumpElapsed += delta;
    const duration = 0.74;
    const t = actor.userData.jumpElapsed / duration;
    const phase = Math.min(t, 1);
    actor.position.y = Math.sin(phase * Math.PI) * 0.95;
    animateJumpPose(actor, phase);
    if (t >= 1) {
      actor.userData.jumpElapsed = 0;
      actor.position.y = 0;
      animateJumpPose(actor, 0);
      actor.userData.behavior = hasMovementKeys() ? actor.userData.behavior : "idle";
      actor.userData.gait = hasMovementKeys() ? actor.userData.gait : "walk";
      if (actor === actorMeshes.get("rhea")) audio.play("land", 0.68);
      if (actor === actorMeshes.get("rhea")) syncDrive(actor, false, false, hasMovementKeys());
    }
  }

  if (actor.userData.mixer) {
    actor.userData.mixer.update(delta);
    const state = actor.userData.behavior === "jump"
      ? "jump"
      : actor.userData.behavior === "running"
      ? "run"
      : actor.userData.behavior === "walking"
        ? "walk"
        : "idle";
    setActorAction(actor, state);
    return;
  }

  if (!actor.userData.usingFallback) return;

  const fallbackRig = actor.userData.fallback?.userData;
  if (!fallbackRig?.armL || !fallbackRig?.armR || !fallbackRig?.legL || !fallbackRig?.legR) {
    return;
  }

  const locomotion = actor.userData.behavior === "running" || actor.userData.behavior === "walking";
  const speed = actor.userData.behavior === "running" ? 8 : 4;
  const swing = locomotion ? Math.sin(elapsed * speed) * 0.45 : 0;
  fallbackRig.armL.rotation.x = swing;
  fallbackRig.armR.rotation.x = -swing;
  fallbackRig.legL.rotation.x = -swing;
  fallbackRig.legR.rotation.x = swing;
  fallbackRig.armR.rotation.z = actor.userData.behavior === "wave" ? -1.35 : 0;
}

function animateJumpPose(actor, phase) {
  const root = actor.userData.visualRoot;
  if (!root) return;
  const lift = Math.sin(phase * Math.PI);
  const crouch = phase < 0.18 ? 1 - phase / 0.18 : phase > 0.82 ? (phase - 0.82) / 0.18 : 0;
  root.rotation.x = -lift * 0.12;
  const base = actor.userData.visualBaseScale || 1;
  const yScale = base * (1 - crouch * 0.08);
  const xzScale = base * (1 + crouch * 0.035);
  root.scale.set(xzScale, yScale, xzScale);
}

function setActorAction(actor, state) {
  const actions = actor.userData.actions;
  const nextAction = actions[state] || actions.idle || actions["idle"] || Object.values(actions)[0];
  if (!nextAction || actor.userData.currentAction === nextAction) return;
  nextAction.reset().fadeIn(0.18).play();
  if (actor.userData.currentAction) actor.userData.currentAction.fadeOut(0.18);
  actor.userData.currentAction = nextAction;
}

function updateCamera(delta) {
  const actor = actorMeshes.get("rhea");
  const desiredTarget = actor
    ? actor.position.clone().add(new THREE.Vector3(0, 1.18, 0))
    : new THREE.Vector3(-2.5, 1.1, 1.0);
  cameraControl.target.lerp(desiredTarget, Math.min(1, delta * 6));

  const radius = cameraControl.distance;
  const horizontal = Math.cos(cameraControl.pitch) * radius;
  const offset = new THREE.Vector3(
    Math.sin(cameraControl.yaw) * horizontal,
    Math.sin(cameraControl.pitch) * radius,
    Math.cos(cameraControl.yaw) * horizontal,
  );
  camera.position.copy(cameraControl.target).add(offset);
  camera.lookAt(cameraControl.target);
}

function createAudioBus() {
  const soundPaths = {
    click: "/static/assets/audio/ui_click.ogg",
    confirm: "/static/assets/audio/ui_confirm.ogg",
    open: "/static/assets/audio/ui_open.ogg",
    error: "/static/assets/audio/ui_move.wav",
    jump: "/static/assets/audio/jump_whoosh.ogg",
    land: "/static/assets/audio/jump_land.wav",
    step: [
      "/static/assets/audio/footstep00.ogg",
      "/static/assets/audio/footstep01.ogg",
      "/static/assets/audio/footstep02.ogg",
      "/static/assets/audio/footstep03.ogg",
    ],
  };
  const pool = new Map();
  let stepIndex = 0;
  let unlocked = false;

  function makeAudio(path) {
    const element = new Audio(path);
    element.preload = "auto";
    return element;
  }

  Object.entries(soundPaths).forEach(([name, value]) => {
    if (Array.isArray(value)) pool.set(name, value.map(makeAudio));
    else pool.set(name, makeAudio(value));
  });

  return {
    unlock() {
      unlocked = true;
    },
    play(name, volume = 0.45) {
      if (!unlocked) return;
      const entry = pool.get(name);
      if (!entry) return;
      const sound = Array.isArray(entry) ? entry[stepIndex++ % entry.length] : entry;
      sound.pause();
      sound.currentTime = 0;
      sound.volume = volume;
      sound.play().catch(() => {});
    },
  };
}

function captureSceneDataUrl() {
  try {
    renderer.render(scene, camera);
    return renderer.domElement.toDataURL("image/png");
  } catch {
    return null;
  }
}

function writeConsole(text) {
  appendConsoleMessage("system", text);
}

function appendObservationResponse(event) {
  const response = event.response || {};
  const lines = [];
  if (response.message) lines.push(`결과: ${response.message}`);
  if (response.player) {
    const nearby = response.player.nearby_interaction?.name || "none";
    const position = response.player.debug_position
      ? `, 위치=x:${response.player.debug_position.x}, z:${response.player.debug_position.z}`
      : "";
    lines.push(
      `캐릭터: ${response.player.id || "rhea"} · ${response.player.behavior || "unknown"} · ${response.player.gait || "unknown"} · nearby=${nearby}${position}`,
    );
  }
  if (response.navigation_observation?.local_clearance) {
    const clearance = Object.entries(response.navigation_observation.local_clearance)
      .map(([key, value]) => `${key}:${value}`)
      .join(" · ");
    lines.push(`주변 이동 가능성: ${clearance}`);
  }
  if (response.navigation_observation?.visible_landmarks?.length) {
    lines.push("보이는 목적지:");
    response.navigation_observation.visible_landmarks
      .slice(0, 5)
      .forEach((item) => lines.push(`- ${item.name}: ${item.direction}, ${item.distance}, ${item.debug_position || ""}`));
  }
  if (response.flags) {
    const visibleFlags = ["quest_complete", "maze_escaped", "puzzle_solved"]
      .map((flag) => `${flag}=${Boolean(response.flags[flag])}`)
      .join(", ");
    lines.push(`완료 플래그: ${visibleFlags}`);
  }
  if (response.goals?.length) {
    lines.push(`목표: ${response.goals.join(" · ")}`);
  }
  if (response.last_events?.length) {
    lines.push("최근 이벤트:");
    response.last_events.forEach((item) => lines.push(`- ${item.message}`));
  }
  lines.push("이 관찰 내용이 Gemini에 tool response로 전달되었습니다.");

  return appendConsoleMessage("tool", lines.join("\n"), {
    label: `Tool Result · ${event.name}`,
    model: currentTurnModel,
    agentName: currentTurnAgentName,
    variant: "tool-response",
  });
}

function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

function appendAgentInputPacket(command, dataUrl) {
  const message = document.createElement("article");
  message.className = "console-message system image-message";
  const label = document.createElement("div");
  label.className = "console-message-label";
  label.textContent = "ADK Agent Input";
  const body = document.createElement("div");
  body.className = "console-message-body";
  body.textContent = [
    `user message: ${command}`,
    dataUrl
      ? "image: attached PNG canvas capture preview below"
      : "image: capture unavailable",
    "state: inspect_game_state supplies coarse position, local clearance, visible landmarks, and broad flags; no hidden route or puzzle answer payloads",
  ].join("\n");
  message.append(label, body);
  if (!dataUrl) {
    consoleLog.append(message);
    scrollConsole();
    return;
  }
  const image = document.createElement("img");
  image.src = dataUrl;
  image.alt = "Canvas capture sent to Gemini";
  image.onload = scrollConsole;
  message.append(image);
  consoleLog.append(message);
  scrollConsole();
}

function appendAgentResponse(payload) {
  appendConsoleMessage("agent", payload.answer || payload.message || summarizePayload(payload), {
    model: payload.model || currentTurnModel,
    agentName: payload.agent_name || "",
  });
  if (payload.trace?.nodes?.length) appendTrace(payload.trace);
}

function summarizePayload(payload) {
  if (payload.message) return payload.message;
  if (payload.final_state) return `QA complete: ${payload.final_state.status}`;
  if (payload.issues) return payload.issues.join("\n");
  if (payload.state) return `State: ${payload.state.status}`;
  return JSON.stringify(payload, null, 2);
}

function appendConsoleMessage(kind, text, options = {}) {
  const message = document.createElement("article");
  message.className = `console-message ${kind}`;
  if (options.variant) message.classList.add(options.variant);
  
  // 에이전트 이름에 따른 전용 색상 클래스 추가
  if (options.agentName) {
    const agentClass = getAgentColorClass(options.agentName);
    if (agentClass) message.classList.add(agentClass);
  }

  const label = document.createElement("div");
  label.className = "console-message-label";
  const labelText = document.createElement("span");
  labelText.textContent = options.label || (
    kind === "user" ? "You" : kind === "agent" ? "Agent" : kind === "tool" ? "Tool" : "System"
  );
  label.append(labelText);
  if (options.model) label.append(modelBadge(options.model, options.agentName));
  const body = document.createElement("div");
  body.className = "console-message-body";
  body.textContent = text;
  message.append(label, body);
  consoleLog.append(message);
  scrollConsole();
  return message;
}

function getAgentColorClass(agentName) {
  const lowerName = agentName.toLowerCase();
  if (lowerName.includes("supervisor") || lowerName.includes("감독자")) return "agent-supervisor";
  if (lowerName.includes("strategist") || lowerName.includes("전략")) return "agent-strategy";
  if (lowerName.includes("observer") || lowerName.includes("관측")) return "agent-observer";
  if (lowerName.includes("actor") || lowerName.includes("행동")) return "agent-actor";
  return "";
}

function modelBadge(model, agentName = "") {
  const badge = document.createElement("span");
  badge.className = "model-badge";
  badge.textContent = agentName ? `${agentName} · ${model}` : model;
  return badge;
}

function setConsoleMessageModel(message, model, agentName = "") {
  const label = message.querySelector(".console-message-label");
  if (!label || label.querySelector(".model-badge")) return;
  label.append(modelBadge(model, agentName));
  
  // 에이전트 이름에 따른 전용 색상 클래스 동적 추가
  const agentClass = getAgentColorClass(agentName);
  if (agentClass) message.classList.add(agentClass);
}

function setConsoleMessageText(message, text) {
  const body = message.querySelector(".console-message-body");
  if (body) body.textContent = text;
  scrollConsole();
}

function cameraCommandSummary(command) {
  const yaw = Number(command.yaw_delta_degrees || 0).toFixed(1);
  const pitch = Number(command.pitch_delta_degrees || 0).toFixed(1);
  const zoom = Number(command.zoom_delta || 0).toFixed(2);
  return `카메라 조작: yaw ${yaw}도, pitch ${pitch}도, zoom ${zoom}`;
}

function compactText(text, limit = 720) {
  return text.length <= limit ? text : `${text.slice(0, limit - 3)}...`;
}

function summarizeFrames(frames) {
  return frames
    .slice(0, 8)
    .map((frame) => `[${(frame.keys || []).join("+") || "idle"} ${frame.duration_ms || 100}ms]`)
    .join(" ");
}

function appendTrace(trace) {
  const section = document.createElement("section");
  section.className = "trace-strip";

  const header = document.createElement("div");
  header.className = "trace-header";
  const title = document.createElement("strong");
  title.textContent = "Agent Trace";
  const chain = document.createElement("span");
  chain.textContent = compactTraceChain(trace);
  header.append(title, chain);
  section.append(header);

  const nodeList = document.createElement("div");
  nodeList.className = "trace-node-list";
  trace.nodes.forEach((node, index) => nodeList.append(traceNodeCard(node, index)));
  section.append(nodeList);

  consoleLog.append(section);
  scrollConsole();
}

function traceNodeCard(node, index) {
  const details = document.createElement("details");
  details.className = `trace-node ${node.type}`;
  if (index < 2) details.open = true;

  const summary = document.createElement("summary");
  const badge = document.createElement("span");
  badge.className = "trace-badge";
  badge.textContent = node.type;
  const title = document.createElement("span");
  title.className = "trace-title";
  title.textContent = `${node.id} · ${node.title}`;
  const model = document.createElement("span");
  model.className = "trace-model";
  model.textContent = node.model || "runtime tool";
  summary.append(badge, title, model);

  const io = document.createElement("div");
  io.className = "trace-io";
  io.append(traceIoRow("input", node.input_summary || "runtime observation"));
  io.append(traceIoRow("output", node.output_summary || "no output summary"));
  details.append(summary, io);
  return details;
}

function traceIoRow(labelText, valueText) {
  const row = document.createElement("div");
  row.className = "trace-io-row";
  const label = document.createElement("span");
  label.textContent = labelText;
  const value = document.createElement("p");
  value.textContent = valueText;
  row.append(label, value);
  return row;
}

function compactTraceChain(trace) {
  if (!trace.edges?.length) return `${trace.nodes.length} nodes`;
  return trace.edges.map((edge) => `${edge.from} -> ${edge.to}`).join(" · ");
}

function scrollConsole() {
  consoleLog.scrollTop = consoleLog.scrollHeight;
}

function onResize() {
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
}

const consoleMaximize = document.getElementById("consoleMaximize");
if (consoleMaximize) {
  consoleMaximize.addEventListener("click", () => {
    document.body.classList.toggle("console-maximized");
    consoleMaximize.textContent = document.body.classList.contains("console-maximized") ? "축소" : "최대화";
    onResize();
    // 캔버스 크기 전환 애니메이션(0.3s) 후 다시 한번 리사이즈하여 정확한 크기 보정
    setTimeout(onResize, 310);
  });
}
