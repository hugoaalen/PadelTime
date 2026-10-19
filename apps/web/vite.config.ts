import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwind from '@tailwindcss/vite';
export default defineConfig({plugins:[react(),tailwind()],build:{rollupOptions:{input:{main:'index.html','push-worker':'src/push-worker.ts'},output:{entryFileNames:chunk=>chunk.name==='push-worker'?'sw.js':'assets/[name]-[hash].js'}}},server:{proxy:{'/api':'http://127.0.0.1:8000'}}});
