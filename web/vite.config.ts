import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Port 8100 is this app's slot in the VM-wide allocation (~/PORTS.md).
// host 0.0.0.0 so the dev server is reachable from the Mac, not just inside the VM.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 8100,
    strictPort: true,
    proxy: {
      // Same-origin in development, so no CORS preflight and no absolute API
      // base URL baked into the bundle. 8007 is Traefik in front of Django.
      "/api": {
        target: "http://localhost:8007",
        changeOrigin: true,
      },
    },
  },
});
