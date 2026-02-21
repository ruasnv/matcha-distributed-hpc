import { useEffect, useState } from 'react';
import { Modal, Code, CopyButton, Tooltip, ActionIcon, List, AppShell, Burger, Group, NavLink, Text, Center, Loader, Stack, Title, Paper, Button, Badge, Divider, Container, Table } from '@mantine/core';
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
  const {isAuthorized, setIsAuthorized} = useState(false);
  const {password, setPassword} = useState("");
  if (!isAuthorized && import.meta.env.PROD) {
    return (
      <Center h="100vh" bg="gray.1">
        <Paper withBorder p="xl" radius="md" shadow="md" w={350}>
          <Stack>
            <Title order={3}>Matcha Private Beta</Title>
            <Text size="sm" c="dimmed">Enter developer password to access the Kolektif.</Text>
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

const FleetDashboard = () => {
  const [devices, setDevices] = useState([]);
  // Enrollment Modal States
  const [opened, { open, close }] = useDisclosure(false);
  const [token, setToken] = useState('');
  const [loadingToken, setLoadingToken] = useState(false);

  // Fetch devices logic (polling)
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

  // Generate Token logic
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
      open();
    } catch (err) {
      console.error("Token generation failed", err);
    } finally {
      setLoadingToken(false);
    }
  };

  const enrollCommand = `python agent.py --enroll ${token}`;

  return (
    <Container size="lg" py="md">
      {/* HEADER SECTION */}
      <Group justify="space-between" mb="xl">
        <Stack gap={0}>
          <Title order={2}>Your Compute Nodes</Title>
          <Text c="dimmed">Live telemetry from your enrolled devices.</Text>
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

      {/* ENROLLMENT INSTRUCTIONS MODAL */}
      <Modal opened={opened} onClose={close} title="Add New Compute Node" size="lg" radius="md">
        <Text size="sm" mb="md" c="dimmed">
          Run these commands on the machine you want to add to the Kolektif.
        </Text>

        <Stack gap="md">
          <Paper withBorder p="xs" bg="gray.0">
            <Text size="xs" fw={700} mb={5} c="dimmed">1. CLONE THE AGENT</Text>
            <Code block>git clone https://github.com/ruasnv/matcha-distributed-hpc.git</Code>
          </Paper>

          <Paper withBorder p="xs" bg="gray.0">
            <Text size="xs" fw={700} mb={5} c="dimmed">2. INSTALL DEPENDENCIES</Text>
            <Code block>pip install -r requirements.txt</Code>
          </Paper>

          <Paper withBorder p="xs" bg="dark.7" c="white">
            <Group justify="space-between" mb={5}>
              <Text size="xs" fw={700} c="gray.5">3. RUN ENROLLMENT</Text>
              <CopyButton value={enrollCommand} timeout={2000}>
                {({ copied, copy }) => (
                  <Tooltip label={copied ? 'Copied' : 'Copy'} withArrow position="right">
                    <ActionIcon color={copied ? 'teal' : 'gray'} variant="subtle" onClick={copy}>
                      {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                    </ActionIcon>
                  </Tooltip>
                )}
              </CopyButton>
            </Group>
            <Code block color="dark.6" c="green.4" style={{ border: '1px solid #333' }}>
              {enrollCommand}
            </Code>
            <Text size="xs" mt="xs" c="orange.4">Token expires in 15 minutes.</Text>
          </Paper>
        </Stack>

        <Button fullWidth mt="xl" onClick={close} variant="outline" color="gray">
          Close Window
        </Button>
      </Modal>

      {/* DEVICES TABLE */}
      <Paper withBorder p="md" radius="md" shadow="sm">
        {devices.length === 0 ? (
          <Center h={100}><Text c="dimmed">No devices enrolled yet.</Text></Center>
        ) : (
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Device Name</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>CPU Load</Table.Th>
                <Table.Th>GPU</Table.Th>
                <Table.Th>GPU Load</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {devices.map((device) => {
                const t = device.telemetry || {};
                const gpuName = t.gpu?.name || "CPU Only";
                const gpuLoad = t.gpu?.load || 0;
                
                return (
                  <Table.Tr key={device.id}>
                    <Table.Td fw={500}>{device.name || device.id}</Table.Td>
                    <Table.Td>
                      <Badge color={device.status === 'active' ? 'green' : 'red'} variant="light">
                        {device.status}
                      </Badge>
                    </Table.Td>
                    <Table.Td>{t.cpu_load ? `${t.cpu_load}%` : 'N/A'}</Table.Td>
                    <Table.Td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                       {gpuName}
                    </Table.Td>
                    <Table.Td>
                      {t.gpu ? (
                        <Group gap="xs">
                          <Text size="sm" w={35}>{gpuLoad}%</Text>
                          <div style={{ flex: 1, height: 8, backgroundColor: '#eee', borderRadius: 4, minWidth: 80 }}>
                            <div 
                              style={{ 
                                width: `${gpuLoad}%`, 
                                height: '100%', 
                                backgroundColor: gpuLoad > 80 ? '#fa5252' : '#40c057', 
                                borderRadius: 4,
                                transition: 'width 0.5s ease' 
                              }} 
                            />
                          </div>
                        </Group>
                      ) : (
                        <Text size="xs" c="dimmed">N/A</Text>
                      )}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        )}
      </Paper>
    </Container>
  );
};
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
} // <--- This closes the main App function!