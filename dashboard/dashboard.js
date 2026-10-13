const feed = document.querySelector("#activityFeed");
const nodeCount = document.querySelector("#nodeCount");
const hubStatus = document.querySelector("#hubStatus");
const connectedNodes = new Set();
const counters = {
  ack_sent: document.querySelector("#ackCount"),
  frame_lost: document.querySelector("#lossCount"),
  frame_corrupted: document.querySelector("#corruptCount"),
  frame_corrupt: document.querySelector("#corruptCount"),
  collision: document.querySelector("#collisionCount"),
  retransmission: document.querySelector("#retryCount"),
};

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
  if (counters[event.kind]) {
    counters[event.kind].textContent = Number(counters[event.kind].textContent) + 1;
  }

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
  const stats = data.statistics || {};
  for (const [kind, element] of Object.entries(counters)) {
    element.textContent = stats[kind] || 0;
  }

  async function adminRequest(path, method, body) {
    const response = await fetch(`/api${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Token": document.querySelector("#adminToken").value,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Request failed");
    return result;
  }

  function showAdminResult(message) {
    document.querySelector("#adminResult").textContent = message;
  }

  document.querySelector("#provisionNode").onclick = async () => {
    try {
      const id = Number(document.querySelector("#adminNodeId").value);
      const name = document.querySelector("#adminNodeName").value;
      const result = await adminRequest("/admin/nodes", "POST", { node_id: id, name });
      showAdminResult(`Node ${result.node_id} credential: ${result.credential}`);
      await loadStatus();
    } catch (error) { showAdminResult(error.message); }
  };

  document.querySelector("#revokeNode").onclick = async () => {
    try {
      const id = Number(document.querySelector("#adminNodeId").value);
      const result = await adminRequest(`/admin/nodes/${id}/revoke`, "POST");
      showAdminResult(`Node ${result.node_id} revoked`);
      await loadStatus();
    } catch (error) { showAdminResult(error.message); }
  };

  async function setPermission(allowed) {
    try {
      const source_id = Number(document.querySelector("#permissionSource").value);
      const destination_id = Number(document.querySelector("#permissionDestination").value);
      await adminRequest("/admin/permissions", "PUT", {
        source_id, destination_id, message_type: 3, allowed,
      });
      showAdminResult(`DATA ${allowed ? "allowed" : "denied"}: ${source_id} → ${destination_id}`);
      await loadStatus();
    } catch (error) { showAdminResult(error.message); }
  }

  document.querySelector("#allowPermission").onclick = () => setPermission(true);
  document.querySelector("#denyPermission").onclick = () => setPermission(false);
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
