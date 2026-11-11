const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const chatScript = fs.readFileSync(
  path.join(__dirname, '..', '..', 'docs', 'chat.js'),
  'utf8',
);

class FakeElement {
  constructor(tag = 'div') {
    this.tag = tag;
    this.children = [];
    this.handlers = {};
    this.dataset = {};
    this.attributes = {};
    this.disabled = false;
    this.value = '';
    this.className = '';
    this._textContent = '';
    this.parentNode = null;
    this.scrollHeight = 100;
    this.scrollTop = 0;
  }

  get textContent() {
    return this._textContent + this.children.map((child) => child.textContent || '').join('');
  }

  set textContent(value) {
    this.children.forEach((child) => { child.parentNode = null; });
    this.children = [];
    this._textContent = String(value);
  }

  addEventListener(name, callback) { this.handlers[name] = callback; }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  append(...items) {
    items.forEach((item) => {
      const child = typeof item === 'string' ? { textContent: item, parentNode: null } : item;
      this.appendChild(child);
    });
  }

  replaceChildren(...items) {
    this.children.forEach((child) => { child.parentNode = null; });
    this.children = [];
    items.forEach((item) => this.appendChild(item));
  }

  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { this.focused = true; }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    this.parentNode = null;
  }
}

function createChat({ fetchImpl, apiBaseUrl = 'https://policy-api.example.test' } = {}) {
  const chatBody = new FakeElement();
  const input = new FakeElement('input');
  const form = new FakeElement('form');
  const sendButton = new FakeElement('button');
  const resetButton = new FakeElement('button');
  const suggestionButtons = [
    'How many PTO days can I take?',
    'What are the attendance rules?',
    'What employee benefits are available?',
    'What is the parental leave policy?',
  ].map((question) => {
    const button = new FakeElement('button');
    button.dataset.question = question;
    return button;
  });
  const elements = {
    chatBody,
    questionInput: input,
    chatForm: form,
    sendButton,
    resetButton,
  };
  const document = {
    getElementById(id) { return elements[id]; },
    querySelectorAll(selector) { return selector === '.suggestion' ? suggestionButtons : []; },
    createElement(tag) { return new FakeElement(tag); },
  };
  const window = {
    document,
    fetch: fetchImpl,
    PEOPLEDESK_CONFIG: { apiBaseUrl },
  };

  vm.runInNewContext(chatScript, { window });
  return { chatBody, input, form, sendButton, resetButton, suggestionButtons };
}

function event() {
  return { prevented: false, preventDefault() { this.prevented = true; } };
}

function flattenedText(element) {
  return element.textContent || '';
}

test('typed send calls the API, shows loading, and renders answer citations', async () => {
  let resolveFetch;
  let requestUrl;
  let requestOptions;
  const ui = createChat({
    fetchImpl(url, options) {
      requestUrl = url;
      requestOptions = options;
      return new Promise((resolve) => { resolveFetch = resolve; });
    },
  });
  ui.input.value = 'How many PTO days can I take?';

  const submitEvent = event();
  const pending = ui.form.handlers.submit(submitEvent);

  assert.equal(submitEvent.prevented, true);
  assert.equal(requestUrl, 'https://policy-api.example.test/api/chat');
  assert.deepEqual(JSON.parse(requestOptions.body), { question: 'How many PTO days can I take?' });
  assert.equal(ui.sendButton.disabled, true);
  assert.equal(ui.input.disabled, true);
  assert.match(flattenedText(ui.chatBody), /Searching the available HR policies/);

  resolveFetch({
    ok: true,
    async json() {
      return {
        answer: 'Employees accrue PTO according to completed service.',
        abstained: false,
        status: 'generated',
        citations: [{
          document: 'leave_policy.md',
          document_id: 'doc_leave_sample',
          section: '2.1 Accrual Rates',
          chunk_id: 'chk_leave_001',
          quote: 'Full-time regular employees accrue PTO based on completed years of service.',
          page_number: null,
        }],
      };
    },
  });
  await pending;

  const output = flattenedText(ui.chatBody);
  assert.match(output, /How many PTO days can I take\?/);
  assert.match(output, /Employees accrue PTO according to completed service/);
  assert.match(output, /leave_policy\.md/);
  assert.match(output, /2\.1 Accrual Rates/);
  assert.match(output, /chk_leave_001/);
  assert.match(output, /Full-time regular employees accrue PTO/);
  assert.doesNotMatch(output, /Searching the available HR policies/);
  assert.equal(ui.sendButton.disabled, false);
  assert.equal(ui.input.disabled, false);
});

test('suggested questions use the same backend request flow', async () => {
  let requestBody;
  const ui = createChat({
    fetchImpl: async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return { ok: true, async json() { return { answer: 'Policy answer', citations: [] }; } };
    },
  });

  await ui.suggestionButtons[1].handlers.click();

  assert.deepEqual(requestBody, { question: 'What are the attendance rules?' });
  assert.match(flattenedText(ui.chatBody), /Policy answer/);
});

test('backend configuration errors are displayed without hiding the server message', async () => {
  const ui = createChat({
    fetchImpl: async () => ({
      ok: false,
      status: 503,
      async json() {
        return {
          answer: 'Live answer generation is not configured. Set OPENAI_API_KEY.',
          citations: [],
          abstained: true,
          status: 'not_configured',
          error: 'live_generation_not_configured',
        };
      },
    }),
  });
  ui.input.value = 'How much PTO can I take?';

  await ui.form.handlers.submit(event());

  assert.match(flattenedText(ui.chatBody), /Live answer generation is not configured/);
  assert.equal(ui.sendButton.disabled, false);
});

test('network failures produce a useful message and release busy controls', async () => {
  const ui = createChat({ fetchImpl: async () => { throw new Error('network down'); } });
  ui.input.value = 'What benefits are available?';

  await ui.form.handlers.submit(event());

  assert.match(flattenedText(ui.chatBody), /couldn't reach the policy service/);
  assert.equal(ui.sendButton.disabled, false);
  assert.equal(ui.resetButton.disabled, false);
});

test('empty input is rejected before a request is sent', async () => {
  let calls = 0;
  const ui = createChat({ fetchImpl: async () => { calls += 1; } });
  ui.input.value = '   ';

  await ui.form.handlers.submit(event());

  assert.equal(calls, 0);
  assert.match(flattenedText(ui.chatBody), /Please enter a question about an HR policy/);
});

test('missing frontend URL is reported and does not make a request', async () => {
  let calls = 0;
  const ui = createChat({ apiBaseUrl: '', fetchImpl: async () => { calls += 1; } });
  ui.input.value = 'How many PTO days can I take?';

  await ui.form.handlers.submit(event());

  assert.equal(calls, 0);
  assert.match(flattenedText(ui.chatBody), /backend URL is not configured/);
});

test('new chat clears the conversation and restores the welcome message', () => {
  const ui = createChat({ fetchImpl: async () => { throw new Error('not used'); } });
  ui.input.value = 'old text';
  ui.chatBody.appendChild(new FakeElement('div'));

  ui.resetButton.handlers.click();

  assert.equal(ui.chatBody.children.length, 1);
  assert.match(flattenedText(ui.chatBody), /Hi! How can I help you with your HR policies today/);
  assert.equal(ui.input.value, '');
  assert.equal(ui.input.focused, true);
});
