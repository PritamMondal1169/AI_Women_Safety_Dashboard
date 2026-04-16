import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

/**
 * Universal storage utility that handles platform differences.
 * Uses expo-secure-store on Native and localStorage on Web.
 */
const storage = {
  setItem: async (key, value) => {
    try {
      if (Platform.OS === 'web') {
        localStorage.setItem(key, value);
      } else {
        await SecureStore.setItemAsync(key, value);
      }
    } catch (error) {
      console.error(`Storage setItem error [${key}]:`, error);
    }
  },

  getItem: async (key) => {
    try {
      if (Platform.OS === 'web') {
        return localStorage.getItem(key);
      } else {
        return await SecureStore.getItemAsync(key);
      }
    } catch (error) {
      console.error(`Storage getItem error [${key}]:`, error);
      return null;
    }
  },

  deleteItem: async (key) => {
    try {
      if (Platform.OS === 'web') {
        localStorage.removeItem(key);
      } else {
        await SecureStore.deleteItemAsync(key);
      }
    } catch (error) {
      console.error(`Storage deleteItem error [${key}]:`, error);
    }
  }
};

export default storage;
