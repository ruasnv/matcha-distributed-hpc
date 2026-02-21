import { useEffect, useState } from 'react';
import { Modal, Code, CopyButton, Tooltip, ActionIcon, List, AppShell, TextInput, Burger, Group, NavLink, Text as MantineText, Center, Loader, Stack, Title, Paper, Button, Badge, Divider, Container, Table } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconCopy, IconCheck, IconTerminal2, IconCpu, IconFlask, IconReceipt } from '@tabler/icons-react';
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
  // 1. ALL HOOKS MUST GO HERE AT THE TOP (Unconditionally)
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [password, setPassword] = useState("");
  const { isLoaded, isSignedIn, user } = useUser();
  const [opened, { toggle }] = useDisclosure();
  const [activePage, setActivePage] = useState('dashboard');
  const [tasks, setTasks] = useState([]);

  // 2. ALL Effects also go here
  useEffect(() => {
    if (isLoaded && isSignedIn && user) {
      fetch(`${API_URL}/auth/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clerk_id: user.id, email: user.primaryEmailAddress.emailAddress }),
      });
    }
  }, [isLoaded, isSignedIn, user]);

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

  // 3. NOW START RETURNING VIEWS
  if (!isLoaded) return <Center h="100vh"><Loader /></Center>;

  // Developer Password Gate
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

  // --- SUB-VIEWS (Defined as functions or simple constants) ---
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

  const FleetDashboard = () => {
    const [devices, setDevices] = useState([]);
    // Using a specific name for enrollment modal to avoid conflicts
    const [enrollOpened, { open: openEnroll, close: closeEnroll }] = useDisclosure(false);
    const [token, setToken] = useState('');
    const [loadingToken, setLoadingToken] = useState(false);

    useEffect(() => {
      const fetchDevices = async () => {
        if (isSignedIn && user) {
          try {
            const response = await fetch(`${API_URL}/provider/my_devices?clerk_id=${user.id}`);
            const data = await response.json();
            setDevices(Array.isArray(data) ? data : []);
          } catch (err) {
            console.error("Failed to fetch devices", err);
          }
        }
      };
      fetchDevices();
      const interval = setInterval(fetchDevices, 5000);
      return () => clearInterval(interval);
    }, [isSignedIn, user]);

    const handleEnrollClick = async () => {
      setLoadingToken(true);
      try {
        const res = await fetch(`${API_URL}/auth/generate_enrollment_token`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ clerk_id: user.id })
        });
        const data = await res.json();
        setToken(data.token);
        openEnroll();
      } catch (err) {
        console.error("Token generation failed", err);
      } finally {
        setLoadingToken(false);
      }
    };

    const enrollCommand = `python agent.py --enroll ${token}`;

    return (
      <Container size="lg" py="md">
        <Group justify="space-between" mb="xl">
          <Stack gap={0}>
            <Title order={2}>Your Compute Nodes</Title>
            <MantineText c="dimmed">Live telemetry from your enrolled devices.</MantineText>
          </Stack>
          <Button 
            variant="light" 
            color="green" 
            leftSection={<IconTerminal2 size={18} />}
            loading={loadingToken}
            onClick={handleEnrollClick}
          >
            + Enroll New Device
          </Button>
        </Group>

        <Modal opened={enrollOpened} onClose={closeEnroll} title="Add New Compute Node" size="lg" radius="md">
          <MantineText size="sm" mb="md" c="dimmed">
            Run these commands on the machine you want to add to the Kolektif.
          </MantineText>

          <Stack gap="md">
            <Paper withBorder p="xs" bg="gray.0">
              <MantineText size="xs" fw={700} mb={5} c="dimmed">1. GET THE AGENT</MantineText>
              {/* Updated Git Link */}
              <Code block>git clone https://github.com/ruasnv/matcha-agent.git && cd matcha-agent</Code>
            </Paper>

            <Paper withBorder p="xs" bg="gray.0">
              <MantineText size="xs" fw={700} mb={5} c="dimmed">2. SETUP ENVIRONMENT</MantineText>
              <Code block>pip install -r requirements.txt</Code>
            </Paper>
            <Paper withBorder p="xs" bg="dark.7" c="white">
              <Group justify="space-between">
                <MantineText size="xs" fw={700}>3. RUN ENROLLMENT</MantineText>
                <CopyButton value={enrollCommand} timeout={2000}>
                  {({ copied, copy }) => (
                    <ActionIcon color={copied ? 'teal' : 'gray'} onClick={copy}>
                      {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                    </ActionIcon>
                  )}
                </CopyButton>
              </Group>
              <Code block color="dark.6" c="green.4">{enrollCommand}</Code>
            </Paper>
          </Stack>
        </Modal>

        <Paper withBorder p="md" radius="md">
          {devices.length === 0 ? <Center h={100}><MantineText c="dimmed">No devices enrolled yet.</MantineText></Center> : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Device Name</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>CPU</Table.Th>
                  <Table.Th>GPU</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {devices.map((device) => (
                  <Table.Tr key={device.id}>
                    <Table.Td>{device.name || device.id}</Table.Td>
                    <Table.Td><Badge color="green">{device.status}</Badge></Table.Td>
                    <Table.Td>{device.telemetry?.cpu_load}%</Table.Td>
                    <Table.Td>{device.telemetry?.gpu?.name || "None"}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Paper>
      </Container>
    );
  };

  // 4. THE MAIN LAYOUT
  return (
    <>
      <SignedOut>
        <Center h="100vh">
          <Stack align="center">
            <Title>Kolektif Network</Title>
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
          <AppShell.Header>
            <Group h="100%" px="md" justify="space-between">
              <Group>
                <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
                <Title order={3}>Matcha Kolektif</Title>
              </Group>
              <UserButton afterSignOutUrl="/" />
            </Group>
          </AppShell.Header>

          <AppShell.Navbar p="md">
            <NavLink label="Tasks" leftSection={<IconFlask size="1.2rem" />} active={activePage === 'dashboard'} onClick={() => setActivePage('dashboard')} />
            <NavLink label="Fleet" leftSection={<IconCpu size="1.2rem" />} active={activePage === 'fleet'} onClick={() => setActivePage('fleet')} />
          </AppShell.Navbar>

          <AppShell.Main bg="#f8f9fa">
            {activePage === 'dashboard' && <ResearchDashboard />}
            {activePage === 'fleet' && <FleetDashboard />}
          </AppShell.Main>
        </AppShell>
      </SignedIn>
    </>
  );
}