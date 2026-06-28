// Front-end API client. Note: it shares no symbol name with the back-end
// handlers — the only thing connecting them is the route string. That is
// exactly the edge a knowledge graph can resolve and a long-context read can't.

export interface User {
  id: string;
  name: string;
}

export async function loadUser(userId: string): Promise<User> {
  const res = await fetch(`/api/users/${userId}`);
  return res.json();
}

export async function checkHealth(): Promise<boolean> {
  const res = await fetch("/api/health");
  return res.ok;
}

export function renderUser(user: User): string {
  return formatName(user) + " (#" + user.id + ")";
}

function formatName(user: User): string {
  return user.name.trim();
}
