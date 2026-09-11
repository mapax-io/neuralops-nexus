import { apiJson } from "./client";

/** One entry of the server's rights registry. */
export interface RightDef {
  code: string;
  object_type: string; // groups the table
  scope: string; // the narrowest level this right can be granted at
  description: string;
}

export interface RoleDef {
  id: string;
  name: string;
  scope: string;
  description: string;
  rights: string[];
  /** False for Owner, which always holds everything. Decided by the server. */
  editable: boolean;
  /** Rights this role may never be GRANTED (removing is still allowed). */
  locked_rights: string[];
}

export interface RolesPayload {
  rights: RightDef[];
  roles: RoleDef[];
}

export interface SetRoleRightsResult {
  id: string;
  name: string;
  rights: string[];
  added: string[];
  removed: string[];
}

// Owner-only: the server gates both on the role.update right.
export const listRoles = () => apiJson<RolesPayload>(`/api/v1/roles/`);

// Full-set replace — send what the role should grant, not a delta.
export const setRoleRights = (roleId: string, rights: string[]) =>
  apiJson<SetRoleRightsResult>(`/api/v1/roles/${roleId}/rights/`, {
    method: "PATCH",
    body: JSON.stringify({ rights }),
  });
