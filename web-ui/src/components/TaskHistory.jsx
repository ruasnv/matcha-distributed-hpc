import { Table, Badge, Button, Text, Group, ActionIcon, Tooltip } from '@mantine/core';
import { IconDownload, IconTerminal2, IconExternalLink } from '@tabler/icons-react';

export function TaskHistory({ tasks }) {
  return (
    <Table highlightOnHover verticalSpacing="md">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Task ID</Table.Th>
          <Table.Th>Status</Table.Th>
          <Table.Th>Resources Used</Table.Th>
          <Table.Th>Actions</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {tasks.map((task) => (
          <Table.Tr key={task.task_id}>
            <Table.Td><Text size="sm" ff="monospace">{task.task_id.slice(0,8)}</Text></Table.Td>
            <Table.Td>
              <Badge 
                color={task.status === 'COMPLETED' ? 'green' : task.status === 'FAILED' ? 'red' : 'blue'}
                variant="light"
              >
                {task.status}
              </Badge>
            </Table.Td>
            <Table.Td><Text size="xs">CPU-Only Worker (ruya-laptop)</Text></Table.Td>
            <Table.Td>
              <Group gap="xs">
                <Tooltip label="View Logs">
                  <ActionIcon variant="light" onClick={() => showLogs(task.stdout)}><IconTerminal2 size={16} /></ActionIcon>
                </Tooltip>
                
                {task.result_url && (
                  <Tooltip label="Download Trained Model/Results">
                    <ActionIcon 
                      component="a" 
                      href={task.result_url} 
                      variant="filled" 
                      color="teal"
                    >
                      <IconDownload size={16} />
                    </ActionIcon>
                  </Tooltip>
                )}
              </Group>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}