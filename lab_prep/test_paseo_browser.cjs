// Run against a disposable Paseo instance, never a student's live browser state.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.PASEO_TEST_BROWSER_EXECUTABLE ? {executablePath:process.env.PASEO_TEST_BROWSER_EXECUTABLE} : {}),
  });
  try {
    for (const viewport of [{ width: 1365, height: 900 }, { width: 390, height: 844 }]) {
      const context = await browser.newContext({ viewport,
        ...(process.env.PASEO_TEST_PASSWORD ? {httpCredentials: {
          username: process.env.PASEO_TEST_USERNAME || 'miagent',
          password: process.env.PASEO_TEST_PASSWORD,
        }} : {}),
      });
      try {
        const page = await context.newPage();
        const errors = [];
        const failedRequests = [];
        const connectionErrors = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('requestfailed', request => failedRequests.push({url:request.url(),error:request.failure()?.errorText}));
        page.on('websocket', socket => socket.on('socketerror', error => connectionErrors.push({url:socket.url(),error})));
        page.on('console', message => {if(message.type()==='error')connectionErrors.push(message.text())});
        await page.goto(process.env.PASEO_TEST_URL || 'http://127.0.0.1:17677/', { waitUntil: 'domcontentloaded' });
        try {
          await page.getByTestId('combined-model-selector').filter({ hasText: 'Local Qwen' }).first().waitFor({ state: 'attached', timeout: 15000 });
          await page.getByTestId('workspace-file-pane').locator('iframe').first().waitFor({timeout:30000});
          await page.frameLocator('[data-testid="workspace-file-pane"] iframe').first()
            .getByRole('heading', {name:'MI Agent, Medical Imaging Agent LLMs, Harness, and Agents'}).waitFor({timeout:15000});
        } catch (error) {
          console.error(await page.locator('body').innerText(), errors);
          console.error(await page.evaluate(()=>({url:location.href,hint:window.__PASEO_INITIAL_DAEMON_CONNECTION__})),failedRequests,connectionErrors);
          throw error;
        }
        await page.waitForTimeout(1000);
        assert.match(page.url(), /\/h\/srv_[^/]+\/workspace\/wks_/);
        assert.equal(await page.getByText('Add a project', { exact: true }).count(), 0);
        assert.equal(errors.length, 0, errors.join('\n'));
        await page.screenshot({ path: path.join(process.env.PASEO_SCREENSHOT_DIR || '/tmp', `paseo-${viewport.width}.png`), fullPage: true });
        // Native sheets can retain offscreen DOM nodes. A real pointer click
        // verifies the prompt is unobstructed rather than checking node counts.
        const prompt = page.locator('textarea').filter({visible:true});
        if (await prompt.count()) await prompt.first().click({ timeout: 5000 });
        console.log(`Paseo first-run passed: ${viewport.width}px, MIAgent workspace, lab introduction in Preview mode`);
        if (viewport.width > 600) {
          const chat = page.getByTestId('workspace-pane-main');
          const documents = page.getByTestId('workspace-pane-miagent-documents');
          const explorer = page.getByTestId('workspace-explorer-sidebar');
          const chatBox = await chat.boundingBox();
          const documentBox = await documents.boundingBox();
          const explorerBox = await explorer.boundingBox();
          assert.ok(chatBox && documentBox && explorerBox);
          assert.ok(chatBox.x < documentBox.x && documentBox.x < explorerBox.x,
            'Chat, document tabs, and Files must appear left to right');
          assert.ok(Math.abs(chatBox.y-documentBox.y)<10, 'Chat and documents must share a horizontal split');
          assert.equal(await page.getByTestId('menu-button').getAttribute('aria-label'),'Open menu');
          const chatTab = await chat.getByRole('button',{name:'New Agent',exact:true}).getAttribute('data-testid');
          const fileRows = explorer.locator('[data-testid^="file-explorer-row-"][data-testid$="-name"]');
          await fileRows.filter({hasText:/^opencode\.json$/}).click();
          await documents.getByTestId('workspace-tab-file_opencode.json').waitFor();
          await documents.getByTestId('workspace-tab-file_lab/01_overview.html').waitFor();
          await fileRows.filter({hasText:/^lab$/}).click();
          await fileRows.filter({hasText:/^03_MIAgent_workflow\.html$/}).click();
          await documents.getByTestId('workspace-tab-file_lab/03_MIAgent_workflow.html').waitFor();
          assert.equal(await documents.getByTestId('workspace-tab-file_opencode.json').count(),1);
          assert.equal(await documents.getByTestId('workspace-tab-file_lab/01_overview.html').count(),1);
          assert.equal(await chat.getByTestId(chatTab).count(),1,'File selections must retain the existing chat');
          await page.reload({waitUntil:'domcontentloaded'});
          await documents.getByTestId('workspace-tab-file_lab/03_MIAgent_workflow.html').waitFor();
          await page.waitForFunction(()=>window.__MIAGENT_COMPOSER_READY__===true);
          assert.equal(await documents.getByTestId('workspace-tab-file_opencode.json').count(),1,'Separate file tabs survive reload');
          assert.equal(await page.getByTestId('menu-button').getAttribute('aria-label'),'Open menu');
          await page.screenshot({path:path.join(process.env.PASEO_SCREENSHOT_DIR || '/tmp','paseo-file-tabs.png'),fullPage:true});
          console.log('Paseo file tabs passed: hidden agent list, horizontal layout, retained chat, distinct file tabs, reload');
          await page.getByTestId('menu-button').click();
          await page.getByRole('button', { name: 'New workspace', exact: true }).click();
          await page.waitForURL(/\/new\?/, { timeout: 15000 });
          await page.getByTestId('combined-model-selector').filter({visible:true}).last().click();
          await page.locator('[data-testid="model-row-opencode-miagent-llm/Qwen/Qwen3.8-27B-FP8"]').filter({visible:true}).click();
          await page.getByTestId('combined-model-selector').filter({ hasText: 'Local Qwen',visible:true }).last().waitFor({ timeout: 15000 });
          console.log('Paseo New workspace passed: Local Qwen available without creating an agent');
        }
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
