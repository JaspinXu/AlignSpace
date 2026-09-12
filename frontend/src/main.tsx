import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { ApiClient } from './api';
import './styles.css';

const container = document.getElementById('root');
if (!container) throw new Error('root container is missing');
const client = new ApiClient();
createRoot(container).render(
  <StrictMode>
    <App client={client} />
  </StrictMode>,
);
