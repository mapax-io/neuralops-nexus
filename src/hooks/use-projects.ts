import { useQuery } from "@tanstack/react-query";
import { listProjects } from "@/services/projects.service";

export function useProjects(companyId?: string) {
  return useQuery({
    queryKey: ["projects", companyId ?? "all"],
    queryFn: () => listProjects(companyId),
    enabled: false, // enable once backend is reachable
  });
}
