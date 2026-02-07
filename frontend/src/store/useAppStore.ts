import { create } from 'zustand';

interface AppState {
  capitalTotal: number;
  botStatus: 'ACTIVE' | 'INACTIVE' | 'ERROR';
  setCapitalTotal: (amount: number) => void;
  setBotStatus: (status: 'ACTIVE' | 'INACTIVE' | 'ERROR') => void;
}

export const useAppStore = create<AppState>((set) => ({
  capitalTotal: 0,
  botStatus: 'ACTIVE',
  setCapitalTotal: (amount) => set({ capitalTotal: amount }),
  setBotStatus: (status) => set({ botStatus: status }),
}));
