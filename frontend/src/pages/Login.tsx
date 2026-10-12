import { zodResolver } from '@hookform/resolvers/zod';
import { ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Navigate, useLocation } from 'react-router-dom';
import { z } from 'zod';

import { authApi } from '@/api/auth';
import { errorMessage, errorStatus } from '@/api/client';
import { useAuth } from '@/auth/AuthProvider';
import { Alert, Button, Field, Input } from '@/components/ui';

const schema = z.object({
  username: z.string().trim().min(1, 'Enter your employee code or email'),
  password: z.string().min(1, 'Enter your password'),
});
type Credentials = z.infer<typeof schema>;

const RESEND_SECONDS = 60;

export default function Login() {
  const { token, signIn } = useAuth();
  const location = useLocation();
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  // OTP step: the credentials are kept in memory only, to be able to resend the code
  const [otp, setOtp] = useState<{ token: string; creds: Credentials } | null>(null);
  const [code, setCode] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  const form = useForm<Credentials>({ resolver: zodResolver(schema), defaultValues: { username: '', password: '' } });

  useEffect(() => {
    if (cooldown <= 0) return;
    const id = window.setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => window.clearTimeout(id);
  }, [cooldown]);

  if (token) {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from && from !== '/login' ? from : '/'} replace />;
  }

  const fail = (err: unknown) =>
    setError(
      errorStatus(err) === 423
        ? 'Too many failed attempts — this account is locked for a few minutes. Try again later.'
        : errorMessage(err),
    );

  const login = async (creds: Credentials) => {
    setError('');
    setInfo('');
    try {
      const res = await authApi.login(creds.username, creds.password);
      if (res.otp_required && res.otp_token) {
        setOtp({ token: res.otp_token, creds });
        setCode('');
        setCooldown(RESEND_SECONDS);
      } else if (res.access_token) {
        signIn(res.access_token);
      }
    } catch (err) {
      fail(err);
    }
  };

  const verify = async () => {
    if (!otp) return;
    setError('');
    setInfo('');
    setVerifying(true);
    try {
      const res = await authApi.verifyOtp(otp.token, code);
      if (res.access_token) signIn(res.access_token);
    } catch (err) {
      fail(err);
    } finally {
      setVerifying(false);
    }
  };

  const resend = async () => {
    if (!otp) return;
    await login(otp.creds);
    setInfo('A new code has been sent.');
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-8">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-5 flex items-center gap-2">
          <ShieldCheck className="h-8 w-8 text-indigo-600" aria-hidden />
          <div>
            <h1 className="text-lg font-bold leading-tight text-slate-900">SMP</h1>
            <p className="text-xs text-slate-500">Subscription Management Platform · BMD / AES</p>
          </div>
        </div>

        {error && <div className="mb-3"><Alert tone="red">{error}</Alert></div>}
        {info && !error && <div className="mb-3"><Alert tone="green">{info}</Alert></div>}

        {!otp ? (
          <form onSubmit={form.handleSubmit(login)} className="space-y-3" noValidate>
            <Field label="Employee code or email" error={form.formState.errors.username?.message}>
              <Input autoFocus autoComplete="username" {...form.register('username')} />
            </Field>
            <Field label="Password" error={form.formState.errors.password?.message}>
              <Input type="password" autoComplete="current-password" {...form.register('password')} />
            </Field>
            <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
              Sign in
            </Button>
          </form>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void verify();
            }}
          >
            <p className="text-sm text-slate-600">
              We emailed a 6-digit code to you. Enter it to finish signing in.
            </p>
            <Field label="Verification code">
              <Input
                autoFocus
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                className="text-center text-lg tracking-[0.5em]"
              />
            </Field>
            <Button type="submit" className="w-full" loading={verifying} disabled={code.length !== 6}>
              Verify
            </Button>
            <div className="flex items-center justify-between text-xs">
              <button type="button" className="text-slate-500 hover:underline" onClick={() => { setOtp(null); setError(''); setInfo(''); }}>
                ← Back
              </button>
              <button
                type="button"
                className="font-medium text-indigo-600 hover:underline disabled:text-slate-400 disabled:no-underline"
                disabled={cooldown > 0}
                onClick={resend}
              >
                {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
