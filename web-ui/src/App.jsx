import { useEffect, useState } from 'react';
import { AppShell, TextInput, Burger, Group, NavLink, Text as MantineText, Center, Loader, Stack, Title, Paper, Button, Divider, Container } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconFlask, IconCpu } from '@tabler/icons-react';
import { SubmitForm } from './components/SubmitForm';
import { TaskTable } from './components/TaskTable';
import FleetDashboard from './components/FleetDashboard';
import {
  SignedIn, 
  SignedOut, 
  SignInButton, 
  UserButton,
  useUser 
} from '@clerk/clerk-react';

// 1. Better fallback for API URL
const API_URL = import.meta.env.VITE_API_URL || "https://matcha-orchestrator.onrender.com";

// 2. Keep Dashboard clean
const ResearchDashboard = ({ tasks }) => (
  <Container size="lg" py="md">
    <Stack gap="xl">
      <Paper withBorder p="xl" radius="md" shadow="sm">
        <SubmitForm />
      </Paper>
      <Divider my="sm" label="Your Research Tasks" labelPosition="center" />
      <Paper withBorder p="md" radius="md">
          <TaskTable tasks={tasks} />
      </Paper>
    </Stack>
  </Container>
);

export default function App() {
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [password, setPassword] = useState("");
  const { isLoaded, isSignedIn, user } = useUser();
  const [opened, { toggle }] = useDisclosure();
  const [activePage, setActivePage] = useState('dashboard');
  const [tasks, setTasks] = useState([]);

  // Sync Clerk user with backend DB
  useEffect(() => {
    if (isLoaded && isSignedIn && user) {
      fetch(`${API_URL}/auth/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          clerk_id: user.id, 
          email: user.primaryEmailAddress.emailAddress 
        }),
      });
    }
  }, [isLoaded, isSignedIn, user]);

  // Polling for tasks
  useEffect(() => {
    const fetchMyTasks = async () => {
      if (isSignedIn && user && activePage === 'dashboard') {
        try {
          const response = await fetch(`${API_URL}/consumer/tasks?clerk_id=${user.id}`);
          const data = await response.json();
          setTasks(Array.isArray(data) ? data : []);
        } catch (err) {
          console.error("Task fetch failed", err);
        }
      }
    };

    fetchMyTasks();
    const interval = setInterval(fetchMyTasks, 4000);
    return () => clearInterval(interval);
  }, [isSignedIn, user, activePage]);

  if (!isLoaded) return <Center h="100vh"><Loader /></Center>;

  // Password Gate (Only active in production)
  if (!isAuthorized && import.meta.env.PROD) {
    return (
      <Center h="100vh" bg="gray.1">
        <Paper withBorder p="xl" radius="md" shadow="md" w={350}>
          <Stack>
            <Title order={3}>Matcha Private Beta</Title>
            <MantineText size="sm" c="dimmed">Enter developer password to access the Kolektif.</MantineText>
            <TextInput 
              type="password" 
              placeholder="Password" 
              value={password} 
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && password === "Kolektif2026!" && setIsAuthorized(true)}
            />
            <Button 
              color="green" 
              onClick={() => {
                if (password === "Kolektif2026!") setIsAuthorized(true);
                else alert("Access Denied");
              }}
            >
              Enter System
            </Button>
          </Stack>
        </Paper>
      </Center>
    );
  }

  return (
    <>
      <SignedOut>
        <Center h="100vh" bg="#f8f9fa">
          <Paper withBorder p="xl" radius="md" shadow="xl" ta="center">
            <Stack align="center" gap="lg">
              <Title order={1}>Matcha Kolektif</Title>
              <MantineText c="dimmed">Decentralized Machine Intelligence Network</MantineText>
              <SignInButton mode="modal">
                <Button color="green" size="md">Sign In to Network</Button>
              </SignInButton>
            </Stack>
          </Paper>
        </Center>
      </SignedOut>

      <SignedIn>
        <AppShell
          header={{ height: 60 }}
          navbar={{ width: 280, breakpoint: 'sm', collapsed: { mobile: !opened } }}
          padding="md"
        >
          <AppShell.Header>
            <Group h="100%" px="md" justify="space-between">
              <Group>
                <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
                <Title order={3} c="green.8">Matcha Kolektif</Title>
              </Group>
              <UserButton afterSignOutUrl="/" />
            </Group>
          </AppShell.Header>

          <AppShell.Navbar p="md">
            <Stack gap="xs">
              <NavLink 
                label="Research Dashboard" 
                leftSection={<IconFlask size="1.2rem" />} 
                active={activePage === 'dashboard'} 
                onClick={() => setActivePage('dashboard')} 
                variant="light"
                color="green"
              />
              <NavLink 
                label="Compute Fleet" 
                leftSection={<IconCpu size="1.2rem" />} 
                active={activePage === 'fleet'} 
                onClick={() => setActivePage('fleet')} 
                variant="light"
                color="green"
              />
            </Stack>
          </AppShell.Navbar>

          <AppShell.Main bg="#f8f9fa">
            {activePage === 'dashboard' && <ResearchDashboard tasks={tasks} />}
            {activePage === 'fleet' && <FleetDashboard isSignedIn={isSignedIn} user={user} />}
          </AppShell.Main>
        </AppShell>
      </SignedIn>
    </>
  );
}