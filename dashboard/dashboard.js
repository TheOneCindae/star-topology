const feed = document.querySelector("#activityFeed");
const nodeCount = document.querySelector("#nodeCount");
const hubStatus = document.querySelector("#hubStatus");
const connectedNodes = new Set();

function renderNodes() {
  nodeCount.textContent = `${connectedNodes.size} / 4`;
  document.querySelectorAll("[data-node]").forEach(node => {
    const id = Number(node.dataset.node);
    const connected = connectedNodes.has(id);
    node.classList.toggle("connected", connected);
    node.querySelector("span").textContent = connected ? "CONNECTED" : "DISCONNECTED";
  });
}

function addEvent(event) {
  const payload = event.payload || {};
  if (event.kind === "client_connected") connectedNodes.add(payload.node_id);
  if (event.kind === "client_disconnected") connectedNodes.delete(payload.node_id);
  renderNodes();

  if (!["transfer_approved", "transfer_denied", "frame_forwarded"].includes(event.kind)) return;
  const item = document.createElement("div");
  item.className = `event ${event.kind === "transfer_approved" ? "approved" : ""} ${event.kind === "transfer_denied" ? "denied" : ""}`;
  const route = payload.src && payload.dst ? `Node ${payload.src} → Node ${payload.dst}` : "";
  item.textContent = `${event.kind.replaceAll("_", " ").toUpperCase()}  ${route} ${payload.reason ? `(${payload.reason})` : ""}`;
  feed.querySelector(".empty")?.remove();
  feed.prepend(item);
  while (feed.children.length > 12) feed.lastElementChild.remove();
}

async function loadStatus() {
  const response = await fetch("/api/status");
  if (!response.ok) throw new Error("Hub unavailable");
  const data = await response.json();
  data.clients.forEach(id => connectedNodes.add(id));
  renderNodes();
  hubStatus.textContent = "ONLINE";
}

function connectEvents() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${location.host}/ws/events`);
  socket.onmessage = event => addEvent(JSON.parse(event.data));
  socket.onclose = () => {
    hubStatus.textContent = "RECONNECTING";
    setTimeout(connectEvents, 2000);
  };
}

loadStatus().then(connectEvents).catch(() => { hubStatus.textContent = "OFFLINE"; });
