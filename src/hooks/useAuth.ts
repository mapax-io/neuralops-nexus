import { useQuery } from "@tanstack/react-query";
import { getAuthInit, getAuthStatus } from "@/services/auth.service";

export function useAuthInit() {
  return useQuery({
    queryKey: ["auth", "init"],
    queryFn: getAuthInit,
    refetchOnWindowFocus: false,
    retry: false,
  });
}

export function useAuthStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["auth", "status"],
    queryFn: getAuthStatus,
    enabled,
    refetchInterval: 3000,
    refetchOnWindowFocus: false,
  });
}
