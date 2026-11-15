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
        {/* key: switching conversations starts from a clean state (no answer of the other one). */}
        <Chat
          key={`${organization.id}:${conversationId ?? "new"}`}
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
