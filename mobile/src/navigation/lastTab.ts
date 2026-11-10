import AsyncStorage from '@react-native-async-storage/async-storage';
import type { TabParamList } from './types';

// Which tab was open last. Not sensitive, so plain storage is fine (tokens stay in secure storage).
const KEY = 'splitapp.lastTab';
export const TAB_NAMES: (keyof TabParamList)[] = [
  'Friends',
  'Groups',
  'Activity',
  'Account',
];
export const DEFAULT_TAB: keyof TabParamList = 'Groups';

export async function loadLastTab(): Promise<keyof TabParamList> {
  try {
    const v = await AsyncStorage.getItem(KEY);
    return TAB_NAMES.find(t => t === v) ?? DEFAULT_TAB;
  } catch {
    return DEFAULT_TAB;
  }
}

export async function saveLastTab(tab: keyof TabParamList): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, tab);
  } catch {
    // Best effort: losing the remembered tab is harmless.
  }
}
