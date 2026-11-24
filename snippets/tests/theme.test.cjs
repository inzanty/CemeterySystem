// Run with: node --test snippets/tests/theme.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('snippets/static/snippets/theme.js', 'utf8');

function page({ stored = null, dark = false, blocked = false, writeBlocked = false, legacy = false } = {}) {
    const windowEvents = {}, documentEvents = {}, buttonEvents = {};
    const button = { hidden: true, dataset: {}, attributes: {},
        setAttribute(name, value) { this.attributes[name] = value; },
        addEventListener: (name, fn) => { buttonEvents[name] = fn; } };
    const root = { dataset: {} };
    const storage = { getItem: () => stored, setItem: (key, value) => {
        if (writeBlocked) throw new Error('quota');
        assert.equal(key, 'memoria-theme'); stored = value;
    } };
    const device = { matches: dark };
    let deviceListener;
    device[legacy ? 'addListener' : 'addEventListener'] = (...args) => { deviceListener = args.at(-1); };
    const window = { matchMedia: () => device, addEventListener: (name, fn) => { windowEvents[name] = fn; } };
    Object.defineProperty(window, 'localStorage', { get() {
        if (blocked) throw new Error('denied');
        return storage;
    } });
    const document = { documentElement: root, getElementById: () => button,
        addEventListener: (name, fn) => { documentEvents[name] = fn; } };
    vm.runInNewContext(source, { window, document });
    return {
        root, button,
        ready: () => documentEvents.DOMContentLoaded(),
        click: () => buttonEvents.click(),
        choose: value => {
            for (let i = 0; i < 3 && button.dataset.preference !== value; i++) buttonEvents.click();
            assert.equal(button.dataset.preference, value);
        },
        device: value => { device.matches = value; deviceListener(); },
        sync: (value, key = 'memoria-theme', storageArea = storage) => windowEvents.storage({ key, newValue: value, storageArea }),
        stored: () => stored,
    };
}

test('system defaults apply before DOM ready; button starts hidden', () => {
    const p = page({ dark: true });
    assert.equal(p.root.dataset.theme, 'dark');
    assert.equal(p.button.hidden, true);
    p.ready();
    assert.equal(p.button.dataset.preference, 'system');
    assert.equal(p.button.hidden, false);
    p.device(false);
    assert.equal(p.root.dataset.theme, 'light');
});

test('all explicit choices persist and survive navigation/reload', () => {
    const p = page(); p.ready();
    for (const value of ['dark', 'light', 'system']) {
        p.choose(value);
        assert.equal(p.stored(), value);
        const next = page({ stored: p.stored(), dark: true }); next.ready();
        assert.equal(next.button.dataset.preference, value);
        assert.equal(next.root.dataset.theme, value === 'system' ? 'dark' : value);
    }
});

test('device changes affect only system preference, including legacy listeners', () => {
    const p = page({ stored: 'light', legacy: true }); p.ready();
    p.device(true); assert.equal(p.root.dataset.theme, 'light');
    p.choose('dark'); p.device(false); assert.equal(p.root.dataset.theme, 'dark');
    p.choose('system'); assert.equal(p.root.dataset.theme, 'light');
    p.device(true); assert.equal(p.root.dataset.theme, 'dark');
});

test('invalid and missing preferences resolve to system', () => {
    for (const stored of [null, '', 'invalid', 'DARK']) {
        const p = page({ stored, dark: true }); p.ready();
        assert.equal(p.button.dataset.preference, 'system');
        assert.equal(p.root.dataset.theme, 'dark');
    }
});

test('cross-tab updates, removal and clear synchronize button and theme', () => {
    const p = page({ stored: 'dark' }); p.ready();
    p.sync('light'); assert.equal(p.root.dataset.theme, 'light'); assert.equal(p.button.dataset.preference, 'light');
    p.sync('dark', 'unrelated'); assert.equal(p.root.dataset.theme, 'light');
    p.sync('dark', 'memoria-theme', {}); assert.equal(p.root.dataset.theme, 'light');
    p.sync('invalid'); assert.equal(p.button.dataset.preference, 'system');
    p.sync('dark'); p.sync(null); assert.equal(p.button.dataset.preference, 'system');
    p.sync('dark'); p.sync(null, null); assert.equal(p.root.dataset.theme, 'light');
});

test('storage getter and write failures leave switching functional', () => {
    for (const options of [{ blocked: true }, { writeBlocked: true }]) {
        const p = page(options); p.ready();
        p.choose('dark'); assert.equal(p.root.dataset.theme, 'dark');
        p.choose('light'); assert.equal(p.root.dataset.theme, 'light');
        p.choose('system'); p.device(true); assert.equal(p.root.dataset.theme, 'dark');
    }
});

test('storage events before DOM ready are reflected at initialization', () => {
    const p = page(); p.sync('dark'); p.ready();
    assert.equal(p.button.dataset.preference, 'dark'); assert.equal(p.root.dataset.theme, 'dark');
});

test('one button cycles system, light, dark with current and next accessible labels', () => {
    const p = page(); p.ready();
    for (const [mode, label] of [
        ['system', 'Motyw: Systemowy. Zmień na Jasny.'],
        ['light', 'Motyw: Jasny. Zmień na Ciemny.'],
        ['dark', 'Motyw: Ciemny. Zmień na Systemowy.'],
        ['system', 'Motyw: Systemowy. Zmień na Jasny.'],
    ]) {
        assert.equal(p.button.dataset.preference, mode);
        assert.equal(p.button.attributes['aria-label'], label);
        assert.equal(p.button.title, label);
        p.click();
    }
});
