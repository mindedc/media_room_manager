import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  build: {
    outDir: resolve(__dirname, "../custom_components/media_room_manager/panel"),
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
      name: "MediaRoomManagerPanel",
      fileName: "panel",
      formats: ["es"],
    },
    rollupOptions: {
      external: [],
    },
  },
});
