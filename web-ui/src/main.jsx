import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import { ClerkProvider} from '@clerk/clerk-react'; // Import Clerk
import { dark } from '@clerk/themes';
import App from './App.jsx';
import '@mantine/core/styles.css';

// Import your key
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!PUBLISHABLE_KEY) {
  throw new Error("Missing Publishable Key");
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* Wrap everything in ClerkProvider */}
    {/* We add "appearance={{ baseTheme: dark }}" to make the login box dark mode too */}
    <ClerkProvider publishableKey={PUBLISHABLE_KEY} appearance={{ baseTheme: dark }}>
      <MantineProvider defaultColorScheme="dark">
        <App />
      </MantineProvider>
    </ClerkProvider>
  </React.StrictMode>
);