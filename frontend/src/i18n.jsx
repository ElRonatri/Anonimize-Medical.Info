import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { loadPref, savePref } from './storage.js'

const messages = {
  es: {
    appSubtitle: 'Anonimización local de documentos clínicos',
    uiLanguage: 'Idioma de la interfaz',
    themeToggle: 'Cambiar tema',

    inputTitle: 'Documento',
    tabFile: 'Archivo',
    tabPaste: 'Pegar texto',
    dropTitle: 'Arrastra un PDF aquí',
    dropSubtitle: 'o haz clic para seleccionarlo',
    dropHint: 'Historia clínica, exámenes, epicrisis, informes… (PDF o TXT)',
    dropActive: 'Suelta el archivo para procesarlo',
    changeFile: 'Cambiar archivo',
    pastePlaceholder: 'Pega aquí el texto del documento clínico…',
    anonymizeText: 'Anonimizar texto',
    pages: (n) => `${n} ${n === 1 ? 'página' : 'páginas'}`,

    optionsTitle: 'Opciones',
    docLanguage: 'Idioma del documento',
    langAuto: 'Detectar automáticamente',
    langEs: 'Español',
    langEn: 'Inglés',
    outputFormat: 'Formato de salida',
    formatMarkdown: 'Markdown',
    formatText: 'Texto plano',
    replacementStyle: 'Marcadores',
    styleNumbered: 'Numerados',
    styleTag: 'Genéricos',
    optProfessionals: 'Anonimizar nombres de profesionales',
    optProfessionalsHint: 'Médicos, enfermeras y firmantes del documento',
    optAllDates: 'Ocultar todas las fechas',
    optAllDatesHint: 'Por defecto sólo se oculta la fecha de nacimiento',
    optAddresses: 'Ocultar direcciones y localidades',
    optRepeated: 'Quitar encabezados y pies repetidos',
    optPageMarkers: 'Indicar número de página',
    customTerms: 'Términos adicionales a ocultar',
    customTermsHint: 'Uno por línea: nombres, instituciones u otros datos que no se detectaron.',
    customTermsPlaceholder: 'Ej.: Clínica Los Andes',
    apply: 'Aplicar',

    resultTitle: 'Resultado anonimizado',
    viewHighlighted: 'Vista',
    viewEdit: 'Editar',
    copy: 'Copiar',
    copied: '¡Copiado!',
    save: 'Guardar',
    saved: 'Guardado',
    processing: 'Procesando documento…',
    emptyResultTitle: 'Aún no hay resultados',
    emptyResultText: 'Selecciona un PDF o pega texto para obtener una versión anonimizada lista para copiar.',
    statPages: 'Páginas',
    statReplacements: 'Reemplazos',
    statLanguage: 'Idioma',
    statTime: 'Tiempo',
    editedNotice: 'Editaste el resultado manualmente. Si cambias opciones, se regenerará.',

    entitiesTitle: 'Datos detectados',
    entitiesEmpty: 'No se detectaron datos personales. Revisa el texto y agrega términos manualmente si es necesario.',
    showValues: 'Mostrar valores originales',
    hideValues: 'Ocultar valores originales',
    keepVisible: 'No anonimizar (falso positivo)',
    restore: 'Volver a anonimizar',
    excludedTitle: 'Excluidos por ti',
    occurrences: (n) => `${n} ${n === 1 ? 'vez' : 'veces'}`,

    categories: {
      PATIENT: 'Paciente', PERSON: 'Otras personas', PROFESSIONAL: 'Profesionales',
      ID: 'Documento de identidad', RECORD: 'N° de ficha / registro', BIRTHDATE: 'Fecha de nacimiento',
      DATE: 'Fechas', PHONE: 'Teléfonos', EMAIL: 'Correos', ADDRESS: 'Direcciones',
      URL: 'Enlaces', IP: 'Direcciones IP', CUSTOM: 'Términos personalizados',
    },

    privacyNote: 'Todo se procesa localmente en este equipo. Revisa siempre el resultado antes de compartirlo: la detección automática puede omitir datos.',
    browserMode: 'Modo navegador: el motor de Python no está disponible. Ejecuta la aplicación con “python backend/main.py”.',

    warnings: {
      no_text: 'El PDF no contiene texto seleccionable (probablemente es un escaneo). Instala el OCR opcional para procesarlo.',
      no_text_after_ocr: 'No se pudo reconocer texto en el documento, ni siquiera con OCR.',
      some_pages_without_text: 'Algunas páginas no tienen texto seleccionable (posible escaneo) y no se procesaron.',
      ocr_used: (n) => `Se aplicó OCR en ${n} ${n === 1 ? 'página' : 'páginas'}: revisa el texto con atención.`,
      page_error: 'Una o más páginas no pudieron leerse.',
      ocr_error: 'Falló el OCR en una o más páginas.',
    },
    errors: {
      file_not_found: 'No se encontró el archivo.',
      file_too_large: 'El archivo es demasiado grande (máx. 80 MB).',
      unsupported: 'Formato no soportado. Usa archivos PDF o TXT.',
      invalid_pdf: 'El PDF está dañado o protegido con contraseña.',
      read_error: 'No se pudo leer el archivo.',
      process_error: 'Ocurrió un error al anonimizar el documento.',
      empty_text: 'Pega algún texto antes de anonimizar.',
      no_document: 'Primero carga un documento.',
      clipboard_error: 'No se pudo copiar al portapapeles.',
      write_error: 'No se pudo guardar el archivo.',
      no_backend: 'El motor de procesamiento no está disponible.',
      generic: 'Ocurrió un error inesperado.',
    },
  },

  en: {
    appSubtitle: 'Local de-identification of clinical documents',
    uiLanguage: 'Interface language',
    themeToggle: 'Toggle theme',

    inputTitle: 'Document',
    tabFile: 'File',
    tabPaste: 'Paste text',
    dropTitle: 'Drop a PDF here',
    dropSubtitle: 'or click to browse',
    dropHint: 'Medical records, lab results, discharge summaries, reports… (PDF or TXT)',
    dropActive: 'Release to process the file',
    changeFile: 'Change file',
    pastePlaceholder: 'Paste the clinical document text here…',
    anonymizeText: 'Anonymize text',
    pages: (n) => `${n} ${n === 1 ? 'page' : 'pages'}`,

    optionsTitle: 'Options',
    docLanguage: 'Document language',
    langAuto: 'Detect automatically',
    langEs: 'Spanish',
    langEn: 'English',
    outputFormat: 'Output format',
    formatMarkdown: 'Markdown',
    formatText: 'Plain text',
    replacementStyle: 'Placeholders',
    styleNumbered: 'Numbered',
    styleTag: 'Generic',
    optProfessionals: 'Anonymize healthcare providers',
    optProfessionalsHint: 'Physicians, nurses and document signers',
    optAllDates: 'Hide all dates',
    optAllDatesHint: 'By default only the date of birth is hidden',
    optAddresses: 'Hide addresses and localities',
    optRepeated: 'Remove repeated headers and footers',
    optPageMarkers: 'Show page numbers',
    customTerms: 'Additional terms to hide',
    customTermsHint: 'One per line: names, institutions or other data that was not detected.',
    customTermsPlaceholder: 'e.g. Mercy General Hospital',
    apply: 'Apply',

    resultTitle: 'Anonymized result',
    viewHighlighted: 'Preview',
    viewEdit: 'Edit',
    copy: 'Copy',
    copied: 'Copied!',
    save: 'Save',
    saved: 'Saved',
    processing: 'Processing document…',
    emptyResultTitle: 'No results yet',
    emptyResultText: 'Select a PDF or paste text to get a de-identified version ready to copy.',
    statPages: 'Pages',
    statReplacements: 'Replacements',
    statLanguage: 'Language',
    statTime: 'Time',
    editedNotice: 'You edited the result manually. Changing options will regenerate it.',

    entitiesTitle: 'Detected data',
    entitiesEmpty: 'No personal data detected. Review the text and add terms manually if needed.',
    showValues: 'Show original values',
    hideValues: 'Hide original values',
    keepVisible: 'Do not anonymize (false positive)',
    restore: 'Anonymize again',
    excludedTitle: 'Excluded by you',
    occurrences: (n) => `${n} ${n === 1 ? 'time' : 'times'}`,

    categories: {
      PATIENT: 'Patient', PERSON: 'Other people', PROFESSIONAL: 'Providers',
      ID: 'Identity document', RECORD: 'Record / chart number', BIRTHDATE: 'Date of birth',
      DATE: 'Dates', PHONE: 'Phone numbers', EMAIL: 'Emails', ADDRESS: 'Addresses',
      URL: 'Links', IP: 'IP addresses', CUSTOM: 'Custom terms',
    },

    privacyNote: 'Everything is processed locally on this computer. Always review the result before sharing it: automatic detection may miss data.',
    browserMode: 'Browser mode: the Python engine is not available. Run the app with “python backend/main.py”.',

    warnings: {
      no_text: 'The PDF has no selectable text (probably a scan). Install the optional OCR add-on to process it.',
      no_text_after_ocr: 'No text could be recognized in the document, even with OCR.',
      some_pages_without_text: 'Some pages have no selectable text (possibly scanned) and were not processed.',
      ocr_used: (n) => `OCR was applied on ${n} ${n === 1 ? 'page' : 'pages'}: review the text carefully.`,
      page_error: 'One or more pages could not be read.',
      ocr_error: 'OCR failed on one or more pages.',
    },
    errors: {
      file_not_found: 'File not found.',
      file_too_large: 'The file is too large (max. 80 MB).',
      unsupported: 'Unsupported format. Use PDF or TXT files.',
      invalid_pdf: 'The PDF is damaged or password protected.',
      read_error: 'The file could not be read.',
      process_error: 'An error occurred while anonymizing the document.',
      empty_text: 'Paste some text before anonymizing.',
      no_document: 'Load a document first.',
      clipboard_error: 'Could not copy to the clipboard.',
      write_error: 'Could not save the file.',
      no_backend: 'The processing engine is not available.',
      generic: 'An unexpected error occurred.',
    },
  },
}

export const UI_LANGUAGES = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
]

const I18nContext = createContext(null)

function initialLanguage() {
  const saved = loadPref('uiLanguage')
  if (saved && messages[saved]) return saved
  const nav = (navigator.language || 'es').slice(0, 2)
  return messages[nav] ? nav : 'es'
}

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(initialLanguage)

  useEffect(() => {
    savePref('uiLanguage', lang)
    document.documentElement.lang = lang
  }, [lang])

  const t = useCallback(
    (key, ...args) => {
      const value = key.split('.').reduce((obj, k) => (obj ? obj[k] : undefined), messages[lang])
      if (typeof value === 'function') return value(...args)
      return value ?? key
    },
    [lang],
  )

  const value = useMemo(() => ({ lang, setLang, t }), [lang, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  return useContext(I18nContext)
}
