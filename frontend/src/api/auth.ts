import type { LoginOut, Me } from '@/types';
import { get, post } from './client';

export const authApi = {
  login: (username: string, password: string) => post<LoginOut>('/auth/login', { username, password }),
  verifyOtp: (otp_token: string, code: string) => post<LoginOut>('/auth/verify-otp', { otp_token, code }),
  me: () => get<Me>('/auth/me'),
  changePassword: (current_password: string, new_password: string) =>
    post<void>('/auth/change-password', { current_password, new_password }),
};
