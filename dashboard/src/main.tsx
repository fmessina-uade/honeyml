import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { LangProvider } from './lib/i18n';
import { TemaProvider } from './lib/tema';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <TemaProvider>
      <LangProvider>
        <App />
      </LangProvider>
    </TemaProvider>
  </React.StrictMode>,
);
