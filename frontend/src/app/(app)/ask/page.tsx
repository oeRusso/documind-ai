"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { PageHeader } from "@/components/people";
import { Chat } from "@/features/chat/chat";
import { ConversationList } from "@/features/chat/conversation-list";
import { useActiveOrganization } from "@/lib/organizations";

function AskPage() {
  const { organization } = useActiveOrganization();
  const conversationId = useSearchParams().get("c");
  if (!organization) return null;

  return (
    <>
      <PageHeader
        title="Preguntar"
        description="La IA responde solo con los documentos de tu organización y cita de dónde sale cada dato. Hacé clic en una cita para ver la página."
      />
      <div className="grid gap-8 md:grid-cols-[14rem_minmax(0,1fr)]">
        <ConversationList organizationId={organization.id} activeId={conversationId} />
        {/* key: another organization starts from scratch. Switching conversations is handled inside
            Chat, so the first question of a new conversation is not cut when its id enters the URL. */}
        <Chat
          key={organization.id}
          organizationId={organization.id}
          conversationId={conversationId}
        />
      </div>
    </>
  );
}

export default function Page() {
  // useSearchParams needs a Suspense boundary in the App Router.
  return (
    <Suspense>
      <AskPage />
    </Suspense>
  );
}
