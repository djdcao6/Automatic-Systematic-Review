import { redirect } from "next/navigation";

// The project's home is its Criteria section; the rail links to the others.
export default async function ReviewProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/review-projects/${id}/criteria`);
}
