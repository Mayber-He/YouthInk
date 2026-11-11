/** Client-side UI state store using Zustand (Dev Doc Section 2.1). */

import { create } from "zustand";
import type { WorkbenchSection } from "@/types/api";

interface UiState {
  currentNovelUid: string | null;
  activeSection: WorkbenchSection;
  selectedChapterId: number | null;
  rightPanelOpen: boolean;
  focusMode: boolean;
  darkMode: boolean;
  settingsModalOpen: boolean;
  settingsInitialTab: "profiles" | "tasks" | "embedding" | "prompts" | "trust" | "styles";

  openNovel: (novelUid: string) => void;
  closeNovel: () => void;
  setActiveSection: (section: WorkbenchSection) => void;
  setSelectedChapterId: (chapterId: number | null) => void;
  toggleRightPanel: () => void;
  toggleFocusMode: () => void;
  toggleDarkMode: () => void;
  openSettingsModal: (tab?: "profiles" | "tasks" | "embedding" | "prompts" | "trust" | "styles") => void;
  closeSettingsModal: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  currentNovelUid: null,
  activeSection: "initiation",
  selectedChapterId: null,
  rightPanelOpen: true,
  focusMode: false,
  darkMode: false,
  settingsModalOpen: false,
  settingsInitialTab: "profiles",

  openNovel: (novelUid) =>
    set({
      currentNovelUid: novelUid,
      activeSection: "initiation",
      selectedChapterId: null,
    }),

  closeNovel: () =>
    set({
      currentNovelUid: null,
      selectedChapterId: null,
      focusMode: false,
    }),

  setActiveSection: (section) => set({ activeSection: section }),
  setSelectedChapterId: (chapterId) => set({ selectedChapterId: chapterId }),
  toggleRightPanel: () => set((state) => ({ rightPanelOpen: !state.rightPanelOpen })),
  toggleFocusMode: () => set((state) => ({ focusMode: !state.focusMode })),
  toggleDarkMode: () =>
    set((state) => {
      const next = !state.darkMode;
      if (typeof document !== "undefined") {
        document.documentElement.classList.toggle("dark", next);
      }
      return { darkMode: next };
    }),
  openSettingsModal: (tab = "profiles") =>
    set({ settingsModalOpen: true, settingsInitialTab: tab }),
  closeSettingsModal: () => set({ settingsModalOpen: false }),
}));
