const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const { proto } = require('@whiskeysockets/baileys');
const { createMessageStore } = require('./message_store');
const { createDriver } = require('./server');

function fixture(t, options = {}) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'casaempeno-wa-test-'));
    t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
    const filename = path.join(directory, 'sent_messages.json');
    const errors = [];
    const config = { filename, proto, onError: error => errors.push(error), ...options };
    return { directory, filename, errors, config, store: createMessageStore(config) };
}

function outgoing(id, message = { conversation: 'Texto ficticio' }) {
    return { key: { id, fromMe: true, remoteJid: '59170000000@s.whatsapp.net' }, message };
}

test('conserva texto e imagen cifrada para recuperación después de reiniciar', t => {
    const f = fixture(t);
    f.store.remember(outgoing('text-1'));
    const image = { imageMessage: { caption: 'Recibo ficticio', mimetype: 'image/png',
        mediaKey: Buffer.from([1, 2, 3]), fileSha256: Buffer.from([4, 5, 6]),
        directPath: '/ruta-ficticia', fileLength: 100, jpegThumbnail: Buffer.from([7, 8]) } };
    f.store.remember(outgoing('image-1', image));
    const restored = createMessageStore(f.config);
    assert.equal(restored.get({ id: 'text-1' }).conversation, 'Texto ficticio');
    assert.deepEqual(proto.Message.toObject(restored.get({ id: 'image-1' })), proto.Message.toObject(proto.Message.fromObject(image)));
    assert.deepEqual(f.errors, []);
});

test('un mensaje desconocido no se reemplaza por otro comprobante', t => {
    const f = fixture(t);
    f.store.remember(outgoing('known'));
    assert.equal(f.store.get({ id: 'missing' }), undefined);
    assert.equal(f.store.get({}), undefined);
    assert.equal(f.store.get(null), undefined);
});

test('limita la cantidad y caduca mensajes sin renovar su antigüedad', t => {
    let time = 1000;
    const f = fixture(t, { maxEntries: 2, ttlMs: 100, now: () => time });
    for (const id of ['one', 'two', 'three']) f.store.remember(outgoing(id));
    assert.equal(f.store.get({ id: 'one' }), undefined);
    assert.equal(f.store.get({ id: 'two' }).conversation, 'Texto ficticio');
    time = 1050;
    f.store.remember(outgoing('two'));
    time = 1101;
    assert.equal(f.store.get({ id: 'two' }), undefined);
    assert.equal(createMessageStore(f.config).get({ id: 'three' }), undefined);
});

test('los mensajes recibidos no sustituyen las copias salientes', t => {
    const f = fixture(t);
    f.store.remember(outgoing('own'));
    f.store.remember({ key: { id: 'own', fromMe: false }, message: { conversation: 'Recibido' } });
    assert.equal(f.store.get({ id: 'own' }).conversation, 'Texto ficticio');
});

test('un fallo de disco conserva el mensaje en memoria sin declarar fallido el envío', t => {
    const f = fixture(t);
    fs.writeFileSync(path.join(f.directory, 'blocked'), 'archivo');
    const store = createMessageStore({ ...f.config, filename: path.join(f.directory, 'blocked', 'cache.json') });
    assert.doesNotThrow(() => store.remember(outgoing('sent')));
    assert.equal(store.get({ id: 'sent' }).conversation, 'Texto ficticio');
    assert.ok(f.errors.length > 0);
});

test('una caché dañada no impide abrir la sesión ni modifica credenciales', t => {
    const f = fixture(t);
    const credentials = path.join(f.directory, 'creds.json');
    fs.writeFileSync(credentials, 'credenciales-ficticias');
    fs.writeFileSync(f.filename, '{incompleto');
    const restored = createMessageStore(f.config);
    assert.equal(restored.get({ id: 'missing' }), undefined);
    restored.remember(outgoing('new'));
    assert.equal(fs.readFileSync(credentials, 'utf8'), 'credenciales-ficticias');
    assert.equal(JSON.parse(fs.readFileSync(f.filename)).messages.length, 1);
    assert.equal(f.errors.length, 1);
});

test('el socket recupera el mismo comprobante tras reconectar y tras reiniciar el bot', async t => {
    const f = fixture(t);
    const sockets = [];
    const sent = [];
    const baileys = {
        proto,
        DisconnectReason: { loggedOut: 401 },
        useMultiFileAuthState: async () => ({ state: {}, saveCreds: async () => {} }),
        fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
        default(config) {
            const socket = { config, ev: new EventEmitter(), user: { id: '59170000000:1@s.whatsapp.net' },
                end() {},
                async sendMessage(jid, message) {
                    sent.push({ jid, message });
                    return outgoing('receipt-1', { imageMessage: { caption: 'Recibo ficticio', mediaKey: Buffer.from([1, 2, 3]) } });
                } };
            sockets.push(socket);
            return socket;
        },
    };
    const options = { loadBaileys: () => baileys, authDir: f.directory };
    const driver = createDriver(options);
    await driver.connect();
    sockets[0].ev.emit('connection.update', { connection: 'open' });
    await driver.send('59170000000@s.whatsapp.net', { image: Buffer.from('ficticia') });
    const key = { id: 'receipt-1', remoteJid: '12345@lid' };
    assert.equal((await sockets[0].config.getMessage(key)).imageMessage.caption, 'Recibo ficticio');
    await driver.connect(true);
    assert.equal((await sockets[1].config.getMessage(key)).imageMessage.caption, 'Recibo ficticio');
    const restarted = createDriver(options);
    await restarted.connect();
    assert.equal((await sockets[2].config.getMessage(key)).imageMessage.caption, 'Recibo ficticio');
    assert.equal(await sockets[2].config.getMessage({ id: 'unknown' }), undefined);
    assert.equal(sent.length, 1);
});
