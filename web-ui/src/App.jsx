import { useEffect, useState } from 'react';
import { Container, Stack, Title, Divider, Paper, Group, Text, Badge, Center, Loader } from '@mantine/core';
import { SubmitForm } from './components/SubmitForm';
import { TaskTable } from './components/TaskTable';
import { 
  SignedIn, 
  SignedOut, 
  SignInButton, 
  UserButton,
  useUser 
} from '@clerk/clerk-react';

export default function App() {
  const { isLoaded, isSignedIn, user } = useUser();
  const [tasks, setTasks] = useState([]); // State to hold the tasks

  // 1. Sync User Logic (Keep this)
  useEffect(() => {
    if (isLoaded && isSignedIn && user) {
      fetch('http://localhost:5000/auth/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clerk_id: user.id, email: user.primaryEmailAddress.emailAddress }),
      });
    }
  }, [isLoaded, isSignedIn, user]);

  // 2. NEW: Fetch User-Specific Tasks
  useEffect(() => {
    const fetchMyTasks = async () => {
      if (isSignedIn && user) {
        try {
          // We pass the clerk_id as a header or param to get ONLY this user's tasks
          const response = await fetch(`http://localhost:5000/consumer/tasks?clerk_id=${user.id}`);
          const data = await response.json();
          setTasks(Array.isArray(data) ? data : []);
        } catch (err) {
          console.error("Task fetch failed", err);
        }
      }
    };

    fetchMyTasks();
    const interval = setInterval(fetchMyTasks, 4000); // Polling for research updates
    return () => clearInterval(interval);
  }, [isSignedIn, user]);

  if (!isLoaded) return <Center h="100vh"><Loader /></Center>;

  return (
    <>
      {/* FEATURE RESTORED: Logged-out view */}
      <SignedOut>
        <Center h="100vh">
          <Stack align="center">
            <Title>Kolektif Network</Title>
            <SignInButton mode="modal" />
          </Stack>
        </Center>
      </SignedOut>

      {/* FEATURE RESTORED: Protected dashboard */}
      <SignedIn>
        <Container size="lg" py="xl">
          <Stack gap="xl">
            <Group justify="space-between">
              <Stack gap={0}>
                <Title order={1}>Kolektif Network</Title>
                <Text c="dimmed">Distributed Compute for ML Research</Text>
              </Stack>
              
              <Group>
                <Paper withBorder p="xs" radius="md">
                  <Group gap="xs">
                    <Badge variant="dot" color="green">Network Active</Badge>
                    <Text size="sm" fw={500}>{user?.primaryEmailAddress?.emailAddress}</Text>
                  </Group>
                </Paper>
                <UserButton afterSignOutUrl="/" />
              </Group>
            </Group>

            <Paper withBorder p="xl" radius="md" shadow="sm">
              <SubmitForm />
            </Paper>

            <Divider my="sm" label="Your Research Tasks" labelPosition="center" />

            <Paper withBorder p="md" radius="md">
               <TaskTable tasks={tasks} />
            </Paper>
          </Stack>
        </Container>
      </SignedIn>
    </>
  );
}