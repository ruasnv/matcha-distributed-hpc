import { useState } from 'react';
import { TextInput, Textarea, Button, Group, Title, Paper, LoadingOverlay } from '@mantine/core';

// This is where your live orchestrator URL will go
const ORCHESTRATOR_URL = "https://matcha-orchestrator.onrender.com";
// We'll hard-code the consumer key for now. Later, this could be a login.
const CONSUMER_API_KEY = "your-secret-consumer-key";

export function SubmitForm() {
  const [image, setImage] = useState('python:3.10-slim-bookworm');
  const [scriptPath, setScriptPath] = useState('');
  const [inputPath, setInputPath] = useState('');
  const [outputPath, setOutputPath] = useState('');
  const [envVars, setEnvVars] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [submittedTaskId, setSubmittedTaskId] = useState(null);

  const handleSubmit = async () => {
    setLoading(true);
    setSubmittedTaskId(null);

    // Parse env vars
    const env_dict = {};
    if (envVars) {
      for (const item of envVars.split(',')) {
        const [key, value] = item.split('=', 1);
        env_dict[key] = value;
      }
    }

    const payload = {
      docker_image: image,
      script_path: scriptPath || null,
      input_path: inputPath || null,
      output_path: outputPath || null,
      env_vars: env_dict
    };

    try {
      const response = await fetch(`${ORCHESTRATOR_URL}/consumer/submit_task`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': CONSUMER_API_KEY,
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to submit task');
      }

      setSubmittedTaskId(data.task_id);
      // We will add a "cool" pop-up notification here later
      console.log("Task submitted!", data);

    } catch (error) {
      console.error("Submission failed:", error);
      // We'll add a "cool" error notification here
    }
    setLoading(false);
  };

  return (
    <Paper withBorder shadow="md" p="xl" radius="md" style={{ position: 'relative' }}>
      <LoadingOverlay visible={loading} zIndex={1000} overlayProps={{ radius: "sm", blur: 2 }} />
      <Title order={3} mb="lg">Submit a New Task</Title>
      
      <TextInput
        label="Docker Image"
        placeholder="e.g., pytorch/pytorch:latest"
        value={image}
        onChange={(e) => setImage(e.currentTarget.value)}
        mb="sm"
        required
      />
      <TextInput
        label="Script Path (R2/S3)"
        placeholder="r2://my-bucket/train.py"
        value={scriptPath}
        onChange={(e) => setScriptPath(e.currentTarget.value)}
        mb="sm"
      />
      <TextInput
        label="Input Data Path (R2/S3)"
        placeholder="r2://my-bucket/dataset.zip"
        value={inputPath}
        onChange={(e) => setInputPath(e.currentTarget.value)}
        mb="sm"
      />
      <TextInput
        label="Output Path (R2/S3)"
        placeholder="r2://my-bucket/results/"
        value={outputPath}
        onChange={(e) => setOutputPath(e.currentTarget.value)}
        mb="lg"
      />
      <Textarea
        label="Environment Variables"
        placeholder="KEY=VALUE,ANOTHER_KEY=ANOTHER_VALUE"
        value={envVars}
        onChange={(e) => setEnvVars(e.currentTarget.value)}
        mb="lg"
      />
      
      <Group justify="flex-end">
        <Button onClick={handleSubmit}>
          Submit Task
        </Button>
      </Group>

      {submittedTaskId && (
        <Paper withBorder p="md" mt="lg" radius="md">
          <Title order={5}> Task Submitted!</Title>
          <p>Your Task ID is: {submittedTaskId}</p>
          <p>We'll build the status viewer next!</p>
        </Paper>
      )}
    </Paper>
  );
}