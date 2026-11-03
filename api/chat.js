// Función serverless del chat de la app. Responde preguntas libres sobre un
// activo, usando SOLO el informe ya investigado de ese activo como contexto
// (sin búsqueda web en vivo — pedido explícito del usuario, por velocidad y costo).
//
// Vive en un proyecto de Vercel separado ("stock-dashboard-chat"), conectado al
// mismo repo de GitHub que GitHub Pages usa para servir la app estática — dos
// plataformas distintas leyendo el mismo repo, sin pisarse.
//
// Variables de entorno requeridas (configurar en Vercel, nunca en el código):
//   ANTHROPIC_API_KEY   — clave de console.anthropic.com (sk-ant-api03-...)
//   CHAT_SHARED_SECRET  — secreto compartido con el frontend (api/chat_client.js
//                          lo manda en el header X-Chat-Secret). No es seguridad
//                          real (el repo es público, el secreto queda visible en
//                          el HTML), pero frena bots/crawlers casuales — el
//                          límite de pedidos por minuto en el Firewall de Vercel
//                          es la protección real contra abuso de costo.

const fs = require("fs");
const path = require("path");

const ALLOWED_ORIGIN = "https://agustinmosqueira.github.io";
const MODEL = "claude-sonnet-5";
const MAX_QUESTION_LEN = 1000;

const SYSTEM_PROMPT = `Eres el asistente del dashboard de research de Agustín. Respondés preguntas SOLO en base al informe que te paso a continuación — nunca inventes datos que no estén ahí. Si la pregunta pide algo que el informe no cubre (ej. un dato más reciente que la fecha del informe), decilo explícitamente en vez de inventar o suponer. Respondé en español, directo y conciso (salvo que el usuario pida explícitamente más extensión — p.ej. "resumen de 10 líneas" significa eso, no un ensayo). Cuando sea relevante, citá qué parte del informe sostiene tu respuesta (ej. "según la sección de catalizadores..."). No sos un asesor financiero: si la pregunta busca una recomendación de compra/venta, respondé con la LECTURA del informe (score, señal, catalizadores, qué tendría que pasar para que cambie), nunca como un consejo personal de inversión.`;

function safeName(ticker) {
  return ticker.includes("/") ? "FX-" + ticker.replace(/\//g, "") : ticker;
}

function setCors(res) {
  res.setHeader("Access-Control-Allow-Origin", ALLOWED_ORIGIN);
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-Chat-Secret");
}

function buildContext(asset) {
  const partes = [];
  if (asset.reportDate) partes.push(`Fecha del informe: ${asset.reportDate}`);
  if (asset.company) partes.push(`Empresa/activo: ${asset.company}`);
  if (asset.perfil) partes.push(`Perfil del negocio:\n${asset.perfil}`);
  if (asset.statsList && asset.statsList.length) {
    partes.push("Datos clave:\n" + asset.statsList.map(([k, v]) => `- ${k}: ${v}`).join("\n"));
  }
  if (asset.technical) {
    const t = asset.technical;
    partes.push(
      `Precio y técnico (calculado, no inventado): precio ${t.price}, ` +
      `cambio día ${t.change_1d_pct}%, cambio semana ${t.change_1w_pct}%, RSI ${t.rsi}, ` +
      `MACD ${t.macd}/${t.macd_signal}, % vs SMA20/50/200: ${t.pct_vs_sma20}/${t.pct_vs_sma50}/${t.pct_vs_sma200}, ` +
      `percentil rango 1 año ${t.price_percentile_1y}.`
    );
  }
  if (asset.scores) {
    partes.push(
      "Scores (0-100, metodología anti-momentum del dashboard):\n" +
      Object.entries(asset.scores).map(([k, v]) => `- ${k}: ${v.score}/100 — ${v.just}`).join("\n")
    );
  }
  if (asset.sections) {
    for (const [k, v] of Object.entries(asset.sections)) {
      if (v) partes.push(`## ${k}\n${v}`);
    }
  }
  if (asset.opportunity) {
    partes.push("Compuesto de oportunidad y plan:\n" + JSON.stringify(asset.opportunity, null, 1));
  }
  if (asset.events && asset.events.length) {
    partes.push("Próximos eventos:\n" + asset.events.map(e => `- ${e.date}: ${e.label} — ${e.info || ""}`).join("\n"));
  }
  return partes.join("\n\n");
}

module.exports = async (req, res) => {
  setCors(res);
  if (req.method === "OPTIONS") {
    res.status(204).end();
    return;
  }
  if (req.method !== "POST") {
    res.status(405).json({ error: "método no permitido" });
    return;
  }

  const secret = req.headers["x-chat-secret"];
  if (!process.env.CHAT_SHARED_SECRET || secret !== process.env.CHAT_SHARED_SECRET) {
    res.status(401).json({ error: "no autorizado" });
    return;
  }
  if (!process.env.ANTHROPIC_API_KEY) {
    res.status(500).json({ error: "el servidor no tiene configurada la API key" });
    return;
  }

  let body = req.body;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch {
      body = {};
    }
  }
  const { ticker, question } = body || {};
  if (!ticker || typeof ticker !== "string") {
    res.status(400).json({ error: "falta el ticker" });
    return;
  }
  if (!question || typeof question !== "string" || !question.trim()) {
    res.status(400).json({ error: "falta la pregunta" });
    return;
  }
  if (question.length > MAX_QUESTION_LEN) {
    res.status(400).json({ error: `la pregunta es demasiado larga (máx ${MAX_QUESTION_LEN} caracteres)` });
    return;
  }

  const tickerUpper = ticker.toUpperCase();
  const fpath = path.join(process.cwd(), "data", safeName(tickerUpper) + ".json");
  let asset;
  try {
    asset = JSON.parse(fs.readFileSync(fpath, "utf8"));
  } catch {
    res.status(404).json({ error: `No encuentro el informe de ${tickerUpper}` });
    return;
  }

  const contexto = buildContext(asset);

  try {
    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": process.env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 800,
        system: SYSTEM_PROMPT,
        messages: [
          {
            role: "user",
            content: `INFORME DE ${asset.ticker} (${asset.company || ""}):\n\n${contexto}\n\n---\n\nPREGUNTA DEL USUARIO:\n${question}`,
          },
        ],
      }),
    });

    if (!r.ok) {
      const errText = await r.text();
      res.status(502).json({ error: "Error llamando a la IA", detail: errText.slice(0, 300) });
      return;
    }

    const data = await r.json();
    const answer = (data.content || []).map((b) => b.text || "").join("");
    res.status(200).json({ answer, ticker: asset.ticker, reportDate: asset.reportDate || null });
  } catch (e) {
    res.status(500).json({ error: "Error interno", detail: String(e).slice(0, 300) });
  }
};
