import { Table, Badge, Button, Text, Group, ActionIcon, Tooltip } from '@mantine/core';
import { IconDownload, IconTerminal2 } from '@tabler/icons-react';

export function TaskTable({ tasks = [] }) {
  if (!tasks || tasks.length === 0) {
    return <Text c="dimmed" ta="center" py="xl">No research tasks submitted yet.</Text>;
  }

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
                {/* 1. Download Link (Only shows if result_url exists) */}
                {task.result_url && (
                  <Button 
                    component="a" 
                    href={task.result_url} 
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