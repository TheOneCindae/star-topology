const status = document.querySelector("#status");
const events = document.querySelector("#events");
async function refresh() {
  const response = await fetch("/api/status");
  const data = await response.json();
  status.textContent = `Connected clients: ${data.clients.join(", ") || "none"}`;
}
function addEvent(event) {
  const item = document.createElement("li");
  item.textContent = `${event.kind}: ${JSON.stringify(event.payload)}`;
  events.prepend(item);
}
refresh().catch(() => { status.textContent = "Server unavailable"; });
const scheme = location.protocol === "https:" ? "wss" : "ws";
const socket = new WebSocket(`${scheme}://${location.host}/ws/events`);
socket.onmessage = event => addEvent(JSON.parse(event.data));
