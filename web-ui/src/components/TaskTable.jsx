import { Table, Badge, Button, Text, Group, ActionIcon, Tooltip } from '@mantine/core';
import { IconDownload, IconTerminal2 } from '@tabler/icons-react';

const CONSUMER_API_KEY = import.meta.env.VITE_ORCHESTRATOR_API_KEY_CONSUMERS;
const API_URL = import.meta.env.VITE_API_URL || "https://matcha-orchestrator.onrender.com";

export function TaskTable({ tasks = [] }) {
  if (!tasks || tasks.length === 0) {
    return <Text c="dimmed" ta="center" py="xl">No research tasks submitted yet.</Text>;
  }

  const handleDownload = async (taskId) => {
    try {
      const res = await fetch(`${API_URL}/consumer/download_results/${taskId}`, {
        headers: { 'X-API-Key': CONSUMER_API_KEY }
      });
      const data = await res.json();
      if (data.download_url) {
        window.open(data.download_url, '_blank'); // Opens the secure R2 link
      } else {
        alert("Download link could not be generated.");
      }
    } catch (err) {
      console.error("Download Error:", err);
    }
  };

  return (
    <Table verticalSpacing="sm">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>ID</Table.Th>
          <Table.Th>Status</Table.Th>
          <Table.Th>Output Snapshot</Table.Th>
          <Table.Th>Actions</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {tasks.map((task) => (
          <Table.Tr key={task.id}>
            <Table.Td>
              <Text size="xs" ff="monospace">
                {task.id ? task.id.substring(0, 8) : 'N/A'}
              </Text>
            </Table.Td>
            <Table.Td>
              <Badge 
                color={task.status === 'COMPLETED' ? 'green' : task.status === 'FAILED' ? 'red' : 'blue'} 
                variant="light"
              >
                {task.status}
              </Badge>
            </Table.Td>
            <Table.Td>
              <Text size="xs" truncate w={200}>
                {task.stdout || "No logs yet..."}
              </Text>
            </Table.Td>
            <Table.Td>
                  <Group gap="xs">
                    {/* 🚀 Changed logic: Show button if status is COMPLETED */}
                    {task.status === 'COMPLETED' && (
                      <Button 
                        onClick={() => handleDownload(task.id)} 
                        size="compact-xs" 
                        color="teal" 
                        variant="filled"
                        leftSection={<IconDownload size={14} />}
                      >
                        Results
                      </Button>
                )}
              </Group>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}