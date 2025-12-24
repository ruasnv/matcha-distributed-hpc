import { useState } from 'react';
import { TextInput, Button, Stack, Title, Paper, FileInput, Text } from '@mantine/core';
import JSZip from 'jszip';

const ORCHESTRATOR_URL = "http://localhost:5000";
// Matching your backend middleware key
const CONSUMER_API_KEY = "debug-consumer-key"; 

export function SubmitForm() {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [entryPoint, setEntryPoint] = useState('main.py');

  const handleUploadAndSubmit = async () => {
    if (!file) return;
    setUploading(true);

    try {
      // 1. Zip the files
      const zip = new JSZip();
      if (file.name.endsWith('.zip')) {
        zip.loadAsync(file);
      } else {
        zip.file(file.name, file);
      }
      const blob = await zip.generateAsync({ type: 'blob' });

      // 2. Upload to R2 via Orchestrator
      const formData = new FormData();
      formData.append('file', blob, 'project.zip');
      
      const uploadRes = await fetch('http://localhost:5000/consumer/upload_project', {
        method: 'POST',
        headers: { 'X-API-Key': 'debug-consumer-key' }, // AUTH IS KEY
        body: formData,
      });
      const { project_url } = await uploadRes.json();

      // 3. Submit Task to Orchestrator
      await fetch('http://localhost:5000/consumer/submit_task', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'X-API-Key': 'debug-consumer-key'
        },
        body: JSON.stringify({
          docker_image: 'matcha-runner:latest',
          input_path: project_url,
          script_path: entryPoint
        }),
      });

      alert("🚀 Research task deployed!");
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Paper withBorder p="xl" radius="md" shadow="sm">
      <Stack>
        <Title order={4}>Deploy Research Code</Title>
        <FileInput 
          label="Project Script" 
          description="Select your transformer/stochastic model script"
          placeholder="e.g. model.py" 
          onChange={setFile} 
        />
        <TextInput 
          label="Entry Point"
          value={entryPoint}
          onChange={(e) => setEntryPoint(e.target.value)}
        />
        <Button onClick={handleUploadAndSubmit} loading={uploading} fullWidth>
          Zip & Run on Network
        </Button>
      </Stack>
    </Paper>
  );
}