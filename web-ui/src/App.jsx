import { useEffect, useState } from 'react';
import { AppShell, Burger, Group, NavLink, Text, Center, Loader, Stack, Title, Paper, Badge, Divider, Container } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconCpu, IconFlask, IconReceipt } from '@tabler/icons-react';
import { SubmitForm } from './components/SubmitForm';
import { TaskTable } from './components/TaskTable';
import { 
  SignedIn, 
  SignedOut, 
  SignInButton, 
  UserButton,
  useUser 
} from '@clerk/clerk-react';

// Centralize your API URL so it automatically switches between localhost and Render
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

export default function App() {
  const { isLoaded, isSignedIn, user } = useUser();
  const [opened, { toggle }] = useDisclosure();
  const [activePage, setActivePage] = useState('dashboard');
  const [tasks, setTasks] = useState([]);

  // 1. Sync User Logic
  useEffect(() => {
    if (isLoaded && isSignedIn && user) {
      fetch(`${API_URL}/auth/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clerk_id: user.id, email: user.primaryEmailAddress.emailAddress }),
      });
    }
  }, [isLoaded, isSignedIn, user]);

  // 2. Fetch User-Specific Tasks (Only active when on the 'dashboard' tab)
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

  // --- SUB-VIEWS ---
  // View 1: Your existing Research Tasks page
  const ResearchDashboard = () => (
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

  // View 2: The upcoming Fleet Manager
  const FleetDashboard = () => (
    <Container size="lg" py="md">
      <Title order={2}>Your Compute Nodes</Title>
      <Text c="dimmed" mb="xl">Manage your enrolled provider devices and view their live telemetry.</Text>
      <Paper withBorder p="xl" radius="md" shadow="sm">
        <Center h={200}>
          <Text c="dimmed">Device list and enrollment wizard coming next...</Text>
        </Center>
      </Paper>
    </Container>
  );

  return (
    <>
      <SignedOut>
        <Center h="100vh">
          <Stack align="center">
            <Title>Kolektif Network</Title>
            <Text c="dimmed">Distributed Compute for ML Research</Text>
            <SignInButton mode="modal" />
          </Stack>
        </Center>
      </SignedOut>

      <SignedIn>
        <AppShell
          header={{ height: 60 }}
          navbar={{ width: 280, breakpoint: 'sm', collapsed: { mobile: !opened } }}
          padding="md"
        >
          {/* TOP HEADER */}
          <AppShell.Header>
            <Group h="100%" px="md" justify="space-between">
              <Group>
                <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
                <Title order={3} variant="gradient" gradient={{ from: 'green', to: 'lime', deg: 90 }}>
                  Matcha Kolektif
                </Title>
              </Group>
              <Group>
                <Badge variant="dot" color="green" hiddenFrom="xs">Active</Badge>
                <UserButton afterSignOutUrl="/" />
              </Group>
            </Group>
          </AppShell.Header>

          {/* SIDEBAR NAVIGATION */}
          <AppShell.Navbar p="md">
            <Text size="xs" fw={500} c="dimmed" mb="sm">MAIN MENU</Text>
            
            <NavLink 
              label="Research Tasks" 
              leftSection={<IconFlask size="1.2rem" stroke={1.5} />} 
              active={activePage === 'dashboard'}
              onClick={() => setActivePage('dashboard')}
              variant="filled"
              color="green"
              mb={4}
              style={{ borderRadius: '8px' }}
            />
            
            <NavLink 
              label="Device Fleet" 
              leftSection={<IconCpu size="1.2rem" stroke={1.5} />} 
              active={activePage === 'fleet'}
              onClick={() => setActivePage('fleet')}
              variant="filled"
              color="green"
              mb={4}
              style={{ borderRadius: '8px' }}
            />

            <NavLink 
              label="Trust Ledger" 
              leftSection={<IconReceipt size="1.2rem" stroke={1.5} />} 
              active={activePage === 'ledger'}
              onClick={() => setActivePage('ledger')}
              variant="filled"
              color="green"
              style={{ borderRadius: '8px' }}
            />
          </AppShell.Navbar>

          {/* MAIN CONTENT AREA */}
          <AppShell.Main bg="#f8f9fa">
            {activePage === 'dashboard' && <ResearchDashboard />}
            {activePage === 'fleet' && <FleetDashboard />}
            {activePage === 'ledger' && (
              <Container size="lg" py="md">
                <Title order={2}>Blockchain Ledger</Title>
                <Text c="dimmed">Immutable history of network events will appear here.</Text>
              </Container>
            )}
          </AppShell.Main>
        </AppShell>
      </SignedIn>
    </>
  );
}