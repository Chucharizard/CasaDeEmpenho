/** Copias locales de mensajes salientes para los reintentos de cifrado de WhatsApp. */
const fs = require('node:fs');
const path = require('node:path');

function createMessageStore({ filename, proto, now = Date.now, maxEntries = 512,
    ttlMs = 7 * 24 * 60 * 60 * 1000, maxBytes = 8 * 1024 * 1024,
    onError = () => console.warn('[WhatsApp] No se pudo conservar la caché local de reintentos.') }) {
    const entries = new Map();
    function trim() {
        for (const [id, entry] of entries) {
            if (entry.savedAt + ttlMs <= now()) entries.delete(id);
        }
        while (entries.size > maxEntries) entries.delete(entries.keys().next().value);
    }
    try {
        if (fs.statSync(filename).size > maxBytes) throw new Error('Caché demasiado grande.');
        const stored = JSON.parse(fs.readFileSync(filename, 'utf8'));
        if (stored.version !== 1 || !Array.isArray(stored.messages)) throw new Error('Caché no válida.');
        for (const entry of stored.messages) {
            if (typeof entry.id === 'string' && Number.isFinite(entry.savedAt) && typeof entry.payload === 'string') {
                entries.set(entry.id, entry);
            }
        }
        trim();
    } catch (error) {
        if (error.code !== 'ENOENT') onError(error);
    }
    function persist() {
        trim();
        let content = JSON.stringify({ version: 1, messages: [...entries.values()] });
        while (entries.size && Buffer.byteLength(content) > maxBytes) {
            entries.delete(entries.keys().next().value);
            content = JSON.stringify({ version: 1, messages: [...entries.values()] });
        }
        const temporary = filename + '.' + process.pid + '.tmp';
        try {
            fs.mkdirSync(path.dirname(filename), { recursive: true });
            fs.writeFileSync(temporary, content, { mode: 0o600 });
            fs.renameSync(temporary, filename);
        } catch (error) {
            // Un fallo de disco no convierte un mensaje ya enviado en un envío fallido.
            onError(error);
        } finally {
            try { fs.unlinkSync(temporary); } catch (error) { if (error.code !== 'ENOENT') onError(error); }
        }
    }
    return {
        remember(message) {
            if (!message?.key?.id || message.key.fromMe !== true || !message.message) return;
            try {
                const payload = Buffer.from(proto.Message.encode(message.message).finish()).toString('base64');
                const savedAt = entries.get(message.key.id)?.savedAt ?? now();
                entries.set(message.key.id, { id: message.key.id, savedAt, payload });
                persist();
            } catch (error) { onError(error); }
        },
        get(key) {
            trim();
            const entry = entries.get(key?.id);
            if (!entry) return undefined;
            try { return proto.Message.decode(Buffer.from(entry.payload, 'base64')); }
            catch (error) { entries.delete(key.id); onError(error); return undefined; }
        },
        clear() { entries.clear(); },
    };
}

module.exports = { createMessageStore };
