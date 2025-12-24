import { useEffect } from 'react';
import { AppShell, Burger, Group, Title, Container, Button, Center, Text, Loader } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { SubmitForm } from './components/SubmitForm';
import { 
  SignedIn, 
  SignedOut, 
  SignInButton, 
  UserButton,
  useUser,
  useAuth
} from "@clerk/clerk-react"; // Import Clerk components

function App() {
  const { isLoaded, isSignedIn, user } = useUser();
  const { getToken } = useAuth();
  const [opened, { toggle }] = useDisclosure();

 useEffect(() => {
    // 3. ...but the LOGIC inside only runs if the conditions are met
    if (isLoaded && isSignedIn && user) {
      const syncUser = async () => {
        try {
          await fetch('http://localhost:5000/auth/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              clerk_id: user.id,
              email: user.primaryEmailAddress.emailAddress
            }),
          });
          console.log("✅ User synced");
        } catch (err) {
          console.error("❌ Sync failed", err);
        }
      };
      syncUser();
    }
  }, [isLoaded, isSignedIn, user]);

  // 4. ONLY AFTER HOOKS can you have early returns for loading
  if (!isLoaded) {
    return <Center h="100vh"><Loader /></Center>;
  }
  
  return (
    <>
      {/* 1. VIEW FOR LOGGED OUT USERS */}
      <SignedOut>
        <Container h="100vh">
          <Center h="100%">
            <div style={{ textAlign: 'center' }}>
              <Title order={1} mb="md">🚀 Matcha Compute</Title>
              <Text mb="xl">Decentralized GPU computing for everyone.</Text>
              {/* This magic button handles the entire login flow */}
              <SignInButton mode="modal">
                <Button size="lg" variant="gradient" gradient={{ from: 'blue', to: 'cyan' }}>
                  Sign In / Register
                </Button>
              </SignInButton>
            </div>
          </Center>
        </Container>
      </SignedOut>

      {/* 2. VIEW FOR LOGGED IN USERS */}
      <SignedIn>
        <AppShell header={{ height: 60 }} padding="md">
          <AppShell.Header>
            <Group h="100%" px="md" justify="space-between">
              <Group>
                <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
                <Title order={3}>🚀 Matcha</Title>
              </Group>
              
              <Group>
                {/* Show the user's email */}
                <Text size="sm">{user?.primaryEmailAddress?.emailAddress}</Text>
                {/* This is the "Profile" circle that lets them logout */}
                <UserButton afterSignOutUrl="/"/>
              </Group>
            </Group>
          </AppShell.Header>

          <AppShell.Main>
            <Container>
              <SubmitForm />
            </Container>
          </AppShell.Main>
        </AppShell>
      </SignedIn>
    </>
  );
}

export default App;