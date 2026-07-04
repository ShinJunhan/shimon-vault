import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The built output (dist/) is what FastAPI will serve same-origin in
// production. In dev, `npm run dev` serves on http://localhost:5173 and the
// app calls your API via VITE_API_BASE (see .env.example / src/api.js).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
