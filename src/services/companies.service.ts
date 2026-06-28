// Empty service shell — implement endpoints as the Django API is wired up.
import { apiJson } from "./api.client";
import type { Company } from "@/types";

export async function listCompanies(): Promise<Company[]> {
  return apiJson<Company[]>("/api/v1/companies/");
}

export async function getCompany(id: string): Promise<Company> {
  return apiJson<Company>(`/api/v1/companies/${id}/`);
}
