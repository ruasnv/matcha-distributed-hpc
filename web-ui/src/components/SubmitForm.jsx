import { useState } from 'react';
import { TextInput, Button, Stack, Title, Paper, FileInput, Text } from '@mantine/core';
import JSZip from 'jszip';
import { useUser } from '@clerk/clerk-react';

const ORCHESTRATOR_URL = "http://localhost:5000";
// Matching your backend middleware key
const CONSUMER_API_KEY = "ultrasecretconsumerkey456"; 

export function SubmitForm() {
  const { user } = useUser();
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [entryPoint, setEntryPoint] = useState('main.py');

  const handleUploadAndSubmit = async () => {
    if (!file) return;
    setUploading(true);

    if (!user) {
      console.error("No user found");
      return;
    }

    try {
      // 1. Create the Zip
      const zip = new JSZip();
      
      // If user uploaded a single .py file, we wrap it. 
      // If it's already a zip, we can just pass it through or re-zip.
      if (file.name.endsWith('.zip')) {
        await zip.loadAsync(file);
      } else {
        zip.file(file.name, file);
      }
      
      const zipBlob = await zip.generateAsync({ type: 'blob' });

      // 2. Prepare the Payload
      const formData = new FormData();
      
      // FIX: Use 'zipBlob' instead of 'file', and give it a name like 'project.zip'
      formData.append('file', zipBlob, 'project.zip'); 
      formData.append('clerk_id', user.id); 

      // 3. Upload to R2 via Orchestrator
      const uploadRes = await fetch('http://localhost:5000/consumer/upload_project', {
        method: 'POST',
        // Note: Do NOT set 'Content-Type' header here. 
        // The browser sets it automatically with the correct "boundary" for FormData.
        body: formData
      });

      if (!uploadRes.ok) throw new Error('Upload failed');

      const { project_url } = await uploadRes.json();
      
      // 4. Finally, Submit the Task to the Queue
      const submitRes = await fetch('http://localhost:5000/consumer/submit_task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clerk_id: user.id,
          input_path: project_url, // This is the Presigned R2 link
          docker_image: 'matcha-runner:latest',
          script_path: file.name.endsWith('.zip') ? 'main.py' : file.name 
        })
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
          label="Script" 
          description="Select your script"
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