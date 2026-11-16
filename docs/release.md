# Cómo publicar un release

Cada release publica las tres variantes de Windows (base, ocr, tesseract) como ZIP, junto con
`SHA256SUMS.txt`. Todo lo hace `.github/workflows/release.yml`; nada se compila a mano.

## Pasos

1. **Versión.** Actualiza `__version__` en `backend/anonymizer/__init__.py` y `version` en
   `frontend/package.json` (una prueba exige que coincidan).
2. **CHANGELOG.** Renombra `## [Unreleased]` a `## [X.Y.Z] - AAAA-MM-DD` y deja un
   `## [Unreleased]` vacío arriba. Las notas del release salen de esa sección.
3. **Ensayo (opcional, recomendado).** En GitHub: *Actions → Release → Run workflow* con
   «publish» desactivado. Compila y prueba las tres variantes y deja `SHA256SUMS.txt` y los ZIP
   como artefacto, sin publicar nada.
4. **Tag.** Tras fusionar a `main`:
   ```bash
   git tag -a vX.Y.Z -m "Anonimize Medical X.Y.Z"
   git push origin vX.Y.Z
   ```
   El workflow verifica que el tag coincida con `__version__` y que el CHANGELOG tenga la sección;
   compila las variantes, ejecuta la autoprueba de cada `.exe` (motor, exportación, red bloqueada,
   procesos en paralelo, OCR sin conexión) y publica el release con las sumas.

## Verificar una descarga

En PowerShell:

```powershell
Get-FileHash .\AnonimizeMedical-X.Y.Z-windows-base.zip -Algorithm SHA256
```

o con `certutil -hashfile AnonimizeMedical-X.Y.Z-windows-base.zip SHA256`, y compara el resultado
con la línea correspondiente de `SHA256SUMS.txt` (también aparece en las notas del release). Con
Python: `python scripts/checksums.py verify SHA256SUMS.txt` en la carpeta de las descargas.

Los builds de PyInstaller no son reproducibles bit a bit: la suma certifica el archivo publicado,
no un build hecho en otro equipo.

## Firma

El ejecutable todavía no se firma. Ver [signing.md](signing.md) para activarla.
