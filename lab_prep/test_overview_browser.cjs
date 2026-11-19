const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const url = process.env.PASEO_TEST_URL || 'http://localhost:8088/__overview_test';
    if (!process.env.PASEO_TEST_URL) {
      // Match Paseo's opaque-origin preview sandbox without starting a server.
      await page.route(url, route => route.fulfill({contentType: 'text/html',
        body: '<div data-testid="workspace-file-pane"><iframe sandbox="allow-scripts" style="width:100%;height:950px;border:0"></iframe></div>'}));
    }
    await page.goto(url, {waitUntil: 'domcontentloaded'});
    if (process.env.PASEO_TEST_URL) {
    await page.getByTestId('workspace-explorer-toggle').first().waitFor({timeout: 45000});
    await page.waitForTimeout(1000);
    let files = page.getByText('Files', {exact: true}).filter({visible: true});
    if (!await files.count()) {
      await page.getByTestId('workspace-explorer-toggle').click();
      files = page.getByText('Files', {exact: true}).filter({visible: true});
    }
    await files.first().click();
    await page.locator('[data-testid$="-name"]').filter({visible: true}).first().waitFor();
    const file = page.getByText('01_overview.html', {exact: true}).filter({visible: true});
    if (!await file.isVisible()) {
      await page.locator('[data-testid$="-name"]').filter({hasText: /^lab$/, visible: true}).click();
    }
    await file.click();
    const preview = page.getByTestId('file-mode-preview').filter({visible: true});
    await preview.last().click();
    } else {
      const source = fs.readFileSync(path.join(__dirname, '../MIAgent/lab/01_overview.html'), 'utf8');
      await page.locator('iframe').evaluate((frame, html) => {frame.srcdoc = html;}, source);
    }
    const lesson = page.frameLocator('[data-testid="workspace-file-pane"] iframe').last();
    await lesson.getByRole('heading', {name: '7.2 Explore the available data', exact: true}).waitFor();
    assert.deepEqual(await lesson.locator('table').first().locator('tbody tr td:first-child').allTextContents(),
      ['LLM / model', 'Harness', 'Agent']);
    assert.equal(await lesson.locator('.prompt-block').count(),
      await lesson.locator('pre').count() - await lesson.locator('.answer pre').count());

    await page.context().grantPermissions(['clipboard-read'], {origin: new URL(page.url()).origin});
    const prompt = lesson.locator('.prompt-block').first();
    const expected = (await prompt.locator('code').textContent()).replace(/\n$/, '');
    await prompt.getByRole('button', {name: 'Copy prompt', exact: true}).click();
    await prompt.getByRole('status').filter({hasText: /^Copied$/}).waitFor();
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), expected);

    await lesson.locator('#table-of-contents').getByRole('link', {name: 'Inference', exact: true}).click();
    const dataPrompt = lesson.locator('.prompt-block').filter({hasText: 'What data do you have access to?'});
    await dataPrompt.getByRole('button', {name: 'Copy prompt', exact: true}).click();
    await dataPrompt.getByRole('status').filter({hasText: /^Copied$/}).waitFor();
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), 'What data do you have access to?');

    for (const width of [760, 340]) {
      await lesson.locator('body').evaluate((body, size) => {body.style.width = size + 'px';}, width);
      assert.ok(await lesson.locator('body').evaluate(body => body.scrollWidth <= body.clientWidth));
    }
    console.log('Overview passed: model/harness/agent order, data question, clipboard contents, navigation, and narrow layout.');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
