/**
 * WhatsApp Bot Server - Casa de Empeño
 * =====================================
 * Servicio local que se conecta a WhatsApp usando Baileys y expone
 * un API REST para que Flask envíe imágenes de recibos automáticamente.
 *
 * Endpoints:
 *   GET  /status       → Estado de conexión y número vinculado
 *   GET  /qr           → Código QR actual como imagen PNG (para escanearlo)
 *   GET  /qr-data      → Código QR como string Base64 (para incrustar en HTML)
 *   POST /send-image    → Enviar imagen a un número de WhatsApp
 *   POST /send-text     → Enviar texto a un número de WhatsApp
 *   POST /logout        → Cerrar sesión de WhatsApp
 */

const express = require('express');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const QRCode = require('qrcode');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(express.json({ limit: '10mb' }));

const PORT = 3001;
const AUTH_DIR = path.join(__dirname, 'auth_session');

// ── Estado Global ──────────────────────────────────────────────────────────
let sock = null;
let currentQR = null;
let connectionStatus = 'disconnected'; // disconnected | qr_pending | connected
let linkedNumber = null;
let reconnectAttempts = 0;
const MAX_RECONNECT = 5;

// ── Logger Silencioso (para no llenar la consola) ──────────────────────────
const logger = pino({ level: 'silent' });

// ── Conectar a WhatsApp ────────────────────────────────────────────────────
async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        version,
        auth: state,
        logger,
        printQRInTerminal: false,
        browser: ['Casa de Empeño', 'Chrome', '10.0'],
        markOnlineOnConnect: false,
    });

    // Guardar credenciales cada vez que se actualicen
    sock.ev.on('creds.update', saveCreds);

    // Manejar actualizaciones de conexión
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            currentQR = qr;
            connectionStatus = 'qr_pending';
            console.log('[WhatsApp Bot] 📱 Código QR generado. Escanéalo desde la página de administración.');
        }

        if (connection === 'close') {
            currentQR = null;
            connectionStatus = 'disconnected';
            linkedNumber = null;

            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

            if (statusCode === DisconnectReason.loggedOut) {
                console.log('[WhatsApp Bot] 🔴 Sesión cerrada por WhatsApp. Limpiando credenciales...');
                if (fs.existsSync(AUTH_DIR)) {
                    fs.rmSync(AUTH_DIR, { recursive: true, force: true });
                }
                reconnectAttempts = 0;
                setTimeout(connectToWhatsApp, 2000);
            } else if (shouldReconnect) {
                // Si la sesión aún no está vinculada, reintentamos con backoff suave
                reconnectAttempts++;
                const delay = Math.min(reconnectAttempts * 3000, 20000);
                console.log(`[WhatsApp Bot] ⚠️ Desconectado (${statusCode || 'timeout'}). Reintentando en ${delay / 1000}s...`);
                setTimeout(connectToWhatsApp, delay);
            }
        }

        if (connection === 'open') {
            currentQR = null;
            connectionStatus = 'connected';
            reconnectAttempts = 0;
            linkedNumber = sock.user?.id?.split(':')[0] || sock.user?.id?.split('@')[0] || 'desconocido';
            console.log(`[WhatsApp Bot] ✅ Conectado exitosamente como +${linkedNumber}`);
        }
    });
}

// ── Formatear Número de Teléfono para WhatsApp ────────────────────────────
function formatPhoneForWA(phone) {
    // Limpiar todo excepto dígitos
    let digits = phone.replace(/\D/g, '');

    // Si son 8 dígitos y empiezan con 6 o 7 (Bolivia), agregar 591
    if (digits.length === 8 && (digits[0] === '6' || digits[0] === '7')) {
        digits = '591' + digits;
    }

    // Formato JID de WhatsApp
    return digits + '@s.whatsapp.net';
}

// ── API: Estado de Conexión ────────────────────────────────────────────────
app.get('/status', (req, res) => {
    // Si está desconectado y han pasado más de 10s, auto-iniciar reconexión
    if (connectionStatus === 'disconnected' && !sock) {
        connectToWhatsApp();
    }
    res.json({
        status: connectionStatus,
        linkedNumber: linkedNumber,
        hasQR: currentQR !== null,
    });
});

