import { AppShell, Burger, Group, Title, Container } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { SubmitForm } from './components/SubmitForm'; // <-- 1. IMPORT IT

function App() {
  const [opened, { toggle }] = useDisclosure();

  return (
    <AppShell
      header={{ height: 60 }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md">
          <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
          <Title order={2}>Matcha Compute</Title>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Container>
          {/* 2. ADD IT HERE, REMOVE THE OLD TITLE */}
          <SubmitForm /> 
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}

export default App;