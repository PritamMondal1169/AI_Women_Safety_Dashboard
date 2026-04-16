import { create } from 'zustand';
import api from '../api';
import storage from '../utils/storage';

export const useAuthStore = create((set, get) => ({
  user: null,
  token: null,
  guardians: [],
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.post('/auth/login', { email, password });
      const { access_token, user } = response.data;
      await storage.setItem('token', access_token);
      set({ user, token: access_token, isLoading: false });
      get().fetchGuardians();
    } catch (error) {
      console.error('Login Error:', error);
      let errMsg = 'Login failed';
      if (error.message === 'Network Error') {
        errMsg = 'CONNECTION_FAILED: Ensure phone is on the same Wi-Fi as your laptop (192.168.1.237)';
      } else {
        errMsg = error.response?.data?.detail || 'Invalid Credentials';
      }
      set({ error: errMsg, isLoading: false });
    }
  },

  register: async (name, email, password, phone) => {
    set({ isLoading: true, error: null });
    try {
      await api.post('/auth/register', { name, email, password, phone });
      // Auto login after register
      const loginRes = await api.post('/auth/login', { email, password });
      const { access_token, user } = loginRes.data;
      await storage.setItem('token', access_token);
      set({ user, token: access_token, isLoading: false });
      get().fetchGuardians();
    } catch (error) {
      let errMsg = 'Registration failed';
      if (error.message === 'Network Error') {
        errMsg = 'CONNECTION_FAILED: Ensure phone is on the same Wi-Fi as your laptop (192.168.1.237)';
      } else {
        errMsg = error.response?.data?.detail || 'Registration failed';
      }
      set({ error: errMsg, isLoading: false });
    }
  },

  logout: async () => {
    await storage.deleteItem('token');
    set({ user: null, token: null, guardians: [] });
  },

  checkAuth: async () => {
    const token = await storage.getItem('token');
    if (token) {
      try {
        const response = await api.get('/auth/me');
        set({ user: response.data, token });
        get().fetchGuardians();
      } catch (error) {
        await storage.deleteItem('token');
        set({ user: null, token: null });
      }
  },

  fetchGuardians: async () => {
    try {
      const response = await api.get('/family');
      set({ guardians: response.data });
    } catch (err) {
      console.error('Failed to fetch guardians globally');
    }
  }
}));
