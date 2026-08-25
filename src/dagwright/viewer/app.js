const pretty = (value) => JSON.stringify(value, null, 2);
const short = (value) => `${value.slice(0, 10)}…${value.slice(-8)}`;

function renderSummary(data) {
  const cards = [
    ["Nodes", data.summary.nodes], ["Edges", data.summary.edges],
    ["Artifacts", data.summary.artifacts], ["Contract SHA-256", short(data.summary.contractDigest)],
    ["IR SHA-256", short(data.summary.irDigest)], ["Manifest SHA-256", short(data.summary.manifestDigest)],
  ];
  document.querySelector("#summary").replaceChildren(...cards.map(([label, value]) => {
    const card = document.createElement("article");
    const caption = document.createElement("span"); caption.textContent = label;
    const strong = document.createElement("strong"); strong.textContent = value;
    card.append(caption, strong); return card;
  }));
}

function renderGraph(graph) {
  const names = Object.fromEntries(graph.nodes.map((node) => [node.id, node.name]));
  const incoming = Object.fromEntries(graph.nodes.map((node) => [node.id, []]));
  graph.edges.forEach((edge) => incoming[edge.target].push(edge));
  const canvas = document.querySelector("#graph-canvas");
  graph.nodes.forEach((node) => {
    const item = document.createElement("article"); item.className = `node node-${node.kind}`;
    const kind = document.createElement("span"); kind.textContent = node.kind;
    const name = document.createElement("strong"); name.textContent = node.name;
    item.append(kind, name);
    incoming[node.id].forEach((edge) => {
      const dependency = document.createElement("small");
      dependency.textContent = `← ${names[edge.source]} · ${edge.kind}`; item.append(dependency);
    });
    canvas.append(item);
  });
}

function renderPlan(plan) {
  const list = document.querySelector("#plan-list");
  plan.steps.forEach((step) => {
    const row = document.createElement("article"); row.className = "plan-step";
    const position = document.createElement("b"); position.textContent = String(step.position).padStart(2, "0");
    const body = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = `${step.kind} / ${step.name}`;
    const dependencies = document.createElement("small");
    dependencies.textContent = step.dependencies.length ? `${step.dependencies.length} dependencies` : "root node";
    body.append(title, dependencies); row.append(position, body); list.append(row);
  });
}

function renderArtifacts(artifacts) {
  const list = document.querySelector("#artifact-list"); const content = document.querySelector("#artifact-content");
  artifacts.forEach((artifact, index) => {
    const button = document.createElement("button"); button.textContent = artifact.path;
    button.title = `${artifact.role} · ${artifact.size} bytes · ${artifact.sha256}`;
    button.addEventListener("click", () => {
      list.querySelectorAll("button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      try { content.textContent = pretty(JSON.parse(artifact.content)); } catch { content.textContent = artifact.content; }
    });
    list.append(button); if (index === 0) button.click();
  });
}

document.querySelectorAll("nav button").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll("nav button, .panel").forEach((item) => item.classList.remove("active"));
  button.classList.add("active"); document.querySelector(`#${button.dataset.panel}`).classList.add("active");
}));

fetch("/api/snapshot").then((response) => {
  if (!response.ok) throw new Error(`Viewer API returned ${response.status}`); return response.json();
}).then((data) => {
  document.querySelector("#product-name").textContent = `${data.product.name} · ${data.product.version}`;
  document.querySelector("#product-description").textContent = `${data.product.description} Owner: ${data.product.owner}.`;
  renderSummary(data); renderGraph(data.graph); renderPlan(data.plan); renderArtifacts(data.artifacts);
  document.querySelector("#contract pre").textContent = pretty(data.contract);
  document.querySelector("#ir pre").textContent = pretty(data.ir);
  document.querySelector("#manifest pre").textContent = pretty(data.manifest);
}).catch((error) => { document.querySelector("#product-name").textContent = "Viewer failed"; document.querySelector("#product-description").textContent = error.message; });
