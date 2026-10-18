const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createApp, formatPhone, HOST } = require('./server');
const TOKEN = 'clave-ficticia-para-pruebas-123456';

async function fixture(t) {
    const calls = [];
    const bot = { state: { status: 'connected', linkedNumber: '59170000000', qr: null },
        async send(...args) { calls.push(args); }, async connect() {}, async logout() {},
        async stop() { calls.push('stop'); this.state.status = 'stopped'; } };
    const server = createApp({ token: TOKEN, bot, onShutdown() { server.close(); } }).listen(0, '127.0.0.1');
    await new Promise(resolve => server.once('listening', resolve));
    t.after(() => new Promise(resolve => { server.closeAllConnections(); server.close(resolve); }));
    return { url: 'http://127.0.0.1:' + server.address().port, calls, bot, server };
}

test('el servicio está limitado a loopback', () => assert.equal(HOST, '127.0.0.1'));
test('sin clave rechaza estado y envío', async t => {
    const f = await fixture(t);
    assert.equal((await fetch(f.url + '/status')).status, 401);
    assert.equal((await fetch(f.url + '/send-text', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone: '71234567', message: 'prueba' }) })).status, 401);
    assert.equal(f.calls.length, 0);
});
test('clave incorrecta no autoriza', async t => {
    const f = await fixture(t);
    assert.equal((await fetch(f.url + '/status', { headers: { 'X-API-Key': 'otra-clave' } })).status, 401);
});
test('petición autorizada usa el número normalizado y un único envío simulado', async t => {
    const f = await fixture(t);
    const response = await fetch(f.url + '/send-text', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-API-Key': TOKEN }, body: JSON.stringify({ phone: '71234567', message: 'mensaje ficticio' }) });
    assert.equal(response.status, 200);
    assert.deepEqual(f.calls, [['59171234567@s.whatsapp.net', { text: 'mensaje ficticio' }]]);
});
test('no modifica conexiones mediante GET', async t => {
    const f = await fixture(t);
    assert.equal((await fetch(f.url + '/reconnect', { headers: { 'X-API-Key': TOKEN } })).status, 404);
});
test('rechaza teléfono inválido y contenido vacío', async t => {
    const f = await fixture(t);
    const response = await fetch(f.url + '/send-text', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-API-Key': TOKEN }, body: JSON.stringify({ phone: '123', message: '' }) });
    assert.equal(response.status, 400);
    assert.equal(f.calls.length, 0);
    assert.throws(() => formatPhone(null));
});

test('apagar requiere POST autenticado y cierra el servicio sin desvincular', async t => {
    const f = await fixture(t);
    assert.equal((await fetch(f.url + '/shutdown', { method: 'POST' })).status, 401);
    assert.equal((await fetch(f.url + '/shutdown', { headers: { 'X-API-Key': TOKEN } })).status, 404);
    let loggedOut = false;
    f.bot.logout = async () => { loggedOut = true; };
    const response = await fetch(f.url + '/shutdown', { method: 'POST', headers: { 'X-API-Key': TOKEN } });
    assert.equal((await response.json()).success, true);
    assert.equal(f.server.listening, false);
    assert.deepEqual(f.calls, ['stop']);
    assert.equal(loggedOut, false);
});
