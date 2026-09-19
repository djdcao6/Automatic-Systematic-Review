import { ProjectShell } from "@/components/ProjectShell";

export default async function ReviewProjectLayout({
  children,
  params,
}: LayoutProps<"/review-projects/[id]">) {
  const { id } = await params;
  return <ProjectShell reviewProjectId={id}>{children}</ProjectShell>;
}
