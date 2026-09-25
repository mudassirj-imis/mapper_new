import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import App from './App.jsx';
import { APP_BASE_PATH } from './config/api';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30 * 1000,
    },
  },
});

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* basename is derived from Vite's `base` so the router and the asset
          base can never drift apart (see src/config/api.js). */}
      <BrowserRouter basename={APP_BASE_PATH || '/'}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
);