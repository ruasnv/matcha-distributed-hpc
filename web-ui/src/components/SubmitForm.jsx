import { useState, useEffect } from 'react';
import { TextInput, Button, Stack, Title, Paper, FileInput, Text as MantineText} from '@mantine/core';
import JSZip from 'jszip';
import { useUser } from '@clerk/clerk-react';

// Use the environment variable so it works  Render
const API_URL = import.meta.env.VITE_API_URL;
const CONSUMER_API_KEY = "ultrasecretconsumerkey456"; 

export function SubmitForm() {
  const { user } = useUser();
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [entryPoint, setEntryPoint] = useState('main.py');

  // DEBUG: Track if the file is actually being captured
  useEffect(() => {
    if (file) {
      console.log("📂 File captured by React:", file.name, "(", file.size, "bytes )");
    }
  }, [file]);

  const handleUploadAndSubmit = async () => {
    console.log("Button Clicked!"); // If you don't see this, the button logic is broken

    if (!user || !user.id) {
        alert("Wait a second! Clerk is still loading your user profile. Try again in a moment.");
        return;
    }
    
    if (!file) {
      alert("Please select a file first.");
      return;
    }
    
    setUploading(true);

    try {
      const zip = new JSZip();
      if (file.name.endsWith('.zip')) {
        await zip.loadAsync(file);
      } else {
        zip.file(file.name, file);
      }
      
      const zipBlob = await zip.generateAsync({ type: 'blob' });

      const formData = new FormData();
      formData.append('file', zipBlob, 'project.zip'); 
      formData.append('clerk_id', user.id);

      console.log("📡 Sending to:", `${API_URL}/consumer/upload_project`);

      const uploadRes = await fetch(`${API_URL}/consumer/upload_project`, {
        method: 'POST',
        headers: { 'X-API-Key': CONSUMER_API_KEY },
        body: formData
      });

      if (!uploadRes.ok) throw new Error('R2 Upload failed');

      const { project_url } = await uploadRes.json();
      
      const submitRes = await fetch(`${API_URL}/consumer/submit_task`, {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'X-API-Key': CONSUMER_API_KEY 
        },
        body: JSON.stringify({
          clerk_id: user.id,
          input_path: project_url,
          docker_image: 'runner:latest',
          script_path: entryPoint 
        })
      });

      if (!submitRes.ok) throw new Error('Task Queueing failed');

      alert("🚀 Task is now in the global queue!");
      setFile(null);
    } catch (err) {
      console.error("Critical Error:", err);
      alert(err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
  <Paper withBorder p="xl" radius="md" shadow="sm">
    <Stack>
      <Title order={4}>Deploy Research Code</Title>
      
      {/* 1. DEBUG LABEL: If this says "No file", the UI will never change */}
      <MantineText size="xs" c={file ? "green" : "red"} fw={700}>
        STATE STATUS: {file ? `File Ready (${file.name})` : "No file in state"}
      </MantineText>

      <FileInput 
        key="matcha-file-input" 
        label="Research Script or ZIP" 
        placeholder="Click to browse" 
        value={file} 
        onChange={(payload) => {
          console.log("🔥 onChange payload:", payload);
          if (payload) {
            setFile(payload);
          }
        }} 
        required
      />
      
      <TextInput 
        label="Entry Point Script"
        value={entryPoint}
        onChange={(e) => setEntryPoint(e.target.value)}
      />

      <Button 
        onClick={() => {
            console.log("Submit button actually clicked. File in state is:", file);
            handleUploadAndSubmit();
        }} 
        loading={uploading} 
        fullWidth 
        color={file !== null ? "green" : "gray"}
        disabled={file === null}
    >
      {file !== null ? `Run ${file.name} on Network` : "Select a File First"}
    </Button>
    </Stack>
  </Paper>
);
}