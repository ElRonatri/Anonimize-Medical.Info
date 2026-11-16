# Firma de código (Authenticode)

> Estado: **documentado, no activado.** El ejecutable se publica hoy sin firma. Este documento
> describe cómo activarla cuando exista un certificado. Las condiciones comerciales y técnicas de
> las autoridades de certificación cambian con frecuencia: confírmalas con el proveedor antes de
> comprar.

## Por qué firmar

- **Identidad del editor:** Windows muestra el nombre del editor en lugar de «Editor desconocido».
- **Integridad:** cualquier modificación del `.exe` invalida la firma.
- **SmartScreen:** un ejecutable sin firma descargado de internet muestra «Windows protegió su PC».
  La firma, junto con la reputación que acumula el certificado con las descargas, reduce o elimina
  ese aviso.
- **Antivirus:** los ejecutables de PyInstaller sin firma generan más falsos positivos.

Las sumas SHA-256 publicadas en cada release (`SHA256SUMS.txt`) **no reemplazan** a la firma:
permiten verificar que la descarga no se corrompió ni se alteró *respecto del release publicado*,
pero no identifican al editor.

## Qué se firma

| Archivo | ¿Firmar? |
|---|---|
| `dist\AnonimizeMedical\AnonimizeMedical.exe` | **Sí** (es lo que ejecuta el usuario) |
| `_internal\python3*.dll` y DLL de Python | No: ya vienen firmadas por la Python Software Foundation |
| `_internal\tesseract\*.exe` (variante `--tesseract`) | Opcional: son binarios de terceros; firmarlos atribuye al editor un código que no compiló |

## Opciones de certificado

Desde junio de 2023 las claves privadas de los certificados de firma de código deben residir en
hardware certificado (token USB o HSM en la nube), así que ya no se usan archivos `.pfx` sueltos.

1. **Azure Trusted Signing** (servicio gestionado de Microsoft): sin token físico; la identidad la
   valida Microsoft y la clave vive en su HSM. Se integra con GitHub Actions. Verifica la
   disponibilidad para tu país y tipo de organización.
2. **Certificado OV o EV de una CA** (DigiCert, Sectigo, GlobalSign, SSL.com...) con la clave en un
   HSM en la nube (Azure Key Vault, Google Cloud KMS, el servicio de la propia CA) para poder firmar
   desde el CI. Un token USB sólo sirve para firmar en un equipo local.

## Dónde va en el pipeline

La firma va **después de PyInstaller y antes de comprimir**, para que el ZIP y su suma SHA-256
correspondan al ejecutable firmado. El punto está marcado en
`.github/workflows/build-windows.yml` («Firma Authenticode (opcional)»):

```
PyInstaller → autoprueba → [FIRMA] → ZIP → SHA-256 → release
```

Una prueba (`tests/test_release.py`) verifica que ese punto quede antes del ZIP.

### Ejemplo con Azure Trusted Signing

Requiere un *environment* de GitHub (p. ej. `release`) con revisores obligatorios y autenticación
OIDC (federada) con Azure, sin secretos de larga duración en el repositorio:

```yaml
# En build-windows.yml, en el punto marcado (y `permissions: id-token: write` en el job):
      - uses: azure/login@v2
        if: inputs.sign
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - uses: azure/trusted-signing-action@v0
        if: inputs.sign
        with:
          endpoint: https://<región>.codesigning.azure.net/
          trusted-signing-account-name: <cuenta>
          certificate-profile-name: <perfil>
          files-folder: dist/AnonimizeMedical
          files-folder-filter: exe
          file-digest: SHA256
          timestamp-rfc3161: http://timestamp.acs.microsoft.com
          timestamp-digest: SHA256
```

Fija la versión de cada acción a una etiqueta o *commit* concreto antes de usarla.

### Ejemplo con signtool y una clave en HSM

```powershell
# El proveedor del HSM instala su CSP/KSP; /sha1 selecciona el certificado por huella.
signtool sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com `
  /sha1 <HUELLA_DEL_CERTIFICADO> /d "Anonimize Medical" `
  dist\AnonimizeMedical\AnonimizeMedical.exe
```

- `/tr` + `/td`: **sello de tiempo RFC 3161**, imprescindible para que la firma siga siendo válida
  cuando el certificado expire.
- `/fd SHA256`: algoritmo del resumen (SHA-1 está obsoleto).

## Verificar la firma

```powershell
signtool verify /pa /v dist\AnonimizeMedical\AnonimizeMedical.exe
Get-AuthenticodeSignature .\AnonimizeMedical.exe | Format-List Status, SignerCertificate, TimeStamperCertificate
```

`Status` debe ser `Valid` y debe existir `TimeStamperCertificate`. Al activar la firma conviene
agregar este control a la autoprueba del CI (paso «Autoprueba del ejecutable»).

## Buenas prácticas

- Firmar sólo en el workflow de release (tags), nunca en *pull requests* de terceros.
- Proteger el *environment* de firma con revisores obligatorios.
- No usar UPX (el spec ya lo desactiva): empeora los falsos positivos y puede romper la firma.
- Revocar el certificado ante cualquier sospecha de compromiso de la clave.
