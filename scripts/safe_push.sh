#!/usr/bin/env bash
# Publica el trabajo de una corrida SIN PERDERLO NUNCA, aunque otra corrida haya
# publicado primero. Antes usábamos `git push || true`: si el push era rechazado el
# informe se perdía en silencio y el workflow igual reportaba éxito (así se perdieron
# CLSK el 24-ago y CENCOSUD el 16-ago). Ahora, si el remoto se movió, se vuelve al
# remoto limpio y se REAPLICA solo el activo de esta corrida; y si aun así no se puede
# publicar, el script falla con código 1 para que el aviso diga la verdad.
#
# Uso: scripts/safe_push.sh "mensaje de commit" [TICKER] [SIMBOLO_TRADINGVIEW]
set -uo pipefail

MSG="${1:?falta el mensaje de commit}"
TICKER="${2:-}"
SYMBOL="${3:-}"
INTENTOS=6

git config user.name  "dashboard-bot"
git config user.email "actions@users.noreply.github.com"

git add -A
if git diff --cached --quiet; then
  echo "Sin cambios que publicar."
  exit 0
fi
git commit -q -m "$MSG"

for i in $(seq 1 $INTENTOS); do
  if git push 2>&1; then
    echo "✓ Publicado (intento $i/$INTENTOS)."
    exit 0
  fi
  echo "⚠️  Push rechazado: otra corrida publicó primero. Reintegrando (intento $i/$INTENTOS)…"

  if [ -z "$TICKER" ]; then
    # Sin activo concreto (números diarios, calendario): rebase normal.
    git fetch -q --unshallow origin 2>/dev/null || git fetch -q origin main
    git rebase -q origin/main || {
      echo "❌ No se pudo rebasar sobre el remoto."; git rebase --abort 2>/dev/null; exit 1; }
    continue
  fi

  # Con activo: guardamos SU informe, volvemos al remoto limpio y lo reaplicamos.
  KEEP=$(mktemp -d)
  cp -a "data/${TICKER}.json" "$KEEP/" 2>/dev/null || {
    echo "❌ No encuentro data/${TICKER}.json — no puedo reintegrar sin arriesgar el informe."; exit 1; }
  git fetch -q origin main || { echo "❌ No pude traer el remoto."; exit 1; }
  git reset -q --hard origin/main

  # Si el activo era nuevo, el cableado también se fue con el reset: add_asset es idempotente.
  if ! grep -q "\"${TICKER}\":" scripts/update_numbers.py; then
    python3 scripts/add_asset.py "$TICKER" ${SYMBOL:+"$SYMBOL"} || {
      echo "❌ No pude recablear ${TICKER} sobre el remoto nuevo."; exit 1; }
  fi

  cp -a "$KEEP/${TICKER}.json" "data/${TICKER}.json"
  python3 scripts/apply_asset.py "$TICKER" || { echo "❌ Falló la reinyección de ${TICKER}."; exit 1; }
  python3 scripts/update_numbers.py || { echo "❌ Falló la reconstrucción."; exit 1; }

  git add -A
  git diff --cached --quiet && { echo "El remoto ya traía este informe."; exit 0; }
  git commit -q -m "$MSG (reintegrado sobre el remoto)"
done

echo "❌ No se pudo publicar tras $INTENTOS intentos. El trabajo NO quedó guardado."
exit 1
