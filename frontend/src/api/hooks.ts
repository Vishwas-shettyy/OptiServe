// react-query hooks for every backend route. Home and Server detail poll every 5 s; other pages every 30 s.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./client";
import type { AwsConnectBody, LoginBody, RecommendationStatus, User } from "./types";

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

export function useActions({ poll = POLL_SLOW }: PollOptions = {}) {
  return useQuery({ queryKey: keys.actions, queryFn: () => api.actions(), refetchInterval: poll });
}

export function useStats({ poll = POLL_SLOW }: PollOptions = {}) {
  return useQuery({ queryKey: keys.stats, queryFn: api.stats, refetchInterval: poll });
}
