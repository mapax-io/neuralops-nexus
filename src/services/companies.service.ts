import type { Company } from "@/types";

// TODO: implement API calls for companies
export function listCompanys(): Promise<Company[]> {
  throw new Error("Not implemented");
}

export function getCompany(id: string): Promise<Company> {
  void id;
  throw new Error("Not implemented");
}

export function createCompany(input: Partial<Company>): Promise<Company> {
  void input;
  throw new Error("Not implemented");
}

export function updateCompany(id: string, input: Partial<Company>): Promise<Company> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteCompany(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
