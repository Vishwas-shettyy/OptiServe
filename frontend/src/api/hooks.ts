// react-query hooks for every backend route. Home and Server detail poll every 5 s; other pages every 30 s.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./client";
import type { AppSettingsUpdate, AwsConnectBody, LoginBody, RecommendationStatus, User } from "./types";

export const POLL_FAST = 5_000;
export const POLL_SLOW = 30_000;

export const keys = {
  health: ["health"] as const,
  me: ["me"] as const,
  agentTokens: ["agent-tokens"] as const,
  connections: ["connections"] as const,
  recommendations: (statuses: RecommendationStatus[] | "all" | undefined) => ["recommendations", statuses ?? "open"] as const,
  actions: ["actions"] as const,
  stats: ["stats"] as const,
  groups: ["groups"] as const,
  weather: ["weather"] as const,
  servers: ["servers"] as const,
  server: (id: number) => ["server", id] as const,
  settings: ["settings"] as const,
  actionChart: (id: number) => ["action-chart", id] as const,
};

interface PollOptions {
  /** Refetch interval in ms; defaults to POLL_SLOW. */
  poll?: number;
}

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: api.health, refetchInterval: POLL_SLOW });
}

/** The signed-in admin, or null when signed out (401 is not an error here). */
export function useMe() {
  return useQuery<User | null, ApiError>({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        return await api.me();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation<User, ApiError, LoginBody>({
    mutationFn: api.login,
    onSuccess: (user) => {
      qc.setQueryData(keys.me, user);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError>({
    mutationFn: () => api.logout(),
    onSettled: () => {
      qc.clear();
      qc.setQueryData(keys.me, null);
    },
  });
}

export function useAgentTokens({ poll = POLL_SLOW }: PollOptions = {}) {
  return useQuery({ queryKey: keys.agentTokens, queryFn: api.agentTokens, refetchInterval: poll });
}

export function useCreateAgentToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (label: string) => api.createAgentToken(label),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.agentTokens }),
  });
}

export function useRevokeAgentToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.revokeAgentToken(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.agentTokens }),
  });
}

export function useConnections({ poll = POLL_SLOW }: PollOptions = {}) {
  return useQuery({ queryKey: keys.connections, queryFn: api.connections, refetchInterval: poll });
}

/** Check AWS credentials and list what they can see, without saving anything. */
export function useTestAws() {
  return useMutation<Awaited<ReturnType<typeof api.testAws>>, ApiError, AwsConnectBody>({ mutationFn: api.testAws });
}

export function useConnectAws() {
  const qc = useQueryClient();
  return useMutation<Awaited<ReturnType<typeof api.connectAws>>, ApiError, AwsConnectBody>({
    mutationFn: api.connectAws,
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useSyncConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.syncConnection(id),
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useRecommendations(statuses?: RecommendationStatus[] | "all", { poll = POLL_SLOW }: PollOptions = {}) {
  return useQuery({
    queryKey: keys.recommendations(statuses),
    queryFn: () => api.recommendations(statuses),
    refetchInterval: poll,
  });
}

function useActOnRecommendation<T>(fn: (id: number) => Promise<T>) {
  const qc = useQueryClient();
  return useMutation<T, ApiError, number>({
    mutationFn: fn,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["recommendations"] });
      void qc.invalidateQueries({ queryKey: keys.actions });
      void qc.invalidateQueries({ queryKey: keys.stats });
    },
  });
}

export function useApprove() {
  return useActOnRecommendation(api.approve);
}

export function useReject() {
  return useActOnRecommendation(api.reject);
}

export function useActions({ poll = POLL_SLOW, limit }: PollOptions & { limit?: number } = {}) {
  return useQuery({ queryKey: [...keys.actions, limit ?? "all"], queryFn: () => api.actions(limit), refetchInterval: poll });
}

/** The live fleet: every group with a tile per server. */
export function useGroups({ poll = POLL_SLOW }: PollOptions = {}) {
  return useQuery({ queryKey: keys.groups, queryFn: api.groups, refetchInterval: poll });
}

/** Capacity weather for the next 24 h (60 min in live mode). */
export function useWeather({ poll = POLL_SLOW }: PollOptions = {}) {
  return useQuery({ queryKey: keys.weather, queryFn: api.weather, refetchInterval: poll });
}

export function useStats({ poll = POLL_SLOW }: PollOptions = {}) {
  return useQuery({ queryKey: keys.stats, queryFn: api.stats, refetchInterval: poll });
}

export function useServers({ poll = POLL_SLOW }: PollOptions = {}) {
  return useQuery({ queryKey: keys.servers, queryFn: api.servers, refetchInterval: poll });
}

/** One server's detail page (polls every 5 s). */
export function useServer(id: number, { poll = POLL_FAST }: PollOptions = {}) {
  return useQuery({
    queryKey: keys.server(id),
    queryFn: () => api.server(id),
    refetchInterval: poll,
    enabled: Number.isInteger(id) && id > 0,
  });
}

export function useSetPrice() {
  const qc = useQueryClient();
  return useMutation<Awaited<ReturnType<typeof api.setPrice>>, ApiError, { id: number; hourlyUsd: number | null }>({
    mutationFn: ({ id, hourlyUsd }) => api.setPrice(id, hourlyUsd),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.servers });
      void qc.invalidateQueries({ queryKey: keys.stats });
      void qc.invalidateQueries({ queryKey: keys.groups });
    },
  });
}

export function useRemoveConnection() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: number) => api.removeConnection(id), onSuccess: () => qc.invalidateQueries() });
}

export function useAppSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: api.settings, refetchInterval: POLL_SLOW });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation<Awaited<ReturnType<typeof api.updateSettings>>, ApiError, AppSettingsUpdate>({
    mutationFn: api.updateSettings,
    onSuccess: (data) => {
      qc.setQueryData(keys.settings, data);
      void qc.invalidateQueries();
    },
  });
}

/** Before/after load for one Activity entry (fetched once; it only changes for 30 min after the action). */
export function useActionChart(id: number) {
  return useQuery({ queryKey: keys.actionChart(id), queryFn: () => api.actionChart(id), staleTime: 60_000 });
}
