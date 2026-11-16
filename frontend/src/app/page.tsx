import { redirect } from "next/navigation";

export default function Home() {
  // The private area sends anonymous visitors to /login.
  redirect("/documents");
}
