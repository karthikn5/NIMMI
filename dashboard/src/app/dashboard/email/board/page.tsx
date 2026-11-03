import { redirect } from "next/navigation";

/** The board moved to Leads. */
export default function Page() {
    redirect("/dashboard/leads/board");
}
