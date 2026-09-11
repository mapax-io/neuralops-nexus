"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { listPersonas, type Persona } from "@/lib/api/intelligence";
import { listTeam, type TeamMember } from "@/lib/api/team";
import { isMentionableName, CONTEXT_DIRECTIVE, OUTPUT_DIRECTIVES } from "@/lib/composer/directives";
import { SLASH_COMMANDS } from "@/lib/composer/slash";
import type { KnownSets } from "@/lib/composer/mention-ranges";
import { useConnectionStore } from "@/stores/connection.store";

export interface KnownMentions {
  personas: Persona[];
  humans: TeamMember[];
  /** The signed-in user's own mentionable name, matched by email. */
  selfName: string | null;
  personasLoading: boolean;
  personasError: boolean;
  /** What counts as a real @name or /command in this project. */
  known: KnownSets;
}

/**
 * Who and what can be @mentioned in a project — the single source for both the
 * composer's pill decoration and the chat transcript's rendering, so a name
 * reads the same in the box you type it in and the message it becomes.
 *
 * The two queries use the same keys the composer already used, so mounting
 * this alongside it costs no extra requests (React Query dedupes).
 */
export function useKnownMentions(projectId?: string): KnownMentions {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  const email = useConnectionStore((s) => s.email);

  const enabled = !!serverUrl && !!token && !!projectId;
  const personasQ = useQuery({
    queryKey: ["personas", serverUrl, projectId],
    queryFn: () => listPersonas(projectId!),
    enabled,
    staleTime: 60_000,
  });
  const teamQ = useQuery({
    queryKey: ["team", serverUrl, projectId],
    queryFn: () => listTeam(projectId!),
    enabled,
    staleTime: 60_000,
  });

  const personas = useMemo(() => personasQ.data ?? [], [personasQ.data]);
  const humans = useMemo(
    () => (teamQ.data ?? []).filter((m) => m.member_type === "human" && isMentionableName(m.name)),
    [teamQ.data],
  );
  const selfName = useMemo(
    () => (email ? humans.find((m) => m.email.toLowerCase() === email.toLowerCase())?.name ?? null : null),
    [humans, email],
  );

  // Memoised so consumers can pass it to memo()'d children without thrashing.
  const known = useMemo<KnownSets>(() => {
    const selfLower = selfName?.toLowerCase();
    return {
      mentions: new Set<string>([
        ...OUTPUT_DIRECTIVES.map((d) => d.name),
        "session",
        CONTEXT_DIRECTIVE.name,
        ...personas.filter((p) => isMentionableName(p.name)).map((p) => p.name.toLowerCase()),
      ]),
      self: new Set(selfLower ? [selfLower] : []),
      humans: new Set(humans.map((m) => m.name.toLowerCase()).filter((n) => n !== selfLower)),
      commands: new Set(SLASH_COMMANDS.map((c) => c.name)),
    };
  }, [personas, humans, selfName]);

  return {
    personas,
    humans,
    selfName,
    personasLoading: personasQ.isLoading,
    personasError: personasQ.isError,
    known,
  };
}
