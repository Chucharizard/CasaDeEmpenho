/** API local autenticada para el envío de comprobantes mediante Baileys. */
const express = require('express');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');
const { createMessageStore } = require('./message_store');
const PORT = 3001;
const HOST = '127.0.0.1';
if (require.main === module) {
    const envPath = path.join(__dirname, '..', '.env');
    if (fs.existsSync(envPath)) process.loadEnvFile(envPath);
}
const AUTH_DIR = process.env.CASAEMPENO_DATA_DIR ? path.join(process.env.CASAEMPENO_DATA_DIR, 'whatsapp-auth') : path.join(__dirname, 'auth_session');

function loadToken() {
    if (process.env.WHATSAPP_API_TOKEN?.trim()) return process.env.WHATSAPP_API_TOKEN.trim();
    const tokenPath = process.env.WHATSAPP_TOKEN_PATH || path.join(process.env.CASAEMPENO_DATA_DIR || path.join(__dirname, '..'), '.whatsapp_api_token');
    try { return fs.readFileSync(tokenPath, 'utf8').trim(); }
    catch (error) {
        if (error.code !== 'ENOENT') throw error;
        const token = crypto.randomBytes(32).toString('base64url');
        try { fs.writeFileSync(tokenPath, token, { flag: 'wx', mode: 0o600 }); return token; }
        catch (writeError) {
            if (writeError.code === 'EEXIST') return fs.readFileSync(tokenPath, 'utf8').trim();
            throw writeError;
        }
    }
}

function formatPhone(phone) {
    if (typeof phone !== 'string') throw new Error('Número de teléfono no válido.');
    let digits = phone.replace(/\D/g, '');
    if (/^[67]\d{7}$/.test(digits)) digits = '591' + digits;
    if (!/^\d{8,15}$/.test(digits)) throw new Error('Número de teléfono no válido.');
    return digits + '@s.whatsapp.net';
}

function createDriver({ loadBaileys = () => require('@whiskeysockets/baileys'), authDir = AUTH_DIR } = {}) {
    let socket = null, connecting = null, timer = null, generation = 0, attempts = 0;
    let stopped = false;
    const credentialWrites = new Set();
    let messageStore = null;
    const state = { status: 'disconnected', linkedNumber: null, qr: null, error: null };
    function retry() {
        if (stopped || timer || attempts >= 5) return;
        attempts++;
        timer = setTimeout(() => { timer = null; connect().catch(() => {}); }, Math.min(attempts * 3000, 20000));
        timer.unref();
    }
    async function connect(force = false) {
        if (connecting) return connecting;
        if (!force && state.status === 'connected') return;
        stopped = false;
        clearTimeout(timer); timer = null;
        const run = async () => {
            const current = ++generation;
            if (socket) socket.end(new Error('Reconexión local'));
            socket = null;
            state.status = 'connecting'; state.qr = null; state.linkedNumber = null;
            const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, proto } = loadBaileys();
            const { state: auth, saveCreds } = await useMultiFileAuthState(authDir);
            if (!messageStore) messageStore = createMessageStore({ filename: path.join(authDir, 'sent_messages.json'), proto });
            const { version } = await fetchLatestBaileysVersion();
            if (current !== generation) return;
            const next = makeWASocket({ version, auth, logger: require('pino')({ level: 'silent' }),
                printQRInTerminal: false, browser: ['Casa de Empeño', 'Chrome', '10.0'], markOnlineOnConnect: false,
                getMessage: async key => messageStore.get(key) });
            socket = next;
            next.ev.on('messages.upsert', ({ messages }) => {
                if (current === generation) for (const message of messages) messageStore.remember(message);
            });
            next.ev.on('creds.update', () => {
                if (current === generation) {
                    const write = saveCreds().catch(error => console.error('No se guardaron las credenciales:', error.message));
                    credentialWrites.add(write);
                    write.finally(() => credentialWrites.delete(write));
                }
            });
            next.ev.on('connection.update', async update => {
                if (current !== generation) return;
                if (update.qr) { state.qr = update.qr; state.status = 'qr_pending'; }
                if (update.connection === 'open') {
                    attempts = 0; state.status = 'connected'; state.qr = null; state.error = null;
                    state.linkedNumber = next.user?.id?.split(':')[0]?.split('@')[0] || null;
                }
                if (update.connection === 'close') {
                    state.status = 'disconnected'; state.qr = null; state.linkedNumber = null; socket = null;
                    const code = update.lastDisconnect?.error?.output?.statusCode;
                    if (code === DisconnectReason.loggedOut) {
                        messageStore.clear();
                        try { fs.rmSync(authDir, { recursive: true, force: true }); }
                        catch (error) { state.error = error.message; }
                        attempts = 0;
                    }
                    retry();
                }
            });
        };
        connecting = run().catch(error => {
            if (!stopped) {
                state.status = 'disconnected'; state.error = error.message; retry();
                console.error('[WhatsApp] No se pudo conectar:', error.message);
            }
            throw error;
        }).finally(() => { connecting = null; });
        return connecting;
    }
    return {
        state,
        connect,
        async stop() {
            stopped = true;
            ++generation; clearTimeout(timer); timer = null; attempts = 0;
            const previous = socket; socket = null;
            state.status = 'stopped'; state.qr = null; state.linkedNumber = null;
            if (previous) previous.end(new Error('Bot apagado desde Configuración'));
            await Promise.allSettled([...credentialWrites]);
        },
        async send(jid, message) {
            if (state.status !== 'connected' || !socket) throw new Error('WhatsApp no está conectado.');
            const sent = await socket.sendMessage(jid, message);
            messageStore.remember(sent);
        },
        async logout() {
            ++generation; clearTimeout(timer); timer = null; attempts = 0;
            const previous = socket; socket = null;
            state.status = 'disconnected'; state.qr = null; state.linkedNumber = null;
            try { if (previous) await previous.logout(); }
            finally {
                if (previous) previous.end(new Error('Sesión cerrada localmente'));
                messageStore?.clear();
                fs.rmSync(authDir, { recursive: true, force: true });
            }
        },
    };
}

