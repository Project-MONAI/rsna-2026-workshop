import { promises as fs } from "node:fs";
import path from "node:path";
import {
  FileBackedProjectRegistry, FileBackedWorkspaceRegistry,
  createPersistedProjectRecord, createPersistedWorkspaceRecord,
} from "/usr/local/lib/node_modules/@getpaseo/server/dist/server/server/workspace-registry.js";
import {
  generateProjectId, generateWorkspaceId,
} from "/usr/local/lib/node_modules/@getpaseo/server/dist/server/server/workspace-registry-model.js";
import { getOrCreateServerId } from "/usr/local/lib/node_modules/@getpaseo/server/dist/server/server/server-id.js";

const logger = { child() { return this; }, info() {}, warn: console.warn, error: console.error };

export function browserDefaultsBootstrap(model) {
  return `<script>{
    try{
      const storage=window.localStorage,marker="miagent:browser-defaults:v1";
      const read=key=>{const value=JSON.parse(storage.getItem(key)||"{}");return value&&typeof value==="object"&&!Array.isArray(value)?value:{}};
      if(storage.getItem(marker)!=="seeded"){
        const settings=read("@paseo:app-settings");
        storage.setItem("@paseo:app-settings",JSON.stringify({...settings,sendBehavior:"queue"}));
        const preferences=read("@paseo:create-agent-preferences");
        const providers=preferences.providerPreferences||{},opencode=providers.opencode||{};
        storage.setItem("@paseo:create-agent-preferences",JSON.stringify({...preferences,provider:"opencode",providerPreferences:{...providers,opencode:{...opencode,model:${JSON.stringify(model)},featureValues:{...opencode.featureValues,auto_accept:true}}}}));
        storage.setItem(marker,"seeded");
      }
      const panels=read("panel-state"),state=panels.state||{};
      storage.setItem("panel-state",JSON.stringify({...panels,version:panels.version??16,state:{...state,desktop:{...state.desktop,agentListOpen:false}}}));
    }catch(error){console.warn("[miagent-paseo] Could not seed browser defaults",error)}
  }</script>`;
}

export function staleRouteBootstrap(serverId) {
  return `<script>{
    const serverId=${JSON.stringify(serverId)};
    // Re-probe only obsolete connections to this page's endpoint. Keep all
    // unrelated hosts and the persisted chat/tab data.
    try{
      const storage=window.localStorage,key="@paseo:daemon-registry";
      const hosts=JSON.parse(storage.getItem(key));
      const current=new URL(window.location.href);
      const sameEndpoint=connection=>{
        if(connection.type!=="directTcp")return false;
        try{return new URL(current.protocol+"//"+connection.endpoint).host===current.host}catch{return false}
      };
      if(Array.isArray(hosts)){
        let changed=false;
        const retained=hosts.flatMap(host=>{
          if(host.serverId===serverId||!Array.isArray(host.connections))return [host];
          const connections=host.connections.filter(connection=>!sameEndpoint(connection));
          if(connections.length===host.connections.length)return [host];
          changed=true;
          return connections.length?[{...host,connections,preferredConnectionId:connections[0].id}]:[];
        });
        if(changed)storage.setItem(key,JSON.stringify(retained));
      }
    }catch{}
    const host=window.location.pathname.match(/^\\/h\\/([^/]+)(?:\\/|$)/);
    if(host&&decodeURIComponent(host[1])!==serverId){
      window.history.replaceState(null,"","/?paseo=1");
    }
  }</script>`;
}

