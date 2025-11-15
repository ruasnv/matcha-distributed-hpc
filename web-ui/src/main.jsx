import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import App from './App.jsx';
import '@mantine/core/styles.css'; // Import Mantine styles

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* This "provider" wraps your whole app */}
    <MantineProvider defaultColorScheme="dark">
      <App />
    </MantineProvider>
  </React.StrictMode>
);