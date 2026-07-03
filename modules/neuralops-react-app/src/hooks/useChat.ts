import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { getMessages, sendMessage } from "@/services/chat.service";

export function useMessages(topicId: string | null) {
  return useQuery({
    queryKey: ["messages", topicId],
    queryFn: () => getMessages(topicId as string),
    enabled: !!topicId,
  });
}

export function useSendMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: sendMessage,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["messages", data.topic_id] });
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