export function labPreviewBootstrap(route, key, introFile = "01_overview.html") {
  const hostPrefix = route.slice(0, route.indexOf("/workspace/") + "/workspace/".length);
  return `<script>{
    const prefix=${JSON.stringify(hostPrefix)},baseKey=${JSON.stringify(key)},intro=${JSON.stringify(introFile)};
    let current=null,key=null,done=false,deadline=0;
    let folder=false,file=false,preview=false,pending=false;
      const visible=element=>element&&element.getClientRects().length>0;
      const find=id=>Array.from(document.querySelectorAll('[data-testid]')).find(element=>element.dataset.testid===id&&visible(element));
      const open=()=>{
        const pathname=window.location.pathname;
        if(!pathname.startsWith(prefix)||!pathname.slice(prefix.length)||pathname.slice(prefix.length).includes("/"))return;
        if(current!==pathname){
          current=pathname;key=baseKey+":"+pathname.slice(prefix.length);
          folder=false;file=false;preview=false;done=false;deadline=Date.now()+30000;
          try{done=localStorage.getItem(key)==="seen"}catch{}
        }
        if(done||Date.now()>deadline)return;
        if(pathname===${JSON.stringify(route)}&&!window.__MIAGENT_COMPOSER_READY__)return;
        const pane=find("workspace-file-pane");
        if(file&&pane){
          const button=find("file-mode-preview");
          if(button&&!preview){preview=true;button.click();return}
          if(preview&&pane.querySelector("iframe")){
            try{localStorage.setItem(key,"seen")}catch{}done=true;return;
          }
        }
        const tab=find("workspace-tab-file_lab/"+intro);
        if(tab&&!file){file=true;tab.click();return}
        const explorer=find("workspace-explorer-sidebar")||find("explorer-content-area");
        if(!explorer){const toggle=find("workspace-explorer-toggle");if(toggle)toggle.click();return}
        const files=find("explorer-sidebar-tab-files")||find("explorer-tab-files");
        if(!find("file-explorer-tree-scroll")){if(files)files.click();return}
        const rows=Array.from(explorer.querySelectorAll('[data-testid]')).filter(element=>/^file-explorer-row-[0-9]+-name$/.test(element.dataset.testid));
        const doc=rows.find(element=>element.textContent===intro);
        if(doc&&!file){file=true;doc.click();return}
        const lab=rows.find(element=>element.textContent==="lab");
        if(lab&&!folder){folder=true;lab.click()}
      };
      const schedule=()=>{if(!pending){pending=true;requestAnimationFrame(()=>{pending=false;open()})}};
      const observer=new MutationObserver(schedule);
      observer.observe(document.documentElement,{childList:true,subtree:true,attributes:true});
      window.addEventListener("popstate",schedule);
      schedule();
  }</script>`;
}

