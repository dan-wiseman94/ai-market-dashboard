import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { queryClient } from "./hooks/queryClient";
import { ThemeProvider } from "./hooks/useTheme";
import { WebSocketProvider } from "./realtime/WebSocketProvider";
import "./styles/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>
          <App />
        </WebSocketProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
