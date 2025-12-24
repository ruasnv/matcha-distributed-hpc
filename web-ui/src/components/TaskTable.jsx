import { Table, Badge, Text, Group, Paper, Title, ActionIcon, Code } from '@mantine/core';
import { useEffect, useState } from 'react';

export function TaskTable() {
  const [tasks, setTasks] = useState([]);

  const fetchTasks = async () => {
    try {
      // For now, let's create a "debug" endpoint in your Flask routes 
      // to get all tasks, or fetch a specific one.
      const response = await fetch('http://localhost:5000/consumer/tasks/debug');
      const data = await response.json();
      setTasks(data);
    } catch (err) {
      console.error("Failed to fetch tasks", err);
    }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case 'COMPLETED': return 'green';
      case 'RUNNING': return 'blue';
      case 'FAILED': return 'red';
      case 'QUEUED': return 'gray';
      default: return 'cyan';
    }
  };

  return (
    <Paper shadow="xs" p="md" withBorder mt="xl">
      <Title order={3} mb="md">Your Tasks</Title>
      <Table verticalSpacing="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Task ID</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Submitted</Table.Th>
            <Table.Th>Provider</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {tasks.map((task) => (
            <Table.Tr key={task.id}>
              <Table.Td><Text size="xs" c="dimmed">{task.id.slice(0, 8)}...</Text></Table.Td>
              <Table.Td>
                <Badge color={getStatusColor(task.status)} variant="light">
                  {task.status}
                </Badge>
              </Table.Td>
              <Table.Td><Text size="xs">{new Date(task.submission_time).toLocaleTimeString()}</Text></Table.Td>
              <Table.Td><Text size="xs">{task.provider_id || 'Waiting...'}</Text></Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Paper>
  );
}