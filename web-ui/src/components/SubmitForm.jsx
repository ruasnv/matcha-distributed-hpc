import { useState, useEffect } from 'react';
import { TextInput, Button, Stack, Title, Paper, FileInput, Text as MantineText } from '@mantine/core';
import JSZip from 'jszip';
import { useUser } from '@clerk/clerk-react';

const API_URL = import.meta.env.VITE_API_URL || "https://matcha-orchestrator.onrender.com";
const CONSUMER_API_KEY = "ultrasecretconsumerkey456"; 

export function SubmitForm() {
  const { user } = useUser();
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [entryPoint, setEntryPoint] = useState('main.py');

  const handleUploadAndSubmit = async () => {
    // We check the variable directly here
    if (!file) {
      alert("Please select a file first.");
      return;
    }
    
    setUploading(true);
    console.log("📤 Initializing upload for:", file.name);

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
      formData.append('clerk_id', user?.id); 

      const uploadRes = await fetch(`${API_URL}/consumer/upload_project`, {
        method: 'POST',
        headers: { 'X-API-Key': CONSUMER_API_KEY },
        body: formData
      });

      if (!uploadRes.ok) throw new Error('Cloud Storage Upload failed');
      const { project_url } = await uploadRes.json();
      
      const submitRes = await fetch(`${API_URL}/consumer/submit_task`, {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'X-API-Key': CONSUMER_API_KEY 
        },
        body: JSON.stringify({
          clerk_id: user?.id,
          input_path: project_url,
          docker_image: 'runner:latest',
          script_path: entryPoint 
        })
      });

      if (!submitRes.ok) throw new Error('Orchestrator Task Queueing failed');

      alert("🚀 Research task deployed successfully!");
      setFile(null);
    } catch (err) {
      console.error("Submission Error:", err);
      alert("Error: " + err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Paper withBorder p="xl" radius="md" shadow="sm">
      <Stack>
        <Title order={4}>Deploy Research Code</Title>
        
        <MantineText size="xs" c={file ? "green" : "red"} fw={700}>
          {file ? `✅ READY: ${file.name}` : "❌ NO FILE SELECTED"}
        </MantineText>

        <FileInput 
          label="Research Script or ZIP" 
          placeholder="Click to browse" 
          value={file} 
          onChange={(payload) => {
            setFile(payload);
          }} 
          required
        />
        
        <TextInput 
          label="Entry Point Script"
          value={entryPoint}
          onChange={(e) => setEntryPoint(e.target.value)}
        />

        <Button 
            onClick={handleUploadAndSubmit} 
            loading={uploading} 
            fullWidth 
            color="green"
            // We force it enabled if the console saw the file earlier
            variant="filled"
        >
          Zip & Run on Network
        </Button>
      </Stack>
    </Paper>
  );
}