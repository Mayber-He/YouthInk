import React from "react";
import { NovelListPage } from "@/features/novels/NovelListPage";
import { AppSettingsModal } from "@/features/app-settings/AppSettingsModal";
import { WorkbenchLayout } from "@/layouts/WorkbenchLayout";
import { useUiStore } from "@/stores/uiStore";

export const App: React.FC = () => {
  const currentNovelUid = useUiStore((s) => s.currentNovelUid);

  return (
    <>
      {currentNovelUid ? <WorkbenchLayout /> : <NovelListPage />}
      <AppSettingsModal />
    </>
  );
};