function createApp({ token, bot, onShutdown = () => {} }) {
    if (!token || token.length < 16) throw new Error('Se requiere una clave local de API de al menos 16 caracteres.');
    const app = express();
    let shuttingDown = false;
    app.disable('x-powered-by');
    app.use((req, res, next) => {
        const supplied = Buffer.from(req.get('X-API-Key') || '');
        const expected = Buffer.from(token);
        if (supplied.length !== expected.length || !crypto.timingSafeEqual(supplied, expected)) {
            return res.status(401).json({ success: false, error: 'Acceso no autorizado.' });
        }
        if (shuttingDown && !['/status', '/shutdown'].includes(req.path)) {
            return res.status(503).json({ success: false, error: 'El bot está apagándose.' });
        }
        next();
    });
    app.use(express.json({ limit: '10mb' }));
    app.get('/status', (req, res) => res.json({ status: bot.state.status, linkedNumber: bot.state.linkedNumber, hasQR: !!bot.state.qr }));
    app.post('/reconnect', (req, res) => {
        bot.connect(true).catch(() => {});
        res.json({ success: true, message: 'Reconexión iniciada.' });
    });
    app.get('/qr-data', async (req, res) => {
        if (!bot.state.qr) return res.status(404).json({ status: bot.state.status, error: 'No hay QR disponible.' });
        try { res.json({ qr: await QRCode.toDataURL(bot.state.qr, { width: 300, margin: 2 }), status: bot.state.status }); }
        catch { res.status(500).json({ error: 'No se pudo generar el QR.' }); }
    });
    app.get('/qr', async (req, res) => {
        if (!bot.state.qr) return res.status(404).json({ error: 'No hay QR disponible.' });
        try { res.type('png').send(await QRCode.toBuffer(bot.state.qr)); }
        catch { res.status(500).json({ error: 'No se pudo generar el QR.' }); }
    });
    for (const kind of ['text', 'image']) {
        app.post('/send-' + kind, async (req, res) => {
            if (bot.state.status !== 'connected') return res.status(503).json({ success: false, error: 'WhatsApp no está conectado.' });
            let jid, message;
            try {
                jid = formatPhone(req.body.phone);
                if (kind === 'text') {
                    if (typeof req.body.message !== 'string' || !req.body.message.trim() || req.body.message.length > 10000) throw new Error('Mensaje no válido.');
                    message = { text: req.body.message };
                } else {
                    const encoded = req.body.imageBase64;
                    if (typeof encoded !== 'string' || !encoded.length || !/^[A-Za-z0-9+/]+={0,2}$/.test(encoded)) throw new Error('Imagen no válida.');
                    const buffer = Buffer.from(encoded, 'base64');
                    if (!buffer.length || buffer.length > 7 * 1024 * 1024) throw new Error('Tamaño de imagen no válido.');
                    message = { image: buffer, caption: String(req.body.caption || 'Comprobante de Pago - Casa de Empeño'), mimetype: 'image/png' };
                }
            } catch (error) { return res.status(400).json({ success: false, error: error.message }); }
            try { await bot.send(jid, message); res.json({ success: true, message: 'Mensaje enviado.' }); }
            catch (error) { res.status(502).json({ success: false, error: error.message }); }
        });
    }
    app.post('/logout', async (req, res) => {
        try { await bot.logout(); res.json({ success: true, message: 'Sesión cerrada.' }); }
        catch (error) { res.status(500).json({ success: false, error: error.message }); }
    });
    app.post('/shutdown', async (req, res) => {
        if (shuttingDown) return res.json({ success: true, message: 'El bot está apagándose.' });
        shuttingDown = true;
        try {
            await bot.stop();
            res.once('finish', onShutdown);
            res.json({ success: true, message: 'Bot apagado; la sesión se conserva.' });
        } catch (error) {
            shuttingDown = false;
            res.status(500).json({ success: false, error: error.message });
        }
    });
    return app;
}

if (require.main === module) {
    const bot = createDriver();
    const server = createApp({ token: loadToken(), bot, onShutdown() {
        server.close(() => process.exit(0));
        setTimeout(() => process.exit(0), 2000).unref();
    } }).listen(PORT, HOST, () => {
        console.log('[WhatsApp] Servicio local en http://' + HOST + ':' + PORT);
        bot.connect().catch(() => {});
    });
}
module.exports = { createApp, createDriver, formatPhone, loadToken, HOST };
