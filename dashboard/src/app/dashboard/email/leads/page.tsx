import { redirect } from "next/navigation";

/** Lead sources moved to Leads. */
export default function Page() {
    redirect("/dashboard/leads/sources");
}
