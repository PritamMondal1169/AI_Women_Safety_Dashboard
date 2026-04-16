import axios from 'axios';
import storage from '../utils/storage';

// For production, set EXPO_PUBLIC_API_URL in your .env or Expo dashboard.
// Fallback to local machine for development.
export const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://192.168.1.237:8000/api/v1'; 
export const WS_URL = API_URL.replace('http', 'ws').replace('/api/v1', '/ws');

const api = axios.create({
  baseURL: API_URL,
});

api.interceptors.request.use(async (config) => {
  const token = await storage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
