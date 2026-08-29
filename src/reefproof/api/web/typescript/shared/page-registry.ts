export type PageController = Readonly<{
  page: string;
  mount: () => Promise<void> | void;
}>;

export const mountRegisteredPage = async (
  page: string | undefined,
  controllers: readonly PageController[],
): Promise<void> => {
  const matching = controllers.filter((controller) => controller.page === page);
  if (matching.length !== 1) {
    throw new Error(`Expected one controller for Workbench page: ${page ?? "missing"}`);
  }
  await matching[0]!.mount();
};
