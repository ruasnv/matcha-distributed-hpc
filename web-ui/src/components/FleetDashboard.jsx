import React, { useState, useEffect } from 'react';
import { 
  Table, 
  Badge, 
  Button, 
  Text as MantineText, 
  Group, 
  Stack, 
  Title, 
  Container, 
  Modal, 
  Paper, 
  Code, 
  CopyButton, 
  ActionIcon, 
  Center 
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconTerminal2, IconCopy, IconCheck, IconDeviceDesktop } from '@tabler/icons-react';

const API_URL = import.meta.env.VITE_API_URL || "https://matcha-orchestrator.onrender.com";

const FleetDashboard = ({ isSignedIn, user }) => { 
  const [devices, setDevices] = useState([]);
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
      {/* Header Section */}
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

      {/* Enrollment Instructions Modal */}
      <Modal opened={enrollOpened} onClose={closeEnroll} title="Add New Compute Node" size="lg" radius="md">
        <MantineText size="sm" mb="md" c="dimmed">
          Run these commands on the machine you want to add to the Kolektif.
        </MantineText>

        <Stack gap="md">
          <Paper withBorder p="xs" bg="gray.0">
            <MantineText size="xs" fw={700} mb={5} c="dimmed">1. GET THE AGENT</MantineText>
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
                  <ActionIcon color={copied ? 'teal' : 'gray'} onClick={copy} variant="subtle">
                    {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                  </ActionIcon>
                )}
              </CopyButton>
            </Group>
            <Code block color="dark.6" c="green.4" mt={5}>{enrollCommand}</Code>
          </Paper>
        </Stack>
      </Modal>

      {/* Device Table */}
      <Paper withBorder p="md" radius="md" shadow="sm">
        {devices.length === 0 ? (
          <Center h={100}>
            <MantineText c="dimmed">No devices enrolled yet.</MantineText>
          </Center>
        ) : (
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Device Name</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>CPU Load</Table.Th>
                <Table.Th>GPU Info</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {devices.map((device) => (
                <Table.Tr key={device.id}>
                  <Table.Td>
                    <Group gap="xs">
                      <IconDeviceDesktop size={16} stroke={1.5} />
                      <MantineText size="sm" fw={500}>{device.name || device.id.substring(0, 12)}</MantineText>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    {/* Dynamic Status Badge */}
                    <Badge 
                      color={device.status === 'active' ? 'green' : 'gray'} 
                      variant="light"
                    >
                      {device.status.toUpperCase()}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <MantineText size="sm">
                      {device.status === 'active' ? `${device.telemetry?.cpu_load}%` : '--'}
                    </MantineText>
                  </Table.Td>
                  <Table.Td>
                    <MantineText size="sm" c={device.status === 'active' ? 'inherit' : 'dimmed'}>
                      {device.telemetry?.gpu?.name || "None"}
                    </MantineText>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>
    </Container>
  );
};

export default FleetDashboard;