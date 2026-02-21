import { useState } from 'react';
import { TextInput, Button, Stack, Title, Paper, FileInput } from '@mantine/core';
import JSZip from 'jszip';
import { useUser } from '@clerk/clerk-react';

// Use the environment variable so it works on both Local and Render
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";
const CONSUMER_API_KEY = "ultrasecretconsumerkey456"; 

export function SubmitForm() {
  const { user } = useUser();
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [entryPoint, setEntryPoint] = useState('main.py');

  const handleUploadAndSubmit = async () => {
    if (!file || !user) {
      alert("Please select a file and ensure you are signed in.");
      return;
    }
    
    setUploading(true);
    console.log("🚀 Starting deployment process...");

    try {
      // 1. Create/Validate the Zip
      const zip = new JSZip();
      if (file.name.endsWith('.zip')) {
        await zip.loadAsync(file);
      } else {
        zip.file(file.name, file);
      }
      
      const zipBlob = await zip.generateAsync({ type: 'blob' });

      // 2. Upload to R2 via Orchestrator
      const formData = new FormData();
      formData.append('file', zipBlob, 'project.zip'); 
      formData.append('clerk_id', user.id); 

      const uploadRes = await fetch(`${API_URL}/consumer/upload_project`, {
        method: 'POST',
        headers: { 'X-API-Key': CONSUMER_API_KEY }, // Added your security key
        body: formData
      });

      if (!uploadRes.ok) {
        const errorData = await uploadRes.json();
        throw new Error(errorData.error || 'Upload failed');
      }

      const { project_url } = await uploadRes.json();
      console.log("📂 File uploaded to R2:", project_url);
      
      // 3. Submit the Task to the Queue
      const submitRes = await fetch(`${API_URL}/consumer/submit_task`, {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'X-API-Key': CONSUMER_API_KEY // Added your security key
        },
        body: JSON.stringify({
          clerk_id: user.id,
          input_path: project_url,
          docker_image: 'runner:latest', // Matches the image name we built
          script_path: entryPoint 
        })
      });

      if (!submitRes.ok) throw new Error('Task submission failed');

      alert("🚀 Research task deployed to the Kolektif!");
      setFile(null); // Reset form
    } catch (err) {
      console.error("Deployment Error:", err);
      alert("Deployment Error: " + err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Paper withBorder p="xl" radius="md" shadow="sm">
      <Stack>
        <Title order={4}>Deploy Research Code</Title>
        <FileInput 
          label="Research Script or ZIP" 
          description="Select a .py file or a .zip project"
          placeholder="e.g. main.py" 
          value={file}
          onChange={setFile} 
          required
        />
        <TextInput 
          label="Entry Point Script"
          description="The script the agent should execute"
          value={entryPoint}
          onChange={(e) => setEntryPoint(e.target.value)}
        />
        <Button 
            onClick={handleUploadAndSubmit} 
            loading={uploading} 
            fullWidth 
            color="green"
            disabled={!file}
        >
          Zip & Run on Network
        </Button>
      </Stack>
    </Paper>
  );
}