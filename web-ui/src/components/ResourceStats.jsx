import { SimpleGrid, Paper, Text, Group, RingProgress } from '@mantine/core';

export function ResourceStats() {
  return (
    <SimpleGrid cols={3} mb="xl">
      <Paper p="md" withBorder>
        <Text size="xs" c="dimmed" fw={700} tt="uppercase">Active Providers</Text>
        <Text fw={700} size="xl">1 Online</Text>
      </Paper>
      <Paper p="md" withBorder>
        <Text size="xs" c="dimmed" fw={700} tt="uppercase">Network VRAM</Text>
        <Text fw={700} size="xl">0 GB (CPU Only)</Text>
      </Paper>
      <Paper p="md" withBorder>
        <Text size="xs" c="dimmed" fw={700} tt="uppercase">Queue Depth</Text>
        <Text fw={700} size="xl">0 Tasks</Text>
      </Paper>
    </SimpleGrid>
  );
}