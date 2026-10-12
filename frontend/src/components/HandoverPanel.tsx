import { useQueryClient } from '@tanstack/react-query';
import { Copy, Eye } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { errorMessage } from '@/api/client';
import { handoverApi } from '@/api/requests';
import { useAuth } from '@/auth/AuthProvider';
import { useAction } from '@/hooks';
import { METHOD_LABEL } from '@/lib/constants';
import { fmtDate, fmtDateTime, fromLocalInput, toLocalInput } from '@/lib/format';
import type { Handover, Reveal } from '@/types';

import { useToast } from './Toast';
import { Alert, Badge, Button, Details, Dialog, Field, Input } from './ui';

/**
 * Reveal a vault credential: email OTP, then the secret is shown for a limited time.
 * The secret lives only in this component's state — never in the query cache or storage —
 * and is cleared on unmount or when the countdown ends.
 */
function RevealCredential({ handoverId }: { handoverId: number }) {
  const toast = useToast();
  const [stage, setStage] = useState<'idle' | 'otp' | 'shown'>('idle');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [secret, setSecret] = useState<Reveal | null>(null);
  const [left, setLeft] = useState(0);

  const hide = useCallback(() => {
    setSecret(null);
    setStage('idle');
    setCode('');
    setError('');
  }, []);

  useEffect(() => () => setSecret(null), []);

  useEffect(() => {
    if (stage !== 'shown') return;
    if (left <= 0) {
      hide();
      return;
    }
    const id = window.setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(id);
  }, [stage, left, hide]);

  const requestCode = async () => {
    setBusy(true);
    setError('');
    try {
      await handoverApi.revealOtp(handoverId);
      setStage('otp');
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  };

  const reveal = async () => {
    setBusy(true);
    setError('');
    try {
      const data = await handoverApi.reveal(handoverId, code);
      setSecret(data);
      setLeft(data.visible_seconds || 60);
      setStage('shown');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
      setCode('');
    }
  };

  const copy = async () => {
    if (!secret) return;
    try {
      await navigator.clipboard.writeText(secret.secret);
      toast.success('Copied — paste it where you need it');
    } catch {
      toast.error('Could not copy — select the text and copy it manually');
    }
  };

  return (
    <>
      <Button variant="secondary" size="sm" loading={busy && stage === 'idle'} onClick={requestCode}>
        <Eye className="h-4 w-4" /> Reveal credential
      </Button>

      <Dialog
        open={stage === 'otp'}
        onClose={hide}
        title="Enter the code we emailed you"
        footer={
          <>
            <Button variant="secondary" onClick={hide}>Cancel</Button>
            <Button loading={busy} disabled={code.length !== 6} onClick={reveal}>Reveal</Button>
          </>
        }
      >
        <div className="space-y-3">
          {error && <Alert tone="red">{error}</Alert>}
          <Field label="6-digit code" hint="The credential will be visible for 60 seconds.">
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
          <button type="button" className="text-xs font-medium text-indigo-600 hover:underline" onClick={requestCode}>
            Send a new code
          </button>
        </div>
      </Dialog>

      <Dialog
        open={stage === 'shown' && !!secret}
        onClose={hide}
        title="Credential"
        footer={<Button onClick={hide}>Hide now</Button>}
      >
        {secret && (
          <div className="space-y-3">
            <Alert tone="amber">Hidden again in {left}s. Do not share or screenshot this.</Alert>
            <div className="flex items-start gap-2">
              <code className="min-w-0 flex-1 select-all break-all rounded-md bg-slate-900 px-3 py-2 font-mono text-sm text-emerald-300">
                {secret.secret}
              </code>
              <Button variant="secondary" size="sm" onClick={copy}>
                <Copy className="h-4 w-4" /> Copy
              </Button>
            </div>
            <Details
              items={[
                ['Login email', secret.login_email ?? '—'],
                ['Login URL', secret.login_url ?? '—'],
                ['Notes', secret.notes ?? '—'],
              ]}
            />
          </div>
        )}
      </Dialog>
    </>
  );
}

function SlotForm({ label, initial, withLocation, busy, onSubmit }: {
  label: string;
  initial?: string | null;
  withLocation?: boolean;
  busy: boolean;
  onSubmit: (at: string, location: string) => void;
}) {
  const [at, setAt] = useState(toLocalInput(initial));
  const [location, setLocation] = useState('');
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Field label="Date and time (Dhaka)">
        <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
      </Field>
      {withLocation && (
        <Field label="Location">
          <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="DMD Sir's office" />
        </Field>
      )}
      <Button size="sm" className="mb-0.5" loading={busy} disabled={!at} onClick={() => onSubmit(fromLocalInput(at), location)}>
        {label}
      </Button>
    </div>
  );
}

