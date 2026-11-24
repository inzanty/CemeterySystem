const { test } = require('node:test');
const assert = require('node:assert/strict');
const { pointFor, zoomFor } = require('../static/snippets/cemetery_map.js');

test('marker coordinates track a zoomed and scrolled image, not viewport pixels', () => {
    const rect = { left: -100, top: -50, width: 800, height: 400 };
    assert.deepEqual(pointFor(100, 150, rect), { x: 25, y: 50 });
    assert.deepEqual(pointFor(166.666, 83.333, rect), { x: 33.33, y: 33.33 });
});

test('markers clamp to image edges', () => {
    const rect = { left: 10, top: 20, width: 200, height: 100 };
    assert.deepEqual(pointFor(-20, -30, rect), { x: 0, y: 0 });
    assert.deepEqual(pointFor(9999, 9999, rect), { x: 100, y: 100 });
});

test('zoom stays between fit-to-width and 400 percent', () => {
    assert.equal(zoomFor(1, -.5), 1);
    assert.equal(zoomFor(4, .5), 4);
    assert.equal(zoomFor(1, .5), 1.5);
    assert.equal(zoomFor(2, -.5), 1.5);
});

function editorHarness() {
    const fs = require('node:fs');
    const vm = require('node:vm');
    const element = (extra = {}) => ({
        listeners: {}, style: {}, dataset: {},
        addEventListener(name, fn) { this.listeners[name] = fn; },
        setAttribute() {},
        ...extra,
    });
    const x = element({value:'25.00'}), y = element({value:'50.00'});
    const clear = element(), status = element();
    const editor = { querySelector: selector => ({
        '[name="map_x"]': x, '[name="map_y"]': y,
        '[data-position-status]': status, '[data-clear-position]': clear,
    })[selector] };
    const viewport = element({scrollLeft:0, scrollTop:0, clientWidth:200, clientHeight:100,
        setPointerCapture(id) { this.captured = id; }});
    const canvas = element({
        querySelector: selector => selector === 'img' ? {complete:true} : null,
        querySelectorAll: () => [], append() {},
        getBoundingClientRect: () => ({left:10,top:20,width:200,height:100}),
    });
    const minus = element({dataset:{mapZoom:'-0.5'}}), plus = element({dataset:{mapZoom:'0.5'}});
    const reset = element(), scale = element(), toolbar = element();
    const map = element({
        closest: () => editor,
        querySelectorAll: () => [minus, plus],
        querySelector: selector => ({
            '.map-viewport':viewport, '.map-canvas':canvas, '.map-toolbar':toolbar,
            '[data-map-scale]':scale, '[data-map-zoom="-0.5"]':minus,
            '[data-map-zoom="0.5"]':plus, '[data-map-reset]':reset,
        })[selector],
    });
    const document = {querySelectorAll:() => [map], createElement:() => element()};
    vm.runInNewContext(fs.readFileSync('snippets/static/snippets/cemetery_map.js','utf8'), {document});
    const target = {closest:() => null};
    const event = (extra={}) => ({target,pointerType:'mouse',pointerId:1,button:0,
        clientX:100,clientY:80,preventDefault() {},...extra});
    return {viewport, x, y, clear, plus, scale, event};
}

test('dragging pans the map without changing the marker on the resulting click', () => {
    const p = editorHarness();
    p.viewport.listeners.pointerdown(p.event());
    assert.equal(p.viewport.captured, 1);
    p.viewport.listeners.pointermove(p.event({clientX:50,clientY:60,buttons:0}));
    assert.equal(p.viewport.scrollLeft, 50);
    assert.equal(p.viewport.scrollTop, 20);
    p.viewport.listeners.pointerup(p.event({clientX:50,clientY:60}));
    p.viewport.listeners.click(p.event({clientX:50,clientY:60}));
    assert.equal(p.x.value,'25.00');
    assert.equal(p.y.value,'50.00');
});

test('a click places the marker, clear resets it, and zoom updates its indicator', () => {
    const p = editorHarness();
    p.viewport.listeners.pointerdown(p.event({clientX:60,clientY:45}));
    p.viewport.listeners.pointerup(p.event({clientX:60,clientY:45}));
    p.viewport.listeners.click(p.event({clientX:60,clientY:45}));
    assert.equal(p.x.value,'25.00');
    assert.equal(p.y.value,'25.00');
    p.plus.listeners.click();
    assert.equal(p.scale.textContent, '150%');
    p.clear.listeners.click();
    assert.equal(p.x.value,'');
    assert.equal(p.y.value,'');
});
