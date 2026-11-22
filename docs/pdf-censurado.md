# PDF censurado

**Exportar → «PDF censurado (.pdf)»** recrea cada PDF **página por página, con el mismo tamaño y
aspecto**, y cubre con un recuadro negro cada dato que la aplicación oculta en el texto. Dentro
del recuadro se puede escribir el marcador (`[PACIENTE_1]`, `[RUN_CL_1]`…), opción *Mostrar el
marcador sobre la censura*. Está disponible para documentos que provienen de un PDF (no para texto
pegado ni `.txt`), uno a la vez o todos a una carpeta.

## Cómo funciona

1. **Mismas decisiones que el texto exportado.** Se usa el mismo motor con las mismas opciones,
   lista de excepciones, datos marcados como «no anonimizar» y la misma numeración de marcadores.
2. **Ubicación en la página.**
   - Páginas con texto seleccionable: posición de cada carácter (pdfplumber).
   - Páginas escaneadas (con OCR): posición de cada palabra reconocida (Tesseract por TSV en
     memoria, o las cajas de RapidOCR).
   - **Red de seguridad:** cada valor que se ocultó en el texto se busca además en cada página (sin
     tildes ni mayúsculas, espacios flexibles). Si alguno no se logra ubicar, la aplicación avisa
     con su marcador («Revisa el PDF: [PERSONA_2] no se pudo ubicar…»), nunca con el valor.
3. **Censura irreversible.** Cada página se convierte en imagen (pypdfium2) y el recuadro se pinta
   sobre los píxeles. El PDF resultante **sólo contiene esas imágenes**: no queda capa de texto,
   metadatos (título, autor), anotaciones, campos de formulario, adjuntos ni JavaScript del
   original. Así se evita el error clásico de dibujar un rectángulo encima de un texto que sigue
   ahí y se puede copiar.

## Calidad y tamaño

| Calidad | Resolución | Uso |
|---|---|---|
| Liviana | 150 ppp | enviar por correo |
| Estándar (por defecto) | 200 ppp | lectura en pantalla e impresión normal |
| Alta | 300 ppp | impresión de calidad, letra pequeña |

Las páginas se guardan como JPEG (en escala de grises si no tienen color). Un PDF de texto de pocos
KB pasa a ~100–150 KB por página a 200 ppp. Como no hay capa de texto, el resultado no se puede
buscar ni copiar: es lo esperado en una censura.

## Privacidad

- Todo ocurre en memoria; sólo se escribe el PDF que el usuario guarda (también verificado por la
  sonda de privacidad en disco del CI de Windows, que exporta PDF censurados con un dato centinela).
- El informe de la exportación sólo contiene conteos y marcadores.

## Limitaciones

- **Ediciones manuales** del texto (pestaña Editar) no se trasladan al PDF; la aplicación avisa.
- **Texto dentro de imágenes** de páginas con texto seleccionable (logos, sellos, firmas
  escaneadas) no se detecta, salvo con OCR en modo «Todas las páginas».
- **Anotaciones y campos de formulario** se omiten del resultado (no se pueden revisar); la
  aplicación indica cuántos.
- Los errores del OCR (letras mal leídas) afectan igual que en el texto: revisa el resultado.

## Páginas rotadas

Las páginas con `/Rotate` (p. ej. informes apaisados) se leen en su orientación natural de texto y
la imagen final se gira como el original. Al implementar esta función se detectó que, **antes**, la
extracción de texto de esas páginas salía desordenada o al revés y los nombres no se ocultaban;
ahora está corregido también para el texto exportado (prueba con control negativo en
`tests/test_redact_pdf.py`).

## Verificación

`tests/test_redact_pdf.py`: para las rotaciones 0/90/180/270, con y sin *cropbox* desplazada, cada
píxel del nombre (obtenido comparando la página con y sin el nombre, independiente del código de
censura) queda negro; el texto clínico no se tapa; la salida no tiene texto, metadatos ni
anotaciones del original; excepciones, marcadores, resolución, OCR (Tesseract) y la exportación por
lotes de la API. La autoprueba del `.exe` incluye un PDF censurado (`redacted_pdf`).