export async function configureWorkspace(home, cwd, sourceUi, targetUi) {
  await fs.access(path.join(cwd, "opencode.json"));
  const directory = path.join(home, "projects");
  await fs.mkdir(directory, { recursive: true });
  const projects = new FileBackedProjectRegistry(path.join(directory, "projects.json"), logger);
  const workspaces = new FileBackedWorkspaceRegistry(path.join(directory, "workspaces.json"), logger);
  // Load before writing so unrelated projects and existing sessions survive restarts.
  const now = new Date().toISOString();
  let project = (await projects.list()).find(p => p.rootPath === cwd && !p.archivedAt);
  if (!project) {
    project = createPersistedProjectRecord({
      projectId: generateProjectId(), rootPath: cwd, kind: "non_git",
      displayName: "MIAgent", createdAt: now, updatedAt: now,
    });
    await projects.upsert(project);
  }
  let workspace = (await workspaces.list()).find(w => w.cwd === cwd && w.projectId === project.projectId && !w.archivedAt);
  if (!workspace) {
    workspace = createPersistedWorkspaceRecord({
      workspaceId: generateWorkspaceId(), projectId: project.projectId, cwd,
      kind: "directory", displayName: "MIAgent", createdAt: now, updatedAt: now,
    });
    await workspaces.upsert(workspace);
  }
  const serverId = getOrCreateServerId(home, { logger });
  const route = `/h/${encodeURIComponent(serverId)}/workspace/${encodeURIComponent(workspace.workspaceId)}`;
  // A small writable overlay keeps the vendor assets untouched. Paseo serves
  // compressed assets normally, but always reads the overlaid index as plain HTML.
  await fs.mkdir(targetUi, { recursive: true });
  for (const entry of await fs.readdir(sourceUi)) {
    if (entry.startsWith("index.html")) continue;
    try {
      await fs.symlink(path.join(sourceUi, entry), path.join(targetUi, entry));
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
    }
  }
  // Wait for the daemon snapshot to populate the sidebar, then use Paseo's
  // own navigation handler. Early deep links can race initial connection.
  const selector = `[data-testid="sidebar-workspace-row-${serverId}:${workspace.workspaceId}"]`;
  const modelSelector = `[data-testid="model-row-opencode-${process.env.OPENCODE_MODEL ?? "miagent-llm/Qwen/Qwen3.8-27B-FP8"}"]`;
  const redirect = `<script>if(window.location.pathname==="/"||window.location.pathname===${JSON.stringify(route)}){
    const route=${JSON.stringify(route)};
    let selected=window.location.pathname===route,composer=false,requested=false,menu=false,expanded=false,provider=false,chosen=false,pending=false;
    const ready=element=>element&&element.getAttribute("aria-disabled")!=="true"&&!element.disabled;
    const closed=new Set();
    const open=()=>{
      const host=window.location.pathname.match(/^\\/h\\/([^/]+)(?:\\/|$)/);
      if(host&&decodeURIComponent(host[1])!==${JSON.stringify(serverId)})selected=false;
      if(chosen){
        const sheet=Array.from(document.querySelectorAll('[data-testid="agent-controls-model-browser-sheet"],[data-testid="agent-controls-model-sheet"]')).reverse().find(element=>!closed.has(element.dataset.testid));
        const close=sheet&&sheet.parentElement.querySelector('[aria-label="Close"]');
        if(close){closed.add(sheet.dataset.testid);close.click();schedule()}
        else{observer.disconnect();clearInterval(timer);window.WebSocket=NativeWebSocket;window.__MIAGENT_COMPOSER_READY__=true}
        return;
      }
      const row=document.querySelector(${JSON.stringify(selector)});
      if(!selected&&ready(row)){selected=true;row.click()}
      const agent=document.querySelector('[data-testid="workspace-new-tab-agent"]');
      if(selected&&!composer&&ready(agent)){requested=true;agent.click();return}
      const trigger=document.querySelector('[data-testid="combined-model-selector"]');
      if(selected&&!composer&&trigger&&!requested){
        observer.disconnect();clearInterval(timer);window.WebSocket=NativeWebSocket;window.__MIAGENT_COMPOSER_READY__=true;return;
      }
      if(selected&&trigger)composer=true;
      if(!composer)return;
      const model=document.querySelector(${JSON.stringify(modelSelector).replace(/</g, "\\u003c")});
      if(ready(model)){
        chosen=true;model.click();schedule();
        return;
      }
      const mobileModel=document.querySelector('[data-testid="agent-controls-model"]');
      if(ready(mobileModel)&&!expanded){expanded=true;mobileModel.click();return}
      const mobileProvider=document.querySelector('[data-testid="model-provider-opencode"]');
      if(ready(mobileProvider)&&!provider){provider=true;mobileProvider.click();return}
      if(ready(trigger)&&!menu){menu=true;trigger.click()}
    };
    const schedule=()=>{if(!pending){pending=true;requestAnimationFrame(()=>{pending=false;open()})}};
    const observer=new MutationObserver(schedule);
    observer.observe(document.documentElement,{childList:true,subtree:true,attributes:true});
    const NativeWebSocket=window.WebSocket;
    const timer=setInterval(schedule,200);
    setTimeout(()=>{clearInterval(timer);observer.disconnect();window.WebSocket=NativeWebSocket},30000);
    window.WebSocket=class extends NativeWebSocket{
      constructor(...args){super(...args);this.addEventListener("message",event=>{
        if(selected||typeof event.data!=="string")return;
        const hasWorkspace=value=>value===${JSON.stringify(workspace.workspaceId)}||value===${JSON.stringify(`${serverId}:${workspace.workspaceId}`)}||(value&&typeof value==="object"&&Object.values(value).some(hasWorkspace));
        try{if(!hasWorkspace(JSON.parse(event.data)))return}catch{return}
        requestAnimationFrame(()=>requestAnimationFrame(()=>{
          if(selected)return;
          selected=true;
          window.history.pushState(null,"",route);
          window.dispatchEvent(new PopStateEvent("popstate"));
          schedule();
        }));
      })}
    };
  }</script>`;
  const html = await fs.readFile(path.join(sourceUi, "index.html"), "utf8");
  if (!html.includes("</head>")) throw new Error("Paseo index is missing its head tag");
  let introFile;
  for (const candidate of ["01_overview.html"]) {
    if (await fs.access(path.join(cwd, "lab", candidate)).then(() => true, () => false)) {
      introFile = candidate;
      break;
    }
  }
  const preview = introFile ? labPreviewBootstrap(route, `miagent:lab-intro:${serverId}`, introFile) : "";
  const defaults = browserDefaultsBootstrap(process.env.OPENCODE_MODEL ?? "miagent-llm/Qwen/Qwen3.8-27B-FP8");
  await fs.writeFile(path.join(targetUi, "index.html"), html.replace("</head>", defaults + staleRouteBootstrap(serverId) + redirect + preview + "</head>"));
  console.log(`[miagent-paseo] Lab project ready: ${cwd}; workspace=${workspace.workspaceId}`);
  return { project, workspace, serverId, route };
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  await configureWorkspace(process.env.PASEO_HOME, "/workspace",
    "/usr/local/lib/node_modules/@getpaseo/server/dist/server/web-ui",
    process.env.PASEO_WEB_UI_DIST_DIR);
}
