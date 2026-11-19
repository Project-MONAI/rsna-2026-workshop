const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../MIAgent/containers/paseo/configure_workspace.mjs'), 'utf8');
function exportedFunction(name, next) {
  const section = source.slice(source.indexOf(`export function ${name}`), source.indexOf(next));
  return new Function(section.replace('export ', '') + `;return ${name};`)();
}
const defaults = exportedFunction('browserDefaultsBootstrap', 'export function staleRouteBootstrap');
const preview = exportedFunction('labPreviewBootstrap', 'export async function configureWorkspace');
const script = html => html.slice('<script>'.length, -'</script>'.length);
const storage = entries => {
  const data = new Map(Object.entries(entries || {}));
  return {getItem:key=>data.get(key)??null, setItem:(key,value)=>data.set(key,value)};
};

const localStorage = storage({
  '@paseo:app-settings': JSON.stringify({theme:'dark',sendBehavior:'steer'}),
  '@paseo:create-agent-preferences': JSON.stringify({providerPreferences:{opencode:{featureValues:{custom:true,auto_accept:false}},claude:{model:'other'}}}),
  'panel-state': JSON.stringify({version:16,state:{sidebarWidth:400,desktop:{agentListOpen:true,focusModeEnabled:false}}}),
});
const context = {window:{localStorage},console};
vm.runInNewContext(script(defaults('local-qwen')), context);
const read = key => JSON.parse(localStorage.getItem(key));
assert.deepEqual(read('@paseo:app-settings'), {theme:'dark',sendBehavior:'queue'});
assert.deepEqual(read('@paseo:create-agent-preferences').providerPreferences.opencode.featureValues, {custom:true,auto_accept:true});
assert.equal(read('@paseo:create-agent-preferences').providerPreferences.claude.model, 'other');
assert.equal(read('panel-state').state.desktop.agentListOpen, false);
assert.equal(read('panel-state').state.sidebarWidth, 400);
localStorage.setItem('@paseo:app-settings', JSON.stringify({sendBehavior:'interrupt'}));
localStorage.setItem('panel-state', JSON.stringify({version:16,state:{sidebarWidth:400,desktop:{agentListOpen:true,focusModeEnabled:true}}}));
vm.runInNewContext(script(defaults('local-qwen')), context);
assert.equal(read('@paseo:app-settings').sendBehavior, 'interrupt', 'Later student choices survive');
assert.equal(read('panel-state').state.desktop.agentListOpen, false, 'Returning browsers also start with the left sidebar hidden');
assert.equal(read('panel-state').state.desktop.focusModeEnabled, true, 'Other panel settings survive');
assert.equal(read('panel-state').state.sidebarWidth, 400);
vm.runInNewContext(script(defaults('local-qwen')), {window:{localStorage:storage()},console});

const route = '/h/srv_lab/workspace/wks_initial';
function previewFixture(pathname, ready=true) {
  const frames = [];
  let mutation, documentOpen=false, previewOpen=false, clicks=0;
  const store = storage();
  const changed = () => mutation();
  const element = values => ({getClientRects:()=>[{}],...values});
  const elements = () => [
    element({dataset:{testid:'workspace-tab-file_lab/01.md'},click(){clicks++;documentOpen=true;changed();}}),
    ...(documentOpen ? [element({dataset:{testid:'workspace-file-pane'},querySelector:selector=>selector==='iframe'&&previewOpen?{}:null}),
      element({dataset:{testid:'file-mode-preview'},click(){previewOpen=true;changed();}})] : []),
  ];
  const window = {location:{pathname},__MIAGENT_COMPOSER_READY__:ready,addEventListener(){}};
  vm.runInNewContext(script(preview(route,'miagent:lab-intro:srv_lab','01.md')), {
    window,localStorage:store,Date,
    document:{documentElement:{},querySelectorAll:()=>elements()},
    MutationObserver:class {constructor(callback){mutation=callback;}observe(){}},
    requestAnimationFrame:callback=>frames.push(callback),
  });
  const flush = () => {for(let n=0;frames.length&&n<30;n++)frames.shift()();assert.equal(frames.length,0);};
  flush();
  return {store,window,flush,get clicks(){return clicks;},navigate(next){window.location.pathname=next;documentOpen=false;previewOpen=false;changed();flush();}};
}
const first = previewFixture(route);
assert.equal(first.clicks, 1);
assert.equal(first.store.getItem('miagent:lab-intro:srv_lab:wks_initial'), 'seen');
first.navigate('/h/srv_lab/workspace/wks_new');
assert.equal(first.clicks, 2, 'A new workspace opens the same introduction');
first.navigate(route);
assert.equal(first.clicks, 2, 'Returning does not replace the selected chat');
first.navigate('/h/srv_other/workspace/wks_other');
assert.equal(first.clicks, 2, 'Other hosts are untouched');
assert.equal(previewFixture('/h/srv_lab/workspace/wks_direct',false).clicks, 1, 'Direct links to a new workspace work');
console.log('Paseo startup defaults passed: auto-accept, Queue, hidden sidebar, preserved preferences, per-workspace preview.');
