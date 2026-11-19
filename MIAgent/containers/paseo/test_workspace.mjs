import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { configureWorkspace, labPreviewBootstrap, staleRouteBootstrap } from "./configure_workspace.mjs";

const root = await fs.mkdtemp(path.join(os.tmpdir(), "miagent-paseo-test-"));
try {
  const home = path.join(root, "home");
  const cwd = path.join(root, "workspace");
  const ui = path.join(root, "ui");
  await fs.mkdir(cwd);
  await fs.writeFile(path.join(cwd, "opencode.json"), "{}");
  await fs.mkdir(path.join(cwd, "lab"));
  await fs.writeFile(path.join(cwd, "lab/01_overview.html"), "<!doctype html><h1>MIAgent</h1>\n");
  const source = "/usr/local/lib/node_modules/@getpaseo/server/dist/server/web-ui";
  const first = await configureWorkspace(home, cwd, source, ui);
  const second = await configureWorkspace(home, cwd, source, ui);
  assert.equal(first.workspace.workspaceId, second.workspace.workspaceId);
  assert.equal(first.serverId, second.serverId);
  const projectsPath = path.join(home, "projects/projects.json");
  const workspacesPath = path.join(home, "projects/workspaces.json");
  const projects = JSON.parse(await fs.readFile(projectsPath));
  const workspaces = JSON.parse(await fs.readFile(workspacesPath));
  assert.equal(projects.length, 1);
  assert.equal(workspaces.length, 1);
  assert.equal(workspaces[0].cwd, cwd);
  assert.equal(projects[0].displayName, "MIAgent");
  assert.equal(workspaces[0].kind, "directory");
  const extra = { ...projects[0], projectId: "prj_other", rootPath: "/another", displayName: "Other" };
  await fs.writeFile(projectsPath, JSON.stringify([...projects, extra]));
  await configureWorkspace(home, cwd, source, ui);
  assert.equal(JSON.parse(await fs.readFile(projectsPath)).length, 2);
  const html = await fs.readFile(path.join(ui, "index.html"), "utf8");
  assert.ok(html.includes(`sidebar-workspace-row-${first.serverId}:${first.workspace.workspaceId}`));
  assert.ok(html.includes('window.location.pathname==="/"'));
  assert.ok(html.includes('file-mode-preview'));
  assert.ok(html.includes('miagent:lab-intro:'));
  assert.ok(html.includes('01_overview.html'));
  assert.ok(!html.includes('01_agents_harness_and_lab_architecture.md'));
  const previewScript = labPreviewBootstrap(first.route, "test-key");
  new Function(previewScript.slice("<script>".length, -"</script>".length));
  const recoveryScript = staleRouteBootstrap(first.serverId);
  const recover = new Function("window", recoveryScript.slice("<script>".length, -"</script>".length));
  for (const pathname of ["/h/srv_obsolete/workspace/wks_old", "/h/srv_obsolete/agent/old"]) {
    let target;
    recover({ location: { pathname }, history: { replaceState(_state, _title, url) { target = url; } } });
    assert.equal(target, "/?paseo=1");
  }
  for (const pathname of [first.route, `/h/${first.serverId}/workspace/wks_other`, "/", "/settings"]) {
    recover({ location: { pathname }, history: { replaceState() { assert.fail("Valid routes must survive"); } } });
  }
  const local = { id: "direct:lab.example:443", type: "directTcp", endpoint: "lab.example:443" };
  const other = { id: "direct:other.example:443", type: "directTcp", endpoint: "other.example:443" };
  let registry = JSON.stringify([
    { serverId: "srv_old", connections: [local] },
    { serverId: "srv_other", connections: [other] },
    { serverId: first.serverId, connections: [local] },
    { serverId: "srv_multiple", connections: [local, other] },
  ]);
  recover({ location: { pathname: "/", href: "https://lab.example/" },
    localStorage: { getItem() { return registry; }, setItem(key, value) {
      assert.equal(key, "@paseo:daemon-registry"); registry = value;
    } }, history: { replaceState() { assert.fail("Keep root route"); } } });
  const retained = JSON.parse(registry);
  assert.deepEqual(retained.map(host => host.serverId), ["srv_other", first.serverId, "srv_multiple"]);
  assert.deepEqual(retained[2].connections, [other]);
  await fs.rm(path.join(cwd, "lab"), { recursive: true });
  await configureWorkspace(home, cwd, source, ui);
  assert.ok(!(await fs.readFile(path.join(ui, "index.html"), "utf8")).includes('miagent:lab-intro:'));
  assert.ok((await fs.lstat(path.join(ui, "_expo"))).isSymbolicLink());
  await assert.rejects(configureWorkspace(home, path.join(root, "missing"), source, ui));
  console.log("Workspace seed tests passed: valid records, stable IDs, preserved projects, route and assets.");
} finally {
  await fs.rm(root, { recursive: true, force: true });
}
