import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// base "./" => rutas relativas, necesarias para que PyWebView (y PyInstaller) sirvan dist/ localmente.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true },
  build: { outDir: 'dist', emptyOutDir: true },
})
