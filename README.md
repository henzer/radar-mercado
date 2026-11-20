# Radar de mercado

Dashboard personal: tendencia del Nasdaq-100 y Tecnología vs. su media de 200 días,
rotación de los 11 sectores contra el S&P 500, VIX, spreads de crédito y posicionamiento
de hedge funds (CFTC).

- `scripts/update.py` descarga los datos públicos de FRED y CFTC y escribe `data.json`.
- `.github/workflows/update.yml` lo corre automáticamente de lunes a viernes (22:30 UTC)
  y guarda el resultado en el repositorio. También se puede correr a mano desde la pestaña
  **Actions → Actualizar datos → Run workflow**.
- `index.html` es la página (GitHub Pages) que lee `data.json`.

Herramienta informativa; no es asesoría financiera.
