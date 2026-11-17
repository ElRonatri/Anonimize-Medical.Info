<#
.SYNOPSIS
  Busca un dato centinela en el disco (texto plano y UTF-16), para verificar que la aplicación no
  deja datos clínicos en el equipo. Lo usa el CI de Windows después de la sonda de privacidad.

.PARAMETER Token
  Texto a buscar (la parte aleatoria del nombre centinela). Se busca también en minúsculas.
.PARAMETER Since
  Sólo se revisan los archivos modificados desde este momento (los demás no pudo escribirlos la app).
.PARAMETER Roots
  Carpetas a recorrer (p. ej. %TEMP%, %LOCALAPPDATA%, %APPDATA%).
.PARAMETER Always
  Carpetas que se revisan completas, sin filtro de fecha (p. ej. las de la aplicación).

  Sale con código 1 si encuentra el centinela, y lista los archivos (nunca su contenido).
#>
param(
  [Parameter(Mandatory)] [string] $Token,
  [Parameter(Mandatory)] [datetime] $Since,
  [Parameter(Mandatory)] [string[]] $Roots,
  [string[]] $Always = @(),
  [long] $MaxBytes = 300MB
)

$ErrorActionPreference = "Stop"
$latin1 = [System.Text.Encoding]::GetEncoding(28591)  # 1 byte = 1 carácter: búsqueda binaria exacta
$variants = @($Token, $Token.ToLowerInvariant(), $Token.ToUpperInvariant()) | Select-Object -Unique
$needles = @()
foreach ($t in $variants) {
  $needles += $latin1.GetString([System.Text.Encoding]::UTF8.GetBytes($t))
  $needles += $latin1.GetString([System.Text.Encoding]::Unicode.GetBytes($t))  # UTF-16LE
}

$files = [System.Collections.Generic.Dictionary[string, System.IO.FileInfo]]::new()
foreach ($root in $Roots + $Always) {
  if (-not (Test-Path -LiteralPath $root)) { continue }
  $all = $Always -contains $root
  Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
    if ($all -or $_.LastWriteTime -ge $Since -or $_.CreationTime -ge $Since) { $files[$_.FullName] = $_ }
  }
}

$scanned = 0; $skipped = 0; $locked = 0; $hits = @()
foreach ($f in $files.Values) {
  if ($f.Length -gt $MaxBytes) { $skipped++; continue }
  try {
    $text = $latin1.GetString([System.IO.File]::ReadAllBytes($f.FullName))
  } catch {
    $locked++; continue
  }
  $scanned++
  foreach ($n in $needles) {
    if ($text.IndexOf($n, [System.StringComparison]::Ordinal) -ge 0) { $hits += $f.FullName; break }
  }
}

Write-Host "Archivos revisados: $scanned · omitidos por tamaño: $skipped · bloqueados: $locked"
Write-Host "Carpetas: $(($Roots + $Always) -join '; ')"
if ($hits.Count) {
  Write-Host "CENTINELA ENCONTRADO en:"
  $hits | ForEach-Object { Write-Host "  $_" }
  exit 1
}
Write-Host "Centinela no encontrado."
exit 0