export function HandoverPanel({
  handover,
  isRequester,
  canReceive,
}: {
  handover: Handover;
  /** the signed-in user is the person receiving access */
  isRequester: boolean;
  /** request is handover_pending and the requester may confirm receipt */
  canReceive: boolean;
}) {
  const { isAdmin, me } = useAuth();
  const qc = useQueryClient();
  const done = () => void qc.invalidateQueries();

  const propose = useAction((at: string) => handoverApi.proposeSlot(handover.id, at), {
    success: 'Slot proposed — DMD Sir will confirm it',
  });
  const confirm = useAction(
    (v: { at: string; location: string }) => handoverApi.confirmSlot(handover.id, v.at, v.location),
    { success: 'Slot confirmed' },
  );
  const handedOver = useAction(() => handoverApi.handedOver(handover.id), { success: 'Marked as handed over' });
  const received = useAction(() => handoverApi.received(handover.id), {
    success: 'Thank you — access confirmed. The seat is now active.',
    onSuccess: done,
  });

  const canReveal = handover.method === 'vault' && handover.has_secret && (isRequester || !!me?.can_reveal_vault);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="indigo">{METHOD_LABEL[handover.method] ?? handover.method}</Badge>
        {handover.received_at && <Badge tone="green">Received {fmtDateTime(handover.received_at)}</Badge>}
      </div>

      {handover.method === 'vault' && (
        <>
          <Details
            items={[
              ['Login email', handover.login_email ?? '—'],
              ['Login URL', handover.login_url
                ? <a className="text-indigo-600 hover:underline" href={handover.login_url} target="_blank" rel="noreferrer">{handover.login_url}</a>
                : '—'],
              ['Notes', handover.notes ?? '—'],
              ['Credential', handover.has_secret ? 'Stored encrypted in the vault' : 'Not stored'],
            ]}
          />
          {canReveal && <RevealCredential handoverId={handover.id} />}
        </>
      )}

      {handover.method === 'appointment' && (
        <>
          <Details
            items={[
              ['Proposed by requester', fmtDateTime(handover.proposed_at)],
              ['Confirmed slot', handover.confirmed_at ? fmtDateTime(handover.confirmed_at) : 'Not confirmed yet'],
              ['Location', handover.location ?? '—'],
              ['Note', handover.notes ?? '—'],
            ]}
          />
          {isRequester && !handover.confirmed_at && !handover.received_at && (
            <SlotForm
              label={handover.proposed_at ? 'Propose another time' : 'Propose this time'}
              initial={handover.proposed_at}
              busy={propose.isPending}
              onSubmit={(at) => propose.mutate(at)}
            />
          )}
          {isAdmin && !handover.received_at && (
            <SlotForm
              label={handover.confirmed_at ? 'Change slot' : 'Confirm slot'}
              initial={handover.confirmed_at ?? handover.proposed_at}
              withLocation
              busy={confirm.isPending}
              onSubmit={(at, location) => confirm.mutate({ at, location })}
            />
          )}
        </>
      )}

      {handover.method === 'colleague' && (
        <>
          <Details
            items={[
              ['Collect from', handover.collector_name ?? '—'],
              ['Note', handover.notes ?? '—'],
              ['Due date', fmtDate(handover.due_date)],
              ['Handed over', handover.handed_over_at ? fmtDateTime(handover.handed_over_at) : 'Not yet'],
            ]}
          />
          {isAdmin && !handover.handed_over_at && !handover.received_at && (
            <Button variant="secondary" size="sm" loading={handedOver.isPending} onClick={() => handedOver.mutate(undefined)}>
              Mark handed over
            </Button>
          )}
        </>
      )}

      {canReceive && isRequester && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
          <p className="mb-2 text-sm text-emerald-900">Once you can sign in to the tool, confirm it here.</p>
          <Button variant="success" loading={received.isPending} onClick={() => received.mutate(undefined)}>
            I received access
          </Button>
        </div>
      )}
    </div>
  );
}