// ── API: Forzar Reconexión ─────────────────────────────────────────────────
app.all('/reconnect', (req, res) => {
    reconnectAttempts = 0;
    connectToWhatsApp();
    res.json({ success: true, message: 'Reconexión iniciada' });
});

// ── API: Obtener QR como Imagen PNG ────────────────────────────────────────
app.get('/qr', async (req, res) => {
    if (!currentQR) {
        if (connectionStatus === 'disconnected') {
            connectToWhatsApp();
        }
        return res.status(404).json({ error: 'No hay código QR disponible. Puede que ya estés conectado.' });
    }
    try {
        const qrPNG = await QRCode.toBuffer(currentQR, { width: 300, margin: 2 });
        res.set('Content-Type', 'image/png');
        res.send(qrPNG);
    } catch (err) {
        res.status(500).json({ error: 'Error al generar imagen QR.' });
    }
});

// ── API: Obtener QR como Data URI (Base64) ─────────────────────────────────
app.get('/qr-data', async (req, res) => {
    if (!currentQR) {
        if (connectionStatus === 'disconnected') {
            connectToWhatsApp();
        }
        return res.status(404).json({ error: 'No hay código QR disponible aún. Generando...', status: connectionStatus });
    }
    try {
        const dataUri = await QRCode.toDataURL(currentQR, { width: 300, margin: 2 });
        res.json({ qr: dataUri, status: connectionStatus });
    } catch (err) {
        res.status(500).json({ error: 'Error al generar QR.' });
    }
});

// ── API: Enviar Imagen ─────────────────────────────────────────────────────
app.post('/send-image', async (req, res) => {
    if (connectionStatus !== 'connected' || !sock) {
        return res.status(503).json({ success: false, error: 'WhatsApp no está conectado. Escanea el QR primero.' });
    }

    const { phone, imageBase64, caption } = req.body;

    if (!phone || !imageBase64) {
        return res.status(400).json({ success: false, error: 'Se requieren "phone" e "imageBase64".' });
    }

    try {
        const jid = formatPhoneForWA(phone);
        const imageBuffer = Buffer.from(imageBase64, 'base64');

        await sock.sendMessage(jid, {
            image: imageBuffer,
            caption: caption || '🧾 Comprobante de Pago - Casa de Empeño',
            mimetype: 'image/png',
        });

        console.log(`[WhatsApp Bot] 📤 Imagen enviada a +${phone}`);
        res.json({ success: true, message: `Imagen enviada a +${phone}` });
    } catch (err) {
        console.error(`[WhatsApp Bot] ❌ Error al enviar imagen a ${phone}:`, err.message);
        res.status(500).json({ success: false, error: err.message });
    }
});

// ── API: Enviar Texto ──────────────────────────────────────────────────────
app.post('/send-text', async (req, res) => {
    if (connectionStatus !== 'connected' || !sock) {
        return res.status(503).json({ success: false, error: 'WhatsApp no está conectado.' });
    }

    const { phone, message } = req.body;

    if (!phone || !message) {
        return res.status(400).json({ success: false, error: 'Se requieren "phone" y "message".' });
    }

    try {
        const jid = formatPhoneForWA(phone);
        await sock.sendMessage(jid, { text: message });
        console.log(`[WhatsApp Bot] 📤 Texto enviado a +${phone}`);
        res.json({ success: true, message: `Texto enviado a +${phone}` });
    } catch (err) {
        console.error(`[WhatsApp Bot] ❌ Error al enviar texto:`, err.message);
        res.status(500).json({ success: false, error: err.message });
    }
});

// ── API: Cerrar Sesión ─────────────────────────────────────────────────────
app.post('/logout', async (req, res) => {
    try {
        if (sock) {
            await sock.logout();
        }
        connectionStatus = 'disconnected';
        linkedNumber = null;
        currentQR = null;
        res.json({ success: true, message: 'Sesión cerrada.' });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// ── Iniciar Servidor ───────────────────────────────────────────────────────
app.listen(PORT, () => {
    console.log('');
    console.log('╔══════════════════════════════════════════════════════════╗');
    console.log('║  🤖 WhatsApp Bot - Casa de Empeño                      ║');
    console.log(`║  🌐 Servidor en: http://localhost:${PORT}                 ║`);
    console.log('║  📱 Escanea el QR desde el panel de administración      ║');
    console.log('╚══════════════════════════════════════════════════════════╝');
    console.log('');
    connectToWhatsApp();
});
